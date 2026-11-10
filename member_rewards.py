"""One verified-registration gift, shared safely with legacy Apple promotions."""
import db


def claim_registration(uid, identifier_hash, points=2, retention_days=730):
    with db._conn() as c:
        with c.cursor() as cur:
            cur.execute('SELECT points_balance,email_verified,registration_bonus_eligible FROM users WHERE id=%s FOR UPDATE', (uid,))
            row = cur.fetchone()
            if not row:
                raise ValueError('會員不存在')
            balance, verified, eligible = row
            if not verified or not eligible:
                return False, balance
            cur.execute("SELECT 1 FROM point_ledger WHERE user_id=%s AND reason='welcome_bonus' LIMIT 1", (uid,))
            already = bool(cur.fetchone())
            cur.execute('DELETE FROM promo_redemptions WHERE expires_at <= NOW()')
            cur.execute("""INSERT INTO promo_redemptions(identifier_hash,campaign,expires_at)
                VALUES(%s,'registration_welcome_v1',NOW()+(%s * INTERVAL '1 day'))
                ON CONFLICT DO NOTHING RETURNING 1""", (identifier_hash, retention_days))
            fresh = bool(cur.fetchone())
            granted = fresh and not already
            if granted:
                cur.execute('UPDATE users SET points_balance=points_balance+%s WHERE id=%s RETURNING points_balance', (points, uid))
                balance = cur.fetchone()[0]
                cur.execute("INSERT INTO point_ledger(user_id,delta,balance_after,reason,ref) VALUES(%s,%s,%s,'welcome_bonus','registration_welcome_v1')", (uid, points, balance))
            cur.execute('UPDATE users SET registration_bonus_eligible=FALSE WHERE id=%s', (uid,))
            return granted, balance
