"""Paid yearly forecasts and verified welcome gifts; disposable PostgreSQL only."""
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import db
import fortune_store as store
import member_rewards


class FortuneUnlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if 'test' not in db.PG_CONF['dbname'].lower():
            raise unittest.SkipTest('requires disposable test database')
        if not db.init_db():
            raise RuntimeError('test database unavailable')
        import app
        cls.web = app

    def setUp(self):
        self.email = f'fortune-{uuid.uuid4()}@example.invalid'
        status, user = db.create_email_user(self.email, 'hash')
        self.assertEqual(status, 'ok')
        self.uid = user['id']
        self.inputs, self.key = store.normalize(dict(y=1990, m=1, d=2, h=3, gender='F', year=2026))
        self.headers = {'Authorization': 'Bearer ' + self.web.make_token(self.uid)}
        self.client = self.web.app.test_client()

    def tearDown(self):
        db.delete_user(self.uid)

    def fund(self, amount=2):
        self.assertTrue(db.add_points(self.uid, amount, 'test_topup')[0])

    def reserve(self):
        return store.reserve(self.uid, self.key, self.inputs, 2)

    def complete(self, result, token):
        return store.save(self.uid, result['fortune_id'], token, {'流年': {'西元': 2026}}, 'prompt', '完整 AI 解讀', 'test-model')

    def test_concurrent_reservation_deducts_only_once(self):
        self.fund()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.reserve(), range(4)))
        self.assertEqual(sum(r[0] == 'reserved' for r in results), 1)
        self.assertEqual(sum(r[0] == 'in_progress' for r in results), 3)
        self.assertEqual(db.get_user(self.uid)['points_balance'], 0)
        with db._conn() as c:
            with c.cursor() as cur:
                cur.execute("SELECT count(*) FROM point_ledger WHERE user_id=%s AND reason='fortune'", (self.uid,))
                self.assertEqual(cur.fetchone()[0], 1)

    def test_saved_revisit_and_expired_regeneration_are_free_at_zero_balance(self):
        self.fund()
        _, result, token = self.reserve()
        self.complete(result, token)
        status, saved, token = self.reserve()
        self.assertEqual(status, 'existing')
        self.assertEqual(saved['reading'], '完整 AI 解讀')
        self.assertEqual(saved['balance'], 0)
        with db._conn() as c:
            with c.cursor() as cur:
                cur.execute("UPDATE fortune_readings SET expires_at=NOW()-INTERVAL '1 second' WHERE user_id=%s", (self.uid,))
        store.cleanup()
        access = store.access(self.uid, self.key, 2)
        self.assertTrue(access['unlocked'])
        self.assertFalse(access['ready'])
        self.assertIsNone(access['reading'])
        self.assertIsNone(access['prompt'])
        self.assertIsNone(access['fortune'])
        status, free, token = self.reserve()
        self.assertEqual(status, 'reserved')
        self.assertFalse(free['charged'])
        self.complete(free, token)
        self.assertEqual(db.get_user(self.uid)['points_balance'], 0)

    def test_refund_is_once_and_old_token_cannot_save_or_refund_retry(self):
        self.fund()
        _, result, token = self.reserve()
        fid = result['fortune_id']
        self.assertEqual(store.refund(self.uid, fid, token), 2)
        self.assertEqual(store.refund(self.uid, fid, token), 2)
        _, retry, new_token = self.reserve()
        with self.assertRaises(RuntimeError):
            self.complete(result, token)
        self.assertEqual(store.refund(self.uid, fid, token), 0)
        self.complete(retry, new_token)

    def test_stale_request_refunded_on_member_refresh(self):
        self.fund()
        self.reserve()
        with db._conn() as c:
            with c.cursor() as cur:
                cur.execute("UPDATE fortune_readings SET generation_started_at=NOW()-INTERVAL '1 hour' WHERE user_id=%s", (self.uid,))
        self.assertEqual(db.get_user(self.uid)['points_balance'], 2)
        self.assertEqual(db.get_user(self.uid)['points_balance'], 2)
        self.assertFalse(store.access(self.uid, self.key, 2)['unlocked'])

    def test_birth_gender_and_year_are_distinct_and_normalized(self):
        _, same = store.normalize({**self.inputs, 'y': '1990', 'gender': ' f '})
        self.assertEqual(same, self.key)
        for field, value in [('year', 2027), ('h', 4), ('gender', 'M')]:
            _, other = store.normalize({**self.inputs, field: value})
            self.assertNotEqual(other, self.key)
        for invalid in [dict(y=1990, m=2, d=30, h=3), {**self.inputs, 'gender': 'invalid'}, [], {**self.inputs, 'h': 3.5}]:
            with self.assertRaises(ValueError):
                store.normalize(invalid)

    def test_unlock_api_persists_package_legacy_prompt_and_reading_do_not_charge_again(self):
        self.fund()
        with patch.object(self.web, '_call_claude_reading', return_value='AI 已保存') as ai:
            first = self.client.post('/api/v1/fortune/unlock', json=self.inputs, headers=self.headers)
            self.assertEqual(first.status_code, 200, first.get_json())
            body = first.get_json()
            self.assertTrue(body['charged'])
            self.assertEqual(body['balance'], 0)
            self.assertEqual(len(body['fortune']['流月']), 12)
            again = self.client.post('/api/v1/fortune/prompt', json=self.inputs, headers=self.headers)
            self.assertEqual(again.status_code, 200)
            self.assertFalse(again.get_json()['charged'])
            reading = self.client.post('/api/v1/fortune/reading', json=self.inputs, headers=self.headers)
            self.assertEqual(reading.status_code, 200)
            self.assertIn('AI 已保存', reading.get_data(as_text=True))
            self.assertEqual(ai.call_count, 1)
        access = self.client.get('/api/v1/fortune/access', query_string=self.inputs, headers=self.headers)
        self.assertEqual(access.get_json()['reading'], 'AI 已保存')
        self.assertIn('no-store', access.headers['Cache-Control'])
        self.assertEqual(self.client.get('/api/v1/fortune', query_string=self.inputs).status_code, 401)
        other = self.client.get('/api/v1/fortune', query_string={**self.inputs, 'year': 2027}, headers=self.headers)
        self.assertEqual(other.status_code, 402)
        self.assertEqual(self.client.get('/api/v1/fortune', query_string=self.inputs, headers=self.headers).status_code, 200)

    def test_api_insufficient_and_provider_or_save_failure_expose_no_content(self):
        with patch.object(self.web, '_call_claude_reading') as ai:
            r = self.client.post('/api/v1/fortune/unlock', json=self.inputs, headers=self.headers)
            self.assertEqual(r.status_code, 402)
            ai.assert_not_called()
        self.fund()
        for target in ('_call_claude_reading', 'save'):
            owner = self.web if target.startswith('_') else store
            with patch.object(self.web, '_call_claude_reading', return_value='secret AI'):
                with patch.object(owner, target, side_effect=RuntimeError('simulated failure')):
                    r = self.client.post('/api/v1/fortune/unlock', json=self.inputs, headers=self.headers)
            self.assertEqual(r.status_code, 502)
            self.assertNotIn('reading', r.get_json())
            self.assertEqual(db.get_user(self.uid)['points_balance'], 2)
            self.assertFalse(store.access(self.uid, self.key, 2)['unlocked'])

    def test_committed_result_survives_lost_database_acknowledgement(self):
        self.fund()
        original = store.save
        def save_then_disconnect(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('commit acknowledgement lost')
        with patch.object(store, 'save', side_effect=save_then_disconnect):
            with patch.object(self.web, '_call_claude_reading', return_value='saved before disconnect'):
                response = self.client.post('/api/v1/fortune/unlock', json=self.inputs, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['reading'], 'saved before disconnect')
        self.assertEqual(db.get_user(self.uid)['points_balance'], 0)

    def test_delete_user_removes_forecast_birth_prompt_reading_and_entitlement(self):
        self.fund()
        _, result, token = self.reserve()
        self.complete(result, token)
        self.assertTrue(db.delete_user(self.uid))
        with db._conn() as c:
            with c.cursor() as cur:
                cur.execute('SELECT count(*) FROM fortune_readings WHERE user_id=%s', (self.uid,))
                self.assertEqual(cur.fetchone()[0], 0)

    def test_gift_requires_verification_is_once_and_blocks_legacy_duplicate(self):
        identifier = uuid.uuid4().hex
        self.assertEqual(member_rewards.claim_registration(self.uid, identifier), (False, 0))
        db.set_email_verified(self.uid)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: member_rewards.claim_registration(self.uid, identifier), range(4)))
        self.assertEqual(sum(r[0] for r in results), 1)
        self.assertEqual(db.get_user(self.uid)['points_balance'], 2)
        legacy = db.claim_promotion(self.uid, uuid.uuid4().hex, 'legacy', 2, 730, once_per_user=True)
        self.assertFalse(legacy[0])
        self.assertEqual(legacy[1], 2)

    def test_legacy_gift_first_does_not_grant_registration_twice(self):
        db.set_email_verified(self.uid)
        self.assertTrue(db.claim_promotion(self.uid, uuid.uuid4().hex, 'legacy', 2, 730, once_per_user=True)[0])
        self.assertEqual(member_rewards.claim_registration(self.uid, uuid.uuid4().hex), (False, 2))

    def test_verify_link_and_me_grant_once_and_recreated_email_cannot_claim(self):
        link = '/verify?token=' + self.web.make_verify_token(self.uid)
        self.assertEqual(self.client.get(link).status_code, 200)
        self.assertEqual(self.client.get(link).status_code, 200)
        me = self.client.get('/api/v1/auth/me', headers=self.headers).get_json()['user']
        self.assertEqual(me['points_balance'], 2)
        self.assertFalse(me['registration_bonus_eligible'])
        db.delete_user(self.uid)
        status, user = db.create_email_user(self.email, 'hash')
        self.assertEqual(status, 'ok')
        self.uid = user['id']
        db.set_email_verified(self.uid)
        self.web._claim_registration_bonus(db.get_user(self.uid))
        self.assertEqual(db.get_user(self.uid)['points_balance'], 0)

    def test_existing_users_are_not_backfilled_gifts(self):
        with db._conn() as c:
            with c.cursor() as cur:
                cur.execute('UPDATE users SET registration_bonus_eligible=FALSE,email_verified=TRUE WHERE id=%s', (self.uid,))
        self.web._claim_registration_bonus(db.get_user(self.uid))
        self.assertEqual(db.get_user(self.uid)['points_balance'], 0)

    def test_different_member_cannot_read_or_finish_purchase(self):
        self.fund()
        _, result, token = self.reserve()
        _, second = db.create_email_user(f'other-{uuid.uuid4()}@example.invalid', 'hash')
        try:
            other = second['id']
            self.assertFalse(store.access(other, self.key, 2)['unlocked'])
            with self.assertRaises(RuntimeError):
                store.save(other, result['fortune_id'], token, {'x': 1}, 'p', 'secret', 'test')
            store.refund(other, result['fortune_id'], token)
            self.complete(result, token)
        finally:
            db.delete_user(second['id'])
