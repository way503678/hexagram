"""Durable yearly-forecast entitlements and atomic two-fruit reservations."""
import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import datetime

from psycopg2.extras import RealDictCursor, Json
import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS fortune_readings (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    input_key TEXT NOT NULL,
    input_data JSONB NOT NULL,
    forecast JSONB,
    prompt TEXT,
    reading TEXT,
    model TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    unlocked_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    generation_started_at TIMESTAMPTZ,
    generation_token TEXT,
    reserved_cost INTEGER NOT NULL DEFAULT 0 CHECK (reserved_cost >= 0),
    UNIQUE(user_id, input_key)
);
CREATE INDEX IF NOT EXISTS idx_fortune_expiry ON fortune_readings(expires_at)
    WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fortune_pending ON fortune_readings(user_id, generation_started_at)
    WHERE generation_token IS NOT NULL;
"""


def normalize(data):
    try:
        if not isinstance(data, Mapping):
            raise ValueError()
        values = {k: int(str(data[k]).strip()) for k in ('y', 'm', 'd', 'h')}
        values['year'] = int(str(data.get('year') or datetime.now().year).strip())
        if not 1900 <= values['y'] <= 2100 or not 1900 <= values['year'] <= 2100:
            raise ValueError()
        datetime(values['y'], values['m'], values['d'], values['h'])
        raw_gender = str(data.get('gender') or '').strip().upper()
        if raw_gender not in ('', 'M', 'F'):
            raise ValueError()
        values['gender'] = raw_gender or None
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError('請提供有效的出生年月日時、性別及目標年份（1900–2100）') from None
    key = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    return values, key


def _user(cur, uid):
    cur.execute('SELECT points_balance FROM users WHERE id=%s FOR UPDATE', (uid,))
    row = cur.fetchone()
    if not row:
        raise ValueError('會員不存在')
    return row['points_balance']


def _credit(cur, uid, amount, ref):
    cur.execute('UPDATE users SET points_balance=points_balance+%s WHERE id=%s RETURNING points_balance', (amount, uid))
    balance = cur.fetchone()['points_balance']
    if amount:
        cur.execute("INSERT INTO point_ledger(user_id,delta,balance_after,reason,ref) VALUES (%s,%s,%s,'refund',%s)", (uid, amount, balance, ref))
    return balance


def _recover(cur, uid):
    cur.execute("""SELECT id,reserved_cost FROM fortune_readings WHERE user_id=%s
        AND generation_token IS NOT NULL
        AND generation_started_at < NOW()-(%s * INTERVAL '1 second') FOR UPDATE""", (uid, db.AI_RESERVATION_TTL_SECONDS))
    for row in cur.fetchall():
        _credit(cur, uid, row['reserved_cost'], f"fortune_stale:{row['id']}")
        cur.execute('UPDATE fortune_readings SET generation_token=NULL,generation_started_at=NULL,reserved_cost=0 WHERE id=%s', (row['id'],))


def refund_stale_for_user(uid):
    with db._conn() as c:
        with c.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""SELECT 1 FROM fortune_readings WHERE user_id=%s AND generation_token IS NOT NULL
                AND generation_started_at < NOW()-(%s * INTERVAL '1 second') LIMIT 1""", (uid, db.AI_RESERVATION_TTL_SECONDS))
            if not cur.fetchone():
                return
            _user(cur, uid)
            _recover(cur, uid)


def cleanup():
    with db._conn() as c:
        with c.cursor() as cur:
            cur.execute("""UPDATE fortune_readings SET forecast=NULL,prompt=NULL,reading=NULL,model=NULL,expires_at=NULL
                WHERE expires_at <= NOW()""")


def _expire(cur, uid):
    cur.execute("""UPDATE fortune_readings SET forecast=NULL,prompt=NULL,reading=NULL,model=NULL,expires_at=NULL
        WHERE user_id=%s AND expires_at <= NOW()""", (uid,))


def _public(row, balance, cost):
    return dict(cost=cost, balance=balance, unlocked=bool(row and row['unlocked_at']),
                ready=bool(row and row['forecast'] and row['reading']),
                pending=bool(row and row['generation_token']),
                fortune_id=row['id'] if row else None,
                fortune=row['forecast'] if row else None,
                reading=row['reading'] if row else None,
                prompt=row['prompt'] if row else None,
                saved_until=row['expires_at'].isoformat() if row and row['expires_at'] else None,
                charged=False)


def access(uid, key, cost):
    with db._conn() as c:
        with c.cursor(cursor_factory=RealDictCursor) as cur:
            _user(cur, uid)
            _recover(cur, uid)
            _expire(cur, uid)
            balance = _user(cur, uid)
            cur.execute('SELECT * FROM fortune_readings WHERE user_id=%s AND input_key=%s', (uid, key))
            return _public(cur.fetchone(), balance, cost)


def reserve(uid, key, inputs, cost):
    with db._conn() as c:
        with c.cursor(cursor_factory=RealDictCursor) as cur:
            _user(cur, uid)
            _recover(cur, uid)
            _expire(cur, uid)
            balance = _user(cur, uid)
            cur.execute('INSERT INTO fortune_readings(user_id,input_key,input_data) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING', (uid, key, Json(inputs)))
            cur.execute('SELECT * FROM fortune_readings WHERE user_id=%s AND input_key=%s FOR UPDATE', (uid, key))
            row = cur.fetchone()
            public = _public(row, balance, cost)
            if public['ready']:
                return 'existing', public, None
            if public['pending']:
                return 'in_progress', public, None
            amount = 0 if public['unlocked'] else cost
            if balance < amount:
                return 'insufficient', public, None
            if amount:
                cur.execute('UPDATE users SET points_balance=points_balance-%s WHERE id=%s RETURNING points_balance', (amount, uid))
                balance = cur.fetchone()['points_balance']
                cur.execute("INSERT INTO point_ledger(user_id,delta,balance_after,reason,ref) VALUES(%s,%s,%s,'fortune',%s)", (uid, -amount, balance, f"fortune:{row['id']}"))
            token = uuid.uuid4().hex
            cur.execute('UPDATE fortune_readings SET generation_token=%s,generation_started_at=NOW(),reserved_cost=%s WHERE id=%s', (token, amount, row['id']))
            public.update(balance=balance, charged=bool(amount), pending=True)
            return 'reserved', public, token


def save(uid, fid, token, forecast, prompt, reading, model):
    if not reading or not reading.strip():
        raise ValueError('AI 未傳回解讀')
    with db._conn() as c:
        with c.cursor(cursor_factory=RealDictCursor) as cur:
            _user(cur, uid)
            cur.execute("""UPDATE fortune_readings SET forecast=%s,prompt=%s,reading=%s,model=%s,
                unlocked_at=COALESCE(unlocked_at,NOW()),expires_at=NOW()+INTERVAL '30 days',
                generation_token=NULL,generation_started_at=NULL,reserved_cost=0
                WHERE user_id=%s AND id=%s AND generation_token=%s RETURNING expires_at""",
                (Json(forecast), prompt, reading, model, uid, fid, token))
            row = cur.fetchone()
            if not row:
                raise RuntimeError('流年預約已失效')
            return row['expires_at'].isoformat()


def refund(uid, fid, token):
    with db._conn() as c:
        with c.cursor(cursor_factory=RealDictCursor) as cur:
            balance = _user(cur, uid)
            cur.execute('SELECT reserved_cost FROM fortune_readings WHERE user_id=%s AND id=%s AND generation_token=%s FOR UPDATE', (uid, fid, token))
            row = cur.fetchone()
            if row:
                balance = _credit(cur, uid, row['reserved_cost'], f'fortune_failed:{fid}')
                cur.execute('UPDATE fortune_readings SET generation_token=NULL,generation_started_at=NULL,reserved_cost=0 WHERE id=%s', (fid,))
            return balance
