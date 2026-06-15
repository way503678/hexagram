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
from datetime import datetime
from contextlib import contextmanager

try:
    import psycopg2
    from psycopg2 import sql
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
}

# 是否啟用 DB（預設啟用）；想暫時關掉，設環境變數 DB_ENABLED=0
DB_ENABLED = os.environ.get("DB_ENABLED", "1") == "1"


@contextmanager
def _conn():
    """連線 context manager，例外會傳出來給呼叫端決定要不要忽略"""
    if not HAS_PSYCOPG:
        raise RuntimeError("psycopg2 not installed")
    c = psycopg2.connect(**PG_CONF, connect_timeout=5)
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


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
    points_balance INTEGER NOT NULL DEFAULT 0,
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
                cur.execute(SCHEMA)
                cur.execute(MIGRATE)
                cur.execute(POINTS_SCHEMA)
        log.info("DB ready: %s@%s/%s",
                 PG_CONF["user"], PG_CONF["host"], PG_CONF["dbname"])
        return True
    except Exception as e:
        log.warning("DB init failed (%s: %s); logging will be skipped",
                    type(e).__name__, e)
        return False


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
                           points_balance, created_at
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
        }
    except Exception as e:
        log.warning("DB get_user failed (%s: %s)", type(e).__name__, e)
        return None


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
