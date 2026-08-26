"""Privacy deletion and promotion-ledger integration tests.

Run only against a disposable PostgreSQL database, for example:
  PG_DATABASE=hexagram_privacy_test python -m unittest tests.test_privacy_db
"""
import os
import unittest
import uuid

import db


class PrivacyDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "test" not in db.PG_CONF["dbname"].lower():
            raise unittest.SkipTest("requires a disposable database with 'test' in its name")
        if not db.init_db():
            raise RuntimeError("could not initialize disposable test database")

    def setUp(self):
        self.email = f"privacy-{uuid.uuid4()}@example.invalid"
        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO users
                         (auth_provider, auth_id, email, password_hash, email_verified,
                          display_name, gender, birth_y, birth_m, birth_d, birth_h)
                       VALUES ('email', %s, %s, 'hash', TRUE,
                               'Privacy Test', 'F', 1990, 1, 2, 3)
                       RETURNING id""",
                    (self.email, self.email),
                )
                self.uid = cur.fetchone()[0]

    def tearDown(self):
        with db._conn() as conn:
            with conn.cursor() as cur:
                for table in (
                    "growth_reflections", "divination_questions", "point_ledger",
                    "payment_orders", "divination_logs",
                ):
                    cur.execute(f"DELETE FROM {table} WHERE user_id = %s", (self.uid,))
                cur.execute("DELETE FROM users WHERE id = %s", (self.uid,))

    def test_delete_user_removes_every_linked_personal_record(self):
        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO growth_reflections (user_id, question, feeling, goal) VALUES (%s, 'q', 'f', 'g')",
                    (self.uid,),
                )
                cur.execute(
                    "INSERT INTO divination_questions (user_id, user_email, question) VALUES (%s, %s, 'q')",
                    (self.uid, self.email),
                )
                cur.execute(
                    "INSERT INTO point_ledger (user_id, delta, balance_after, reason) VALUES (%s, 1, 1, 'test')",
                    (self.uid,),
                )
                cur.execute(
                    """INSERT INTO payment_orders
                         (merchant_trade_no, user_id, amount, points)
                       VALUES (%s, %s, 1, 1)""",
                    (uuid.uuid4().hex, self.uid),
                )
        self.assertTrue(db.log_divination("Privacy Test", 1990, 1, 2, 3, "F", self.uid))
        # 模擬升級前沒有 user_id 的舊命盤；精確吻合本會員時也必須刪除。
        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO divination_logs
                         (client_name, gender, input_year, input_month, input_day, input_hour)
                       VALUES ('Privacy Test', 'F', 1990, 1, 2, 3)"""
                )
        self.assertTrue(db.delete_user(self.uid))

        with db._conn() as conn:
            with conn.cursor() as cur:
                for table in (
                    "users", "growth_reflections", "divination_questions",
                    "point_ledger", "payment_orders", "divination_logs",
                ):
                    cur.execute(f"SELECT count(*) FROM {table} WHERE " +
                                ("id = %s" if table == "users" else "user_id = %s"),
                                (self.uid,))
                    self.assertEqual(cur.fetchone()[0], 0, table)
                cur.execute(
                    """SELECT count(*) FROM divination_logs
                       WHERE client_name = 'Privacy Test'
                         AND input_year = 1990 AND input_month = 1
                         AND input_day = 2 AND input_hour = 3"""
                )
                self.assertEqual(cur.fetchone()[0], 0, "legacy divination_logs")

    def test_promotion_is_idempotent_and_has_no_user_link(self):
        digest = uuid.uuid4().hex
        campaign = "welcome_test"
        claimed, balance, reason = db.claim_promotion(self.uid, digest, campaign, 3, 30)
        self.assertEqual((claimed, balance, reason), (True, 3, "claimed"))
        claimed2, balance2, reason2 = db.claim_promotion(self.uid, digest, campaign, 3, 30)
        self.assertEqual((claimed2, balance2, reason2), (False, 3, "already_redeemed"))

        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT column_name FROM information_schema.columns
                       WHERE table_name = 'promo_redemptions'"""
                )
                columns = {row[0] for row in cur.fetchall()}
                self.assertFalse(columns & {"user_id", "email", "birth_y", "question"})
                cur.execute(
                    "DELETE FROM promo_redemptions WHERE identifier_hash = %s AND campaign = %s",
                    (digest, campaign),
                )


if __name__ == "__main__":
    unittest.main()
