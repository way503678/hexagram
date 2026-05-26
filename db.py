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
