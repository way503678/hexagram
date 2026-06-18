# -*- coding: utf-8 -*-
"""
PostgreSQL 紀錄存取
連線資訊由環境變數提供：
  PG_HOST     (預設 postgres)
  PG_PORT     (預設 5432)
  PG_USER     (預設 postgres)
  PG_PASSWORD (預設 postgres)
  PG_DATABASE (預設 hexagram)

若任一連線步驟失敗，所有函式都會吞掉例外、印警告，並讓網頁繼續運作。
排盤功能不應該因為 DB 掛掉而中斷。
"""
import os
import logging
import time
import threading
from datetime import datetime
from contextlib import contextmanager

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2 import pool as _pg_pool
    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False

log = logging.getLogger("hexagram.db")

PG_CONF = {
    "host":     os.environ.get("PG_HOST", "postgres"),
    "port":     int(os.environ.get("PG_PORT", "5432")),
    "user":     os.environ.get("PG_USER", "postgres"),
    "password": os.environ.get("PG_PASSWORD", "postgres"),
    "dbname":   os.environ.get("PG_DATABASE", "hexagram"),
    "connect_timeout": 5,
    # TCP keepalive:讓 OS 偵測到斷掉的連線,避免池裡留死連線
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
}

# 是否啟用 DB（預設啟用）；想暫時關掉，設環境變數 DB_ENABLED=0
DB_ENABLED = os.environ.get("DB_ENABLED", "1") == "1"


def norm_gender(v):
    """性別正規化的單一來源:'M'/'F' 維持原值,其餘一律 None。

    呼叫端若需要空字串(例如填回表單)可用 `norm_gender(v) or ""`。
    """
    return v if v in ("M", "F") else None

# 連線池上限(每個 gunicorn worker 各一個池;2 workers × 4 threads,8 足夠)
_POOL_MAX = int(os.environ.get("PG_POOL_MAX", "8"))
# 連線最大壽命(秒):超過就回收換新,避免連線無限老化
_CONN_MAX_AGE = int(os.environ.get("PG_CONN_MAX_AGE", "600"))
_POOL = None
_POOL_PID = None
_POOL_LOCK = threading.Lock()
_CONN_BORN = {}  # id(conn) -> 首次取用的時間(算壽命用)


def _get_pool():
    """取得本行程的連線池(lazy 建立)。

    用 pid 綁定:gunicorn fork 出來的子行程第一次用到時會各自建自己的池,
    避免把 fork 前建立的連線跨行程共用(那會出錯)。
    """
    global _POOL, _POOL_PID
    pid = os.getpid()
    if _POOL is None or _POOL_PID != pid:
        with _POOL_LOCK:
            if _POOL is None or _POOL_PID != pid:
                _POOL = _pg_pool.ThreadedConnectionPool(1, _POOL_MAX, **PG_CONF)
                _POOL_PID = pid
    return _POOL


def _discard_conn(pool, c):
    """把一條連線從池中關掉丟棄(不歸還),並清掉壽命紀錄。"""
    _CONN_BORN.pop(id(c), None)
    try:
        pool.putconn(c, close=True)
    except Exception:
        pass


def _get_live_conn(pool):
    """從池取一條「確定健康」的連線。健康機制三層:
      1. 太老(超過 _CONN_MAX_AGE)→ 回收換新,避免連線無限老化。
      2. SELECT 1 驗證仍活著(連線已開好,只是極輕量往返,遠比重新 connect 便宜)。
      3. 驗證失敗 → 關掉丟棄,再換一條。
    保留原本「每次操作都拿到可用連線」的語意。
    """
    last_err = None
    for _ in range(3):
        c = pool.getconn()
        born = _CONN_BORN.get(id(c))
        now = time.time()
        # 1. 壽命到了就回收
        if born is not None and (now - born) > _CONN_MAX_AGE:
            _discard_conn(pool, c)
            continue
        # 2. 健檢
        try:
            with c.cursor() as cur:
                cur.execute("SELECT 1")
            c.rollback()  # 結束驗證用的隱式交易
        except Exception as e:
            last_err = e
            _discard_conn(pool, c)  # 3. 壞了就丟
            continue
        if born is None:
            _CONN_BORN[id(c)] = now
        return c
    raise last_err or RuntimeError("no live DB connection")


@contextmanager
def _conn():
    """連線 context manager(改用連線池)。

    行為與原本一致:成功 commit、例外 rollback 並向外拋。差別只在連線取自
    池、用完歸還(若途中連線壞掉就關掉不歸還),省去每次 connect 的握手成本。
    """
    if not HAS_PSYCOPG:
        raise RuntimeError("psycopg2 not installed")
    pool = _get_pool()
    c = _get_live_conn(pool)
    healthy = True
    try:
        yield c
        c.commit()
    except Exception:
        try:
            c.rollback()
        except Exception:
            healthy = False  # rollback 都失敗 → 連線已壞,別歸還
        raise
    finally:
        if healthy:
            try:
                pool.putconn(c)
            except Exception:
                pass
        else:
            _discard_conn(pool, c)  # 壞連線:關掉丟棄,別污染池


SCHEMA = """
CREATE TABLE IF NOT EXISTS divination_logs (
    id            SERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    client_name   TEXT NOT NULL,
    gender        CHAR(1),
    input_year    INTEGER NOT NULL,
    input_month   INTEGER NOT NULL,
    input_day     INTEGER NOT NULL,
    input_hour    INTEGER NOT NULL,
    query_count   INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT divination_logs_unique
        UNIQUE (client_name, input_year, input_month, input_day, input_hour)
);
CREATE INDEX IF NOT EXISTS idx_divination_logs_created_at
    ON divination_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_divination_logs_client_name
    ON divination_logs (client_name);
"""

# 對舊資料庫升級：若 table 已存在但缺欄位或約束，補上去
MIGRATE = """
DO $$
BEGIN
    -- 1. client_name 改為 NOT NULL（若曾經有 NULL 紀錄會失敗，先把它刪掉）
    DELETE FROM divination_logs WHERE client_name IS NULL;
    BEGIN
        ALTER TABLE divination_logs ALTER COLUMN client_name SET NOT NULL;
    EXCEPTION WHEN others THEN NULL;
    END;

    -- 2. 若 UNIQUE 約束不存在，補上
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'divination_logs_unique'
    ) THEN
        -- 若已有重複資料，先各保留最新一筆
        DELETE FROM divination_logs a USING divination_logs b
        WHERE a.id < b.id
          AND a.client_name = b.client_name
          AND a.input_year  = b.input_year
          AND a.input_month = b.input_month
          AND a.input_day   = b.input_day
          AND a.input_hour  = b.input_hour;

        ALTER TABLE divination_logs
            ADD CONSTRAINT divination_logs_unique
            UNIQUE (client_name, input_year, input_month, input_day, input_hour);
    END IF;

    -- 3. 若 query_count 欄位不存在，補上（預設值 1，所有舊紀錄都是 1）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'divination_logs' AND column_name = 'query_count'
    ) THEN
        ALTER TABLE divination_logs
            ADD COLUMN query_count INTEGER NOT NULL DEFAULT 1;
    END IF;

    -- 4. 若 gender 欄位不存在，補上（CHAR(1)：M/F/NULL）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'divination_logs' AND column_name = 'gender'
    ) THEN
        ALTER TABLE divination_logs
            ADD COLUMN gender CHAR(1);
    END IF;
END$$;
"""


# ============================================================
# 點數系統:會員、點數帳本、綠界訂單
#   - users.points_balance:可快速讀取、可加鎖的餘額(扣點用)
#   - point_ledger:每筆增減的稽核帳本(餘額異動的真相來源)
#   - payment_orders:綠界儲值訂單
#   身分採可插拔設計:auth_provider('admin'/'line'/'google'/'email'...) + auth_id
# ============================================================
POINTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id             SERIAL PRIMARY KEY,
    auth_provider  TEXT NOT NULL,
    auth_id        TEXT NOT NULL,
    display_name   TEXT,
    email          TEXT,
    password_hash  TEXT,                 -- 僅 Email 帳號使用;社群登入留空
    points_balance INTEGER NOT NULL DEFAULT 0,
    consent_at     TIMESTAMPTZ,          -- 同意個資/免責的時間
    consent_version TEXT,                -- 同意的條文版本
    gender         TEXT,                 -- 性別 'M'/'F'/NULL
    birth_y        INTEGER,              -- 生日(命盤排卦用):年
    birth_m        INTEGER,              -- 月
    birth_d        INTEGER,              -- 日
    birth_h        INTEGER,              -- 時(0-23)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (auth_provider, auth_id)
);

CREATE TABLE IF NOT EXISTS point_ledger (
    id          BIGSERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    delta       INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    ref         TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_point_ledger_user
    ON point_ledger (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS payment_orders (
    id                SERIAL PRIMARY KEY,
    merchant_trade_no TEXT NOT NULL UNIQUE,
    user_id           INTEGER NOT NULL REFERENCES users(id),
    amount            INTEGER NOT NULL,
    points            INTEGER NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at           TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_payment_orders_user
    ON payment_orders (user_id, created_at DESC);
"""


# 卜卦問事紀錄:每次會員在「卜卦問事」成功起卦就寫一筆,供管理介面查詢
QUESTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS divination_questions (
    id            BIGSERIAL PRIMARY KEY,
    user_id       INTEGER REFERENCES users(id),
    user_email    TEXT,                              -- 冗餘存一份,方便查詢顯示
    login_at      TIMESTAMPTZ,                       -- 該次登入時間
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),-- 卜卦時間
    question      TEXT,                              -- 所問之事
    ben_gua       TEXT,                              -- 本卦
    bian_gua      TEXT,                              -- 變卦
    moving_lines  TEXT,                              -- 動爻描述
    yao_vals      TEXT,                              -- 原始六爻 "陰陽,動否" 以 | 連接,供重建完整卦象
    cast_dt       TEXT                               -- 起卦時間字串(重建卦象用)
);
-- 舊資料庫升級:補欄位(idempotent)
ALTER TABLE divination_questions ADD COLUMN IF NOT EXISTS yao_vals TEXT;
ALTER TABLE divination_questions ADD COLUMN IF NOT EXISTS cast_dt  TEXT;
CREATE INDEX IF NOT EXISTS idx_divq_created
    ON divination_questions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_divq_user
    ON divination_questions (user_id, created_at DESC);
"""


# 對舊資料庫升級:users 表若缺 password_hash 欄位則補上(Email 帳號登入用)
MIGRATE_USERS = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'password_hash'
    ) THEN
        ALTER TABLE users ADD COLUMN password_hash TEXT;
    END IF;
END $$;
-- 同意紀錄欄位(舊庫升級;idempotent)
ALTER TABLE users ADD COLUMN IF NOT EXISTS consent_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS consent_version TEXT;
-- 性別 + 生日欄位(命盤排卦用)
ALTER TABLE users ADD COLUMN IF NOT EXISTS gender TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_y INTEGER;
ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_m INTEGER;
ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_d INTEGER;
ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_h INTEGER;
"""


def init_db():
    """應用啟動時呼叫一次，確保 table 存在。失敗會印警告但不中斷。"""
    if not DB_ENABLED:
        log.warning("DB disabled (DB_ENABLED=0)")
        return False
    if not HAS_PSYCOPG:
        log.warning("psycopg2 not installed; DB logging disabled")
        return False
    try:
        with _conn() as c:
            with c.cursor() as cur:
                # 多個 gunicorn worker 會同時跑這段 DDL,直接併發會互相卡死
                # (DeadlockDetected)。先取一把交易層 advisory lock 讓彼此排隊,
                # 交易結束自動釋放;DDL 都是 IF NOT EXISTS,排隊重跑也安全。
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (911002,))
                cur.execute(SCHEMA)
                cur.execute(MIGRATE)
                cur.execute(POINTS_SCHEMA)
                cur.execute(MIGRATE_USERS)
                cur.execute(QUESTIONS_SCHEMA)
        log.info("DB ready: %s@%s/%s",
                 PG_CONF["user"], PG_CONF["host"], PG_CONF["dbname"])
        _ensure_search_indexes()
        return True
    except Exception as e:
        log.warning("DB init failed (%s: %s); logging will be skipped",
                    type(e).__name__, e)
        return False


# 卜卦問事查詢用的加速索引:管理介面以 ILIKE '%關鍵字%' 搜 email / 問題,
# 一般 btree 對前後萬用字元無效,需 pg_trgm 的 GIN 三元組索引才會快。
# 另外放一個交易,且自帶 try:就算缺權限建不了 extension 也只是搜尋慢,
# 不會影響核心建表。
SEARCH_INDEXES = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_divq_email_trgm
    ON divination_questions USING gin (user_email gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_divq_question_trgm
    ON divination_questions USING gin (question gin_trgm_ops);
"""


def _ensure_search_indexes():
    """建立 pg_trgm 與 GIN 索引(加速管理介面的模糊搜尋)。失敗只記 warning。"""
    if not DB_ENABLED or not HAS_PSYCOPG:
        return
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (911003,))
                cur.execute(SEARCH_INDEXES)
    except Exception as e:
        log.warning("DB search-index setup skipped (%s: %s); "
                    "搜尋仍可運作,只是大量資料時較慢", type(e).__name__, e)


def log_divination(client_name, y, m, d, h, gender=None):
    """
    寫入或更新一筆排盤紀錄（UPSERT）。失敗只記 warning，不丟例外。

    比對鍵：(client_name, input_year, input_month, input_day, input_hour)
    若該組合已存在，覆蓋 created_at 為現在時間（記最新一次查詢），
    並在 gender 有提供時更新 gender。

    參數：
      client_name: 姓名（必填；空字串會被擋掉並回傳 False）
      y, m, d, h:  輸入的年月日時（int）
      gender:      'M' / 'F' / None。None 不影響舊值。
    """
    if not DB_ENABLED or not HAS_PSYCOPG:
        return False
    if not client_name or not str(client_name).strip():
        return False
    # 標準化 gender:只接受 'M' 或 'F',其他通通變 None
    g = None
    if gender and str(gender).strip().upper() in ('M', 'F'):
        g = str(gender).strip().upper()
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO divination_logs
                      (client_name, gender, input_year, input_month, input_day, input_hour)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (client_name, input_year, input_month, input_day, input_hour)
                    DO UPDATE SET
                      created_at  = NOW(),
                      query_count = divination_logs.query_count + 1,
                      gender      = COALESCE(EXCLUDED.gender, divination_logs.gender)
                    """,
                    (
                        str(client_name).strip(),
                        g,
                        int(y), int(m), int(d), int(h),
                    ),
                )
        return True
    except Exception as e:
        log.warning("DB log failed (%s: %s); skipped",
                    type(e).__name__, e)
        return False


def list_clients():
    """
    列出所有不同姓名（每人一行），含累計查詢次數與最後查詢時間。
    回傳 list of dict: [{name, total_queries, unique_charts, last_query}, ...]
    失敗回傳 []。
    """
    if not DB_ENABLED or not HAS_PSYCOPG:
        return []
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    SELECT client_name,
                           SUM(query_count)::int AS total_queries,
                           COUNT(*)::int        AS unique_charts,
                           MAX(created_at)      AS last_query
                    FROM divination_logs
                    GROUP BY client_name
                    ORDER BY last_query DESC
                    """
                )
                rows = cur.fetchall()
        return [
            {"name": r[0], "total_queries": r[1],
             "unique_charts": r[2], "last_query": r[3]}
            for r in rows
        ]
    except Exception as e:
        log.warning("DB list_clients failed (%s: %s)", type(e).__name__, e)
        return []


def list_charts_by_name(name):
    """
    列出指定姓名的所有命盤紀錄。
    回傳 list of dict，依 created_at DESC 排序。
    """
    if not DB_ENABLED or not HAS_PSYCOPG:
        return []
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, client_name, gender,
                           input_year, input_month, input_day, input_hour,
                           query_count, created_at
                    FROM divination_logs
                    WHERE client_name = %s
                    ORDER BY created_at DESC
                    """,
                    (str(name).strip(),),
                )
                rows = cur.fetchall()
        return [
            {
                "id": r[0], "name": r[1], "gender": r[2],
                "year": r[3], "month": r[4], "day": r[5], "hour": r[6],
                "query_count": r[7], "created_at": r[8],
            }
            for r in rows
        ]
    except Exception as e:
        log.warning("DB list_charts_by_name failed (%s: %s)", type(e).__name__, e)
        return []


def delete_chart_by_id(chart_id):
    """
    依 id 刪除單筆命盤紀錄。
    回傳:
      (success: bool, deleted_count: int, info: str)
      success: 是否執行成功
      deleted_count: 實際刪除筆數(0 = 該 id 不存在)
      info: 成功時為刪除的紀錄描述,失敗時為錯誤訊息
    """
    if not DB_ENABLED or not HAS_PSYCOPG:
        return (False, 0, "DB 未啟用")
    try:
        cid = int(chart_id)
    except (TypeError, ValueError):
        return (False, 0, f"非法的 id: {chart_id!r}")

    try:
        with _conn() as c:
            with c.cursor() as cur:
                # 先抓出要刪的內容,寫 log 用
                cur.execute(
                    """
                    SELECT client_name, input_year, input_month, input_day, input_hour
                    FROM divination_logs WHERE id = %s
                    """,
                    (cid,),
                )
                row = cur.fetchone()
                if row is None:
                    return (True, 0, f"id={cid} 不存在")
                info = (f"{row[0]} {row[1]}-{row[2]:02d}-{row[3]:02d} "
                        f"{row[4]:02d}時 (id={cid})")
                # 執行刪除
                cur.execute("DELETE FROM divination_logs WHERE id = %s", (cid,))
                deleted = cur.rowcount
        log.info("Deleted chart: %s", info)
        return (True, deleted, info)
    except Exception as e:
        log.warning("DB delete_chart_by_id failed (%s: %s)", type(e).__name__, e)
        return (False, 0, f"{type(e).__name__}: {e}")

def get_chart_gender(name, y, m, d, h):
    """
    依 (姓名, 年月日時) 撈出該命盤的 gender。
    用於管理員流年頁:從 history 點過來時要知道這張盤是男命還是女命。
    回傳 'M' / 'F' / None。失敗或查不到時回傳 None,呼叫端要當作未指定處理。
    """
    if not DB_ENABLED or not HAS_PSYCOPG:
        return None
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    SELECT gender FROM divination_logs
                    WHERE client_name = %s
                      AND input_year = %s AND input_month = %s
                      AND input_day  = %s AND input_hour  = %s
                    LIMIT 1
                    """,
                    (str(name).strip(), int(y), int(m), int(d), int(h)),
                )
                row = cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        log.warning("DB get_chart_gender failed (%s: %s)", type(e).__name__, e)
        return None


# ============================================================
# 點數系統操作
# 注意:點數涉及金流,錯誤「不」靜默吞掉成功——失敗一律回明確的失敗值,
#       讓呼叫端能拒絕出解讀(避免免費贈送)或重試儲值。
# ============================================================
def get_or_create_user(auth_provider, auth_id, display_name=None, email=None):
    """依 (auth_provider, auth_id) 取得或建立會員。回傳 dict 或 None(DB 失敗)。"""
    if not DB_ENABLED or not HAS_PSYCOPG:
        return None
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (auth_provider, auth_id, display_name, email)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (auth_provider, auth_id)
                    DO UPDATE SET
                        display_name = COALESCE(EXCLUDED.display_name, users.display_name),
                        email        = COALESCE(EXCLUDED.email, users.email)
                    RETURNING id, auth_provider, auth_id, display_name, email, points_balance, created_at
                    """,
                    (str(auth_provider), str(auth_id), display_name, email),
                )
                r = cur.fetchone()
        return {
            "id": r[0], "auth_provider": r[1], "auth_id": r[2],
            "display_name": r[3], "email": r[4],
            "points_balance": r[5], "created_at": r[6],
        }
    except Exception as e:
        log.warning("DB get_or_create_user failed (%s: %s)", type(e).__name__, e)
        return None


def create_email_user(email, password_hash, display_name=None, consent_version=None):
    """建立一個 Email 帳號會員(auth_provider='email', auth_id=email)。

    consent_version:若有提供,會一併記錄同意時間(NOW())與條文版本。
    回傳 (status, user_dict):
      ('ok',     dict)  建立成功
      ('exists', None)  這個 email 已經註冊過
      ('error',  None)  DB 失敗
    email 應由呼叫端先正規化(去空白 + 轉小寫)。
    """
    if not DB_ENABLED or not HAS_PSYCOPG:
        return ("error", None)
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (auth_provider, auth_id, display_name, email,
                                       password_hash, consent_at, consent_version)
                    VALUES ('email', %s, %s, %s, %s,
                            CASE WHEN %s::text IS NOT NULL THEN NOW() ELSE NULL END, %s)
                    ON CONFLICT (auth_provider, auth_id) DO NOTHING
                    RETURNING id, auth_provider, auth_id, display_name, email, points_balance, created_at
                    """,
                    (str(email), display_name, str(email), str(password_hash),
                     consent_version, consent_version),
                )
                r = cur.fetchone()
        if r is None:
            return ("exists", None)
        return ("ok", {
            "id": r[0], "auth_provider": r[1], "auth_id": r[2],
            "display_name": r[3], "email": r[4],
            "points_balance": r[5], "created_at": r[6],
        })
    except Exception as e:
        log.warning("DB create_email_user failed (%s: %s)", type(e).__name__, e)
        return ("error", None)


def get_email_user(email):
    """依 email 取得 Email 帳號會員(含 password_hash,供登入驗證)。回傳 dict 或 None。

    email 應由呼叫端先正規化(去空白 + 轉小寫)。
    """
    if not DB_ENABLED or not HAS_PSYCOPG:
        return None
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, auth_provider, auth_id, display_name, email,
                           password_hash, points_balance, created_at
                    FROM users
                    WHERE auth_provider = 'email' AND auth_id = %s
                    """,
                    (str(email),),
                )
                r = cur.fetchone()
        if not r:
            return None
        return {
            "id": r[0], "auth_provider": r[1], "auth_id": r[2],
            "display_name": r[3], "email": r[4], "password_hash": r[5],
            "points_balance": r[6], "created_at": r[7],
        }
    except Exception as e:
        log.warning("DB get_email_user failed (%s: %s)", type(e).__name__, e)
        return None


def list_users(limit=500):
    """列出所有會員(新到舊),供管理介面用。回傳 list of dict。失敗回 []。"""
    if not DB_ENABLED or not HAS_PSYCOPG:
        return []
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, auth_provider, auth_id, display_name, email,
                           points_balance, created_at
                    FROM users
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (int(limit),),
                )
                rows = cur.fetchall()
        return [{
            "id": r[0], "auth_provider": r[1], "auth_id": r[2],
            "display_name": r[3], "email": r[4],
            "points_balance": r[5], "created_at": r[6],
        } for r in rows]
    except Exception as e:
        log.warning("DB list_users failed (%s: %s)", type(e).__name__, e)
        return []


def log_divination_question(user_id, user_email, login_at, question,
                            ben_gua, bian_gua, moving_lines,
                            yao_vals=None, cast_dt=None,
                            dedup_window_seconds=20):
    """寫入一筆卜卦問事紀錄。失敗只記 warning,不影響起卦。

    dedup_window_seconds:若同一會員在這段秒數內已寫過「完全相同」的一筆
    (同問題 + 同卦象),視為重整 / 連點造成的重複,直接跳過不寫。
    回傳 True=有寫入, False=跳過或失敗。
    """
    if not DB_ENABLED or not HAS_PSYCOPG:
        return False
    try:
        with _conn() as c:
            with c.cursor() as cur:
                if dedup_window_seconds:
                    cur.execute(
                        """
                        SELECT 1 FROM divination_questions
                        WHERE user_id      IS NOT DISTINCT FROM %s
                          AND question     IS NOT DISTINCT FROM %s
                          AND ben_gua      IS NOT DISTINCT FROM %s
                          AND bian_gua     IS NOT DISTINCT FROM %s
                          AND moving_lines IS NOT DISTINCT FROM %s
                          AND created_at > NOW() - make_interval(secs => %s)
                        LIMIT 1
                        """,
                        (user_id, question, ben_gua, bian_gua, moving_lines,
                         int(dedup_window_seconds)),
                    )
                    if cur.fetchone():
                        return False  # 短時間內的重複,跳過
                cur.execute(
                    """
                    INSERT INTO divination_questions
                      (user_id, user_email, login_at, question,
                       ben_gua, bian_gua, moving_lines, yao_vals, cast_dt)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (user_id, user_email, login_at, question,
                     ben_gua, bian_gua, moving_lines, yao_vals, cast_dt),
                )
        return True
    except Exception as e:
        log.warning("DB log_divination_question failed (%s: %s)",
                    type(e).__name__, e)
        return False


def list_divination_questions(limit=200, search=None, start=None, end=None):
    """列出卜卦問事紀錄(新到舊)。

    search:email 或問題關鍵字(模糊);start/end:日期字串 YYYY-MM-DD(含當日)。
    回傳 list of dict。
    """
    if not DB_ENABLED or not HAS_PSYCOPG:
        return []
    try:
        conds, params = [], []
        if search:
            conds.append("(user_email ILIKE %s OR question ILIKE %s)")
            like = f"%{search}%"
            params += [like, like]
        if start:
            conds.append("created_at >= %s::date")
            params.append(start)
        if end:
            conds.append("created_at < (%s::date + 1)")  # 含結束當日
            params.append(end)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        params.append(int(limit))
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, user_email, login_at, created_at, question,
                           ben_gua, bian_gua, moving_lines
                    FROM divination_questions
                    {where}
                    ORDER BY created_at DESC LIMIT %s
                    """,
                    params,
                )
                rows = cur.fetchall()
        return [{
            "id": r[0], "user_email": r[1], "login_at": r[2],
            "created_at": r[3], "question": r[4], "ben_gua": r[5],
            "bian_gua": r[6], "moving_lines": r[7],
        } for r in rows]
    except Exception as e:
        log.warning("DB list_divination_questions failed (%s: %s)",
                    type(e).__name__, e)
        return []


def get_divination_question(qid):
    """依 id 取單筆卜卦問事紀錄(含原始六爻/起卦時間,供重建完整卦象)。回傳 dict 或 None。"""
    if not DB_ENABLED or not HAS_PSYCOPG:
        return None
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, user_email, login_at, created_at,
                           question, ben_gua, bian_gua, moving_lines,
                           yao_vals, cast_dt
                    FROM divination_questions WHERE id = %s
                    """,
                    (int(qid),),
                )
                r = cur.fetchone()
        if not r:
            return None
        return {
            "id": r[0], "user_id": r[1], "user_email": r[2], "login_at": r[3],
            "created_at": r[4], "question": r[5], "ben_gua": r[6],
            "bian_gua": r[7], "moving_lines": r[8],
            "yao_vals": r[9], "cast_dt": r[10],
        }
    except Exception as e:
        log.warning("DB get_divination_question failed (%s: %s)",
                    type(e).__name__, e)
        return None


def get_user(user_id):
    """依 id 取得會員(含餘額)。回傳 dict 或 None。"""
    if not DB_ENABLED or not HAS_PSYCOPG:
        return None
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, auth_provider, auth_id, display_name, email,
                           points_balance, created_at,
                           birth_y, birth_m, birth_d, birth_h, gender
                    FROM users WHERE id = %s
                    """,
                    (int(user_id),),
                )
                r = cur.fetchone()
        if not r:
            return None
        return {
            "id": r[0], "auth_provider": r[1], "auth_id": r[2],
            "display_name": r[3], "email": r[4],
            "points_balance": r[5], "created_at": r[6],
            "birth_y": r[7], "birth_m": r[8], "birth_d": r[9], "birth_h": r[10],
            "gender": r[11],
        }
    except Exception as e:
        log.warning("DB get_user failed (%s: %s)", type(e).__name__, e)
        return None


def update_user_profile(user_id, display_name=None, gender=None, birth=None):
    """更新會員資料(完整覆寫修改頁的欄位)。

    display_name / gender:直接覆寫(None = 清空)。
    birth:(y,m,d,h) tuple 或 None(清空生日)。
    回傳 True/False。
    """
    if not DB_ENABLED or not HAS_PSYCOPG:
        return False
    by, bm, bd, bh = birth if birth else (None, None, None, None)
    g = norm_gender(gender)
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """UPDATE users SET display_name=%s, gender=%s,
                           birth_y=%s, birth_m=%s, birth_d=%s, birth_h=%s
                       WHERE id = %s""",
                    (display_name, g, by, bm, bd, bh, int(user_id)),
                )
        return True
    except Exception as e:
        log.warning("DB update_user_profile failed (%s: %s)", type(e).__name__, e)
        return False


def get_password_hash(user_id):
    """依 id 取密碼雜湊(重設密碼 token 驗證用)。回傳字串或 None。"""
    if not DB_ENABLED or not HAS_PSYCOPG:
        return None
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT password_hash FROM users WHERE id = %s", (int(user_id),)
                )
                r = cur.fetchone()
        return r[0] if r else None
    except Exception as e:
        log.warning("DB get_password_hash failed (%s: %s)", type(e).__name__, e)
        return None


def update_password(user_id, new_password_hash):
    """更新會員密碼雜湊。回傳 True/False。"""
    if not DB_ENABLED or not HAS_PSYCOPG:
        return False
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE id = %s",
                    (str(new_password_hash), int(user_id)),
                )
        return True
    except Exception as e:
        log.warning("DB update_password failed (%s: %s)", type(e).__name__, e)
        return False


def delete_user(user_id):
    """刪除會員及其所有資料(點數帳本、卜卦紀錄、付款訂單)。整筆交易內完成。
    回傳 True/False。"""
    if not DB_ENABLED or not HAS_PSYCOPG:
        return False
    try:
        with _conn() as c:
            with c.cursor() as cur:
                uid = int(user_id)
                # 先刪有外鍵指向 users 的子表,最後刪 users 本身
                cur.execute("DELETE FROM divination_questions WHERE user_id = %s", (uid,))
                cur.execute("DELETE FROM point_ledger WHERE user_id = %s", (uid,))
                cur.execute("DELETE FROM payment_orders WHERE user_id = %s", (uid,))
                cur.execute("DELETE FROM users WHERE id = %s", (uid,))
        return True
    except Exception as e:
        log.warning("DB delete_user failed (%s: %s)", type(e).__name__, e)
        return False


def list_user_questions(user_id, limit=100):
    """列出某會員自己的卜卦問事紀錄(新到舊),供「我的紀錄」。回傳 list of dict。"""
    if not DB_ENABLED or not HAS_PSYCOPG:
        return []
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, created_at, question, ben_gua, bian_gua, moving_lines
                    FROM divination_questions
                    WHERE user_id = %s
                    ORDER BY created_at DESC LIMIT %s
                    """,
                    (int(user_id), int(limit)),
                )
                rows = cur.fetchall()
        return [{
            "id": r[0], "created_at": r[1], "question": r[2],
            "ben_gua": r[3], "bian_gua": r[4], "moving_lines": r[5],
        } for r in rows]
    except Exception as e:
        log.warning("DB list_user_questions failed (%s: %s)", type(e).__name__, e)
        return []


def add_points(user_id, points, reason, ref=None):
    """
    加點(儲值成功 / 管理員調整)。餘額與帳本在同一交易內更新。
    回傳 (success: bool, new_balance: int|None)。
    """
    if not DB_ENABLED or not HAS_PSYCOPG:
        return (False, None)
    try:
        n = int(points)
    except (TypeError, ValueError):
        return (False, None)
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "UPDATE users SET points_balance = points_balance + %s "
                    "WHERE id = %s RETURNING points_balance",
                    (n, int(user_id)),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError(f"user {user_id} not found")
                bal = row[0]
                cur.execute(
                    "INSERT INTO point_ledger (user_id, delta, balance_after, reason, ref) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (int(user_id), n, bal, str(reason), ref),
                )
        return (True, bal)
    except Exception as e:
        log.warning("DB add_points failed (%s: %s)", type(e).__name__, e)
        return (False, None)


def try_deduct_point(user_id, n=1, reason="divination", ref=None):
    """
    原子扣點:餘額足夠才扣,否則不動。餘額與帳本同一交易更新。
    回傳 (ok: bool, new_balance: int|None, msg: str)。
      ok=False 且 msg='insufficient' 表示點數不足;
      ok=False 且 msg='error'        表示 DB 失敗(呼叫端應拒絕出解讀)。
    """
    if not DB_ENABLED or not HAS_PSYCOPG:
        return (False, None, "error")
    try:
        n = int(n)
    except (TypeError, ValueError):
        return (False, None, "error")
    try:
        with _conn() as c:
            with c.cursor() as cur:
                # 條件式 UPDATE:餘額不足時 rowcount=0,不會扣成負數
                cur.execute(
                    "UPDATE users SET points_balance = points_balance - %s "
                    "WHERE id = %s AND points_balance >= %s "
                    "RETURNING points_balance",
                    (n, int(user_id), n),
                )
                row = cur.fetchone()
                if row is None:
                    return (False, None, "insufficient")
                bal = row[0]
                cur.execute(
                    "INSERT INTO point_ledger (user_id, delta, balance_after, reason, ref) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (int(user_id), -n, bal, str(reason), ref),
                )
        return (True, bal, "ok")
    except Exception as e:
        log.warning("DB try_deduct_point failed (%s: %s)", type(e).__name__, e)
        return (False, None, "error")


def list_ledger(user_id, limit=50):
    """列出某會員的點數異動紀錄(新到舊)。回傳 list of dict。"""
    if not DB_ENABLED or not HAS_PSYCOPG:
        return []
    try:
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    SELECT delta, balance_after, reason, ref, created_at
                    FROM point_ledger WHERE user_id = %s
                    ORDER BY created_at DESC LIMIT %s
                    """,
                    (int(user_id), int(limit)),
                )
                rows = cur.fetchall()
        return [
            {"delta": r[0], "balance_after": r[1], "reason": r[2],
             "ref": r[3], "created_at": r[4]}
            for r in rows
        ]
    except Exception as e:
        log.warning("DB list_ledger failed (%s: %s)", type(e).__name__, e)
        return []
