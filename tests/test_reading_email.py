"""Owned saved-reading email: disposable DB, mocked mail, no AI/provider calls."""
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import db


class ReadingEmailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if 'test' not in db.PG_CONF['dbname'].lower():
            raise unittest.SkipTest('disposable database required')
        assert db.init_db()
        import app
        cls.web = app

    def setUp(self):
        _, user = db.create_email_user(f'email-{uuid.uuid4()}@example.invalid', 'hash')
        self.uid = user['id']
        self.email = user['email']
        db.set_email_verified(self.uid)
        self.qid = db.log_divination_question(self.uid, self.email, None,
            '我該留意什麼？', '乾', '坤', '初爻', '1,0|0,0|1,0|0,0|1,0|0,0',
            '2026-11-13 10:00', dedup_window_seconds=0)
        with db._conn() as c:
            with c.cursor() as cur:
                cur.execute("""UPDATE divination_questions SET ai_reading=%s,
                    ai_reading_expires_at=NOW()+INTERVAL '30 days' WHERE id=%s""",
                    ('【盤面解析】\n完整解讀\n【現在的你】\n慢慢來。', self.qid))
        self.client = self.web.app.test_client()
        self.headers = {'Authorization': 'Bearer ' + self.web.make_token(self.uid)}
        self.mail = patch.object(self.web, '_send_mail', return_value=True)
        self.send = self.mail.start()
        self.addCleanup(self.mail.stop)
        self.ai = patch.object(self.web, '_call_claude_reading', side_effect=AssertionError('must reuse saved reading'))
        self.ai.start()
        self.addCleanup(self.ai.stop)

    def tearDown(self):
        db.delete_user(self.uid)

    def post(self, headers=None, **kwargs):
        return self.client.post(f'/api/v1/member/questions/{self.qid}/email',
            headers=self.headers if headers is None else headers, **kwargs)

    def test_saved_email_is_free_and_ignores_client_recipient_and_body(self):
        before = db.get_user(self.uid)['points_balance']
        r = self.post(json={'email': 'attacker@example.invalid', 'reading': 'fake'})
        self.assertEqual(r.status_code, 200)
        args = self.send.call_args.args
        self.assertEqual(args[0], self.email)
        self.assertIn('完整解讀', args[2])
        self.assertIn('我該留意什麼？', args[2])
        self.assertIn('乾 → 坤', args[2])
        self.assertNotIn('fake', args[2])
        self.assertEqual(db.get_user(self.uid)['points_balance'], before)
        self.assertIn('no-store', r.headers['Cache-Control'])
        self.assertEqual(self.post().status_code, 429)
        self.assertEqual(self.send.call_count, 1)

    def test_login_and_ownership_required(self):
        self.assertEqual(self.post(headers={}).status_code, 401)
        with patch.object(self.web, 'current_user', return_value={
                'id': self.uid + 999999, 'email': 'other@example.invalid', 'email_verified': True}):
            self.assertEqual(self.post().status_code, 404)
        self.send.assert_not_called()

    def test_unverified_account_cannot_send(self):
        with db._conn() as c:
            with c.cursor() as cur:
                cur.execute('UPDATE users SET email_verified=FALSE WHERE id=%s', (self.uid,))
        self.assertEqual(self.post().status_code, 403)
        self.send.assert_not_called()

    def test_expired_and_missing_reading_are_not_regenerated(self):
        with db._conn() as c:
            with c.cursor() as cur:
                cur.execute("UPDATE divination_questions SET ai_reading_expires_at=NOW()-INTERVAL '1 second' WHERE id=%s", (self.qid,))
        self.assertEqual(self.post().status_code, 409)
        self.send.assert_not_called()
        self.assertIsNone(db.get_user_question(self.uid, self.qid)['ai_reading'])

    def test_concurrent_attempts_share_persisted_cooldown(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: db.claim_reading_email(self.uid, self.qid), range(4)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 3)

    def test_delivery_failure_keeps_reading_and_balance(self):
        self.send.return_value = False
        self.assertEqual(self.post().status_code, 502)
        self.assertIn('完整解讀', db.get_user_question(self.uid, self.qid)['ai_reading'])
        self.assertEqual(db.get_user(self.uid)['points_balance'], 0)
        self.assertEqual(self.post().status_code, 429)

    def test_reservation_database_failure_does_not_send(self):
        with patch.object(db, 'claim_reading_email', return_value=None):
            self.assertEqual(self.post().status_code, 503)
        self.send.assert_not_called()
