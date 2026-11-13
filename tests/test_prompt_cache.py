"""Cache boundaries and usage accounting; no provider calls or member content logs."""
import json
import runpy
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import prompt_cache


class PromptCacheTests(unittest.TestCase):
    def test_ttl_is_explicit_validated_and_preserves_instruction_bytes(self):
        original = '固定規則\r\n  不能刪減\n'
        for ttl in ('5m', '1h'):
            with patch.dict(os.environ, {'AI_PROMPT_CACHE_TTL': ttl}):
                block = prompt_cache.system_blocks(original)[0]
                self.assertEqual(block['text'], original)
                self.assertEqual(block['cache_control'], {'type': 'ephemeral', 'ttl': ttl})
        with patch.dict(os.environ, {'AI_PROMPT_CACHE_TTL': 'never'}):
            with self.assertRaises(ValueError):
                prompt_cache.cache_ttl()

    def test_low_frequency_default_and_off_keep_rules_without_cache_marker(self):
        with patch.dict(os.environ):
            os.environ.pop('AI_PROMPT_CACHE_TTL', None)
            self.assertEqual(prompt_cache.cache_ttl(), 'off')
            self.assertEqual(prompt_cache.system_blocks('規則\r\n'), [{'type': 'text', 'text': '規則\r\n'}])
        self.assertEqual(prompt_cache.system_blocks('規則', ttl='off'), [{'type': 'text', 'text': '規則'}])

    def test_disabled_diagnostic_cannot_create_provider_client(self):
        with patch.dict(os.environ, {'AI_PROMPT_CACHE_TTL': 'off'}), patch('anthropic.Anthropic') as provider:
            with self.assertRaisesRegex(SystemExit, 'disabled'):
                runpy.run_path('scripts/verify_prompt_cache.py', run_name='__main__')
            provider.assert_not_called()

    def test_usage_counts_cached_input_in_total_without_leaking_content(self):
        response = SimpleNamespace(model='test-model', secret='private reading', usage=SimpleNamespace(
            input_tokens=120, cache_creation_input_tokens=1000,
            cache_read_input_tokens=9000, output_tokens=50,
            cache_creation=SimpleNamespace(ephemeral_5m_input_tokens=600, ephemeral_1h_input_tokens=400)))
        with self.assertLogs(prompt_cache.logger, 'INFO') as logs:
            event = prompt_cache.record_usage(response, operation='reading', system_text='private rules', ttl='5m', started_at=time.monotonic())
        self.assertEqual(event['total_input_tokens'], 10120)
        self.assertTrue(event['cache_hit'])
        self.assertEqual(event['cache_read_fraction'], round(9000 / 10120, 6))
        self.assertEqual(event['cache_write_1h_tokens'], 400)
        self.assertNotIn('private', '\n'.join(logs.output))
        self.assertNotIn('user_id', event)
        self.assertNotIn('reading', json.dumps({k:v for k,v in event.items() if k != 'operation'}))

    def test_missing_usage_is_unknown_not_zero_or_cache_hit(self):
        event = prompt_cache.record_usage(None, operation='reading_stream', system_text='fixed', ttl='5m', started_at=time.monotonic())
        self.assertFalse(event['usage_available'])
        self.assertIsNone(event['input_tokens'])
        self.assertIsNone(event['cache_hit'])
        self.assertIsNone(event['total_input_tokens'])

    def test_cache_miss_and_partial_usage_are_accounted_honestly(self):
        event = prompt_cache.record_usage({'model':'m','usage':{'input_tokens':2, 'output_tokens':1, 'cache_creation_input_tokens':500, 'cache_read_input_tokens':0}}, operation='reading', system_text='x', ttl='5m', started_at=time.monotonic())
        self.assertFalse(event['cache_hit'])
        self.assertEqual(event['total_input_tokens'], 502)
        self.assertEqual(event['cache_read_fraction'], 0)
        self.assertIsNone(event['cache_write_5m_tokens'])
        partial = prompt_cache.record_usage({'usage':{'input_tokens':2}}, operation='reading', system_text='x', ttl='5m', started_at=time.monotonic())
        self.assertIsNone(partial['total_input_tokens'])

    def test_logging_failure_cannot_fail_paid_generation(self):
        with patch.object(prompt_cache.logger, 'info', side_effect=RuntimeError('disk unavailable')):
            self.assertIsNone(prompt_cache.record_usage({'usage':{}}, operation='chat', system_text='x', ttl='1h', started_at=time.monotonic()))


class ClaudeCacheIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        cls.web = app

    def response(self):
        return SimpleNamespace(model='test-model', content=[SimpleNamespace(type='text', text='完整解讀')], usage=SimpleNamespace(input_tokens=5, cache_creation_input_tokens=0, cache_read_input_tokens=2048, output_tokens=3))

    def test_reading_chat_and_stream_share_fixed_prefix_only(self):
        fixed = '固定規則\n不可修改的內容'
        fake = MagicMock()
        fake.messages.create.return_value = self.response()
        stream = fake.messages.stream.return_value.__enter__.return_value
        stream.text_stream = iter(['完整', '解讀'])
        stream.get_final_message.return_value = self.response()
        private_question = '私人問題與卦象'
        chat = [{'role':'user','content':private_question}, {'role':'assistant','content':'個人解讀'}, {'role':'user','content':'個人追問'}]
        with patch('anthropic.Anthropic', return_value=fake), patch.dict(os.environ, {'AI_PROMPT_CACHE_TTL':'1h'}):
            with self.assertLogs(prompt_cache.logger, 'INFO') as logs:
                self.assertEqual(self.web._call_claude_reading(fixed, private_question), '完整解讀')
                self.assertEqual(self.web._call_claude_chat(fixed, chat), '完整解讀')
                self.assertEqual(''.join(self.web._stream_claude_reading(fixed, private_question)), '完整解讀')
        calls = fake.messages.create.call_args_list + fake.messages.stream.call_args_list
        self.assertEqual(len(calls), 3)
        for call in calls:
            self.assertEqual(call.kwargs['system'], prompt_cache.system_blocks(fixed, ttl='1h'))
            self.assertNotIn(private_question, json.dumps(call.kwargs['system'], ensure_ascii=False))
        self.assertEqual(fake.messages.create.call_args_list[1].kwargs['messages'], chat)
        self.assertEqual(len(logs.output), 3)
        hashes = {json.loads(line.split(':',2)[2])['prompt_sha256'] for line in logs.output}
        self.assertEqual(len(hashes), 1)
        for private in (private_question, '個人解讀', '個人追問', fixed):
            self.assertNotIn(private, '\n'.join(logs.output))

    def test_off_applies_to_reading_chat_and_stream_with_usage_preserved(self):
        fake = MagicMock()
        fake.messages.create.return_value = self.response()
        stream = fake.messages.stream.return_value.__enter__.return_value
        stream.text_stream = iter(['完整解讀'])
        stream.get_final_message.return_value = self.response()
        with patch.dict(os.environ, {'AI_PROMPT_CACHE_TTL': 'off'}), patch('anthropic.Anthropic', return_value=fake):
            with self.assertLogs(prompt_cache.logger, 'INFO') as logs:
                self.web._call_claude_reading('fixed', 'q')
                self.web._call_claude_chat('fixed', [{'role': 'user', 'content': 'q'}])
                list(self.web._stream_claude_reading('fixed', 'q'))
        for call in fake.messages.create.call_args_list + fake.messages.stream.call_args_list:
            self.assertEqual(call.kwargs['system'], [{'type': 'text', 'text': 'fixed'}])
        self.assertEqual(len(logs.output), 3)
        self.assertTrue(all(json.loads(line.split(':', 2)[2])['cache_ttl'] == 'off' for line in logs.output))

    def test_provider_failure_propagates_for_existing_refund_flow(self):
        fake = MagicMock()
        fake.messages.create.side_effect = RuntimeError('provider failed')
        with patch('anthropic.Anthropic', return_value=fake):
            with self.assertRaisesRegex(RuntimeError, 'provider failed'):
                self.web._call_claude_reading('fixed', 'question')

    def test_completed_stream_survives_usage_inspection_failure(self):
        fake = MagicMock()
        stream = fake.messages.stream.return_value.__enter__.return_value
        stream.text_stream = iter(['完整解讀'])
        stream.get_final_message.side_effect = RuntimeError('usage missing')
        with patch('anthropic.Anthropic', return_value=fake):
            self.assertEqual(''.join(self.web._stream_claude_reading('fixed', 'q')), '完整解讀')

    def test_interrupted_stream_still_fails_for_existing_refund_flow(self):
        def interrupted():
            yield 'partial'
            raise RuntimeError('stream disconnected')
        fake = MagicMock()
        stream = fake.messages.stream.return_value.__enter__.return_value
        stream.text_stream = interrupted()
        with patch('anthropic.Anthropic', return_value=fake):
            with self.assertRaisesRegex(RuntimeError, 'stream disconnected'):
                list(self.web._stream_claude_reading('fixed', 'q'))
        stream.get_final_message.assert_not_called()
