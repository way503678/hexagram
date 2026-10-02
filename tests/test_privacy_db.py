"""Privacy deletion and promotion-ledger integration tests.

Run only against a disposable PostgreSQL database, for example:
  PG_DATABASE=hexagram_privacy_test python -m unittest tests.test_privacy_db
"""
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

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
                    "growth_reflections", "ai_readings", "divination_questions", "point_ledger",
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
                    """INSERT INTO divination_questions (user_id, user_email, question)
                       VALUES (%s, %s, 'q') RETURNING id""",
                    (self.uid, self.email),
                )
                qid = cur.fetchone()[0]
                cur.execute(
                    """INSERT INTO ai_readings
                         (user_id, question_id, reading, model, expires_at)
                       VALUES (%s, %s, 'reading', 'test-model', NOW() + INTERVAL '30 days')""",
                    (self.uid, qid),
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
                    "users", "growth_reflections", "ai_readings", "divination_questions",
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

    def test_ai_reading_is_saved_and_expired_text_is_deleted(self):
        qid = db.log_divination_question(
            self.uid, self.email, None, "Will this be saved?",
            "乾", "坤", "初爻", "1,0|0,0|1,0|0,0|1,0|0,0",
            "2026-09-30 10:00", dedup_window_seconds=0,
        )
        self.assertIsInstance(qid, int)
        self.assertEqual(db.add_points(self.uid, 2, "test_topup"), (True, 2))
        status, balance, reading, expires_at, token = db.reserve_ai_reading(
            self.uid, qid, cost=1,
        )
        self.assertEqual((status, balance, reading, expires_at),
                         ("charged", 1, None, None))
        self.assertTrue(token)
        expires_at = db.save_ai_reading(
            self.uid, qid, "完整 AI 解讀", token,
            model="test-model", retention_days=30,
        )
        self.assertIsNotNone(expires_at)
        rows = db.list_user_questions(self.uid)
        saved = next(r for r in rows if r["id"] == qid)
        self.assertEqual(saved["ai_reading"], "完整 AI 解讀")
        self.assertEqual(saved["ai_model"], "test-model")

        # 同一筆再查看／再按 AI 必須直接拿既有內容，不再扣果實。
        status, balance, reading, existing_expires, existing_token = db.reserve_ai_reading(
            self.uid, qid, cost=1,
        )
        self.assertEqual(status, "existing")
        self.assertEqual(balance, 1)
        self.assertEqual(reading, "完整 AI 解讀")
        self.assertEqual(existing_expires, expires_at)
        self.assertIsNone(existing_token)

        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE divination_questions
                       SET ai_reading_expires_at = NOW() - INTERVAL '1 second'
                       WHERE id = %s""",
                    (qid,),
                )
        rows = db.list_user_questions(self.uid)
        expired = next(r for r in rows if r["id"] == qid)
        self.assertIsNone(expired["ai_reading"])
        self.assertIsNone(expired["ai_reading_expires_at"])

    def test_prompt_charge_and_save_are_atomic_and_idempotent(self):
        qid = db.log_divination_question(
            self.uid, self.email, None, "Prompt test",
            "乾", "坤", "初爻", "1,0|0,0|1,0|0,0|1,0|0,0",
            "2026-10-02 10:00", chart_payload={"schema_version": 2},
            dedup_window_seconds=0,
        )
        self.assertEqual(
            db.find_matching_divination_question(
                self.uid, "Prompt test",
                "1,0|0,0|1,0|0,0|1,0|0,0", "2026-10-02 10:00",
            ),
            qid,
        )
        self.assertEqual(db.add_points(self.uid, 1, "test_topup"), (True, 1))

        first = db.get_or_charge_prompt(self.uid, qid, "secret prompt", 30)
        self.assertEqual(first[0], "charged")
        self.assertEqual(first[1], 0)
        self.assertEqual(first[2], "secret prompt")

        second = db.get_or_charge_prompt(self.uid, qid, "different text", 30)
        self.assertEqual(second[0], "existing")
        self.assertEqual(second[1], 0)
        self.assertEqual(second[2], "secret prompt")

        qid2 = db.log_divination_question(
            self.uid, self.email, None, "No fruit",
            "乾", None, "無動爻", "1,0|1,0|1,0|1,0|1,0|1,0",
            "2026-10-02 11:00", chart_payload={"schema_version": 2},
            dedup_window_seconds=0,
        )
        denied = db.get_or_charge_prompt(self.uid, qid2, "must not leak", 30)
        self.assertEqual(denied[:3], ("insufficient", 0, None))
        self.assertIsNone(db.get_user_question(self.uid, qid2)["prompt_text"])

        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT count(*) FROM point_ledger
                       WHERE user_id = %s AND reason = 'prompt'""",
                    (self.uid,),
                )
                self.assertEqual(cur.fetchone()[0], 1)

        # 歷史查詢只是讀取，不會新增任何扣點帳本。
        before = len(db.list_ledger(self.uid, limit=100))
        detail = db.get_user_question(self.uid, qid)
        self.assertEqual(detail["prompt_text"], "secret prompt")
        self.assertEqual(len(db.list_ledger(self.uid, limit=100)), before)

        other_email = f"other-{uuid.uuid4()}@example.invalid"
        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO users
                         (auth_provider, auth_id, email, password_hash,
                          email_verified, points_balance)
                       VALUES ('email', %s, %s, 'hash', TRUE, 2)
                       RETURNING id""",
                    (other_email, other_email),
                )
                other_uid = cur.fetchone()[0]
        try:
            self.assertIsNone(db.get_user_question(other_uid, qid))
            denied_other = db.get_or_charge_prompt(
                other_uid, qid, "cross-account leak", 30,
            )
            self.assertEqual(denied_other, ("not_found", None, None, None))
            self.assertEqual(db.get_user(other_uid)["points_balance"], 2)
        finally:
            db.delete_user(other_uid)

    def test_concurrent_paid_requests_only_charge_once(self):
        qid = db.log_divination_question(
            self.uid, self.email, None, "Concurrent test",
            "乾", "坤", "初爻", "1,0|0,0|1,0|0,0|1,0|0,0",
            "2026-10-02 12:00", chart_payload={"schema_version": 2},
            dedup_window_seconds=0,
        )
        self.assertEqual(db.add_points(self.uid, 3, "test_topup"), (True, 3))

        with ThreadPoolExecutor(max_workers=2) as pool:
            prompt_results = list(pool.map(
                lambda _: db.get_or_charge_prompt(
                    self.uid, qid, "same prompt", retention_days=30,
                ),
                range(2),
            ))
        self.assertEqual(sorted(r[0] for r in prompt_results), ["charged", "existing"])
        self.assertEqual(db.get_user(self.uid)["points_balance"], 2)

        with ThreadPoolExecutor(max_workers=2) as pool:
            reading_results = list(pool.map(
                lambda _: db.reserve_ai_reading(self.uid, qid, cost=1),
                range(2),
            ))
        self.assertEqual(sorted(r[0] for r in reading_results), ["charged", "in_progress"])
        self.assertEqual(db.get_user(self.uid)["points_balance"], 1)
        charged_result = next(r for r in reading_results if r[0] == "charged")
        self.assertIsNone(db.save_ai_reading(
            self.uid, qid, "must not save", "wrong-token", model="test",
        ))
        self.assertEqual(
            db.refund_ai_reading(self.uid, qid, "wrong-token", 1),
            (False, None),
        )
        self.assertEqual(db.get_user(self.uid)["points_balance"], 1)
        refunded, balance = db.refund_ai_reading(
            self.uid, qid, charged_result[4], 1,
            ref="concurrent_test_cleanup",
        )
        self.assertEqual((refunded, balance), (True, 2))

        status, balance, _reading, _expires, stale_token = db.reserve_ai_reading(
            self.uid, qid, cost=1,
        )
        self.assertEqual((status, balance), ("charged", 1))
        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE divination_questions
                       SET ai_generation_started_at = NOW() - INTERVAL '1 day'
                       WHERE id = %s""",
                    (qid,),
                )
        self.assertEqual(db.get_user(self.uid)["points_balance"], 2)
        self.assertEqual(
            db.refund_ai_reading(self.uid, qid, stale_token, 1),
            (False, None),
        )

    def test_init_db_skips_legacy_backfill_that_would_collide(self):
        self.assertTrue(db.log_divination(
            "Privacy Test", 1990, 1, 2, 3, "F", self.uid,
        ))
        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO divination_logs
                         (client_name, gender, input_year, input_month, input_day, input_hour)
                       VALUES ('Privacy Test', 'F', 1990, 1, 2, 3)
                       RETURNING id"""
                )
                legacy_id = cur.fetchone()[0]
        self.assertTrue(db.init_db())
        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM divination_logs WHERE id = %s", (legacy_id,))
                self.assertIsNone(cur.fetchone()[0])

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
