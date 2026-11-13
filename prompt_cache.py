"""Stable Claude prompt-cache boundaries and content-free usage telemetry.

Only the fixed system instructions are cacheable here. Member questions, chart
JSON, readings and conversation history remain outside the shared breakpoint.
"""
import hashlib
import json
import logging
import os
import sys
import time
from collections.abc import Mapping

logger = logging.getLogger('hexagram.ai_usage')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
logger.propagate = False


def cache_ttl():
    value = os.environ.get('AI_PROMPT_CACHE_TTL', 'off').strip().lower()
    if value not in ('off', '5m', '1h'):
        raise ValueError('AI_PROMPT_CACHE_TTL must be off, 5m or 1h')
    return value


def system_blocks(system_text, ttl=None):
    """Keep instruction bytes/order unchanged across generation modes and users."""
    selected = cache_ttl() if ttl is None else ttl
    if selected == 'off':
        return [{'type': 'text', 'text': system_text}]
    if selected not in ('5m', '1h'):
        raise ValueError('cache TTL must be off, 5m or 1h')
    return [{'type': 'text', 'text': system_text,
             'cache_control': {'type': 'ephemeral', 'ttl': selected}}]


def _field(obj, name, default=None):
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _tokens(obj, name):
    value = _field(obj, name)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def record_usage(response, *, operation, system_text, ttl, started_at):
    """Log counters only; never serialize a response, prompt, question or user id.

    Missing usage is distinct from zero. Telemetry failures must never turn a
    successful paid reading into a failed/refunded request.
    """
    try:
        usage = _field(response, 'usage')
        details = _field(usage, 'cache_creation')
        fields = {name: _tokens(usage, name) for name in (
            'input_tokens', 'cache_creation_input_tokens',
            'cache_read_input_tokens', 'output_tokens',
        )}
        inputs = [fields[name] for name in (
            'input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens',
        )]
        total = sum(inputs) if all(value is not None for value in inputs) else None
        read = fields['cache_read_input_tokens']
        event = {
            'event': 'ai_usage',
            'operation': operation,
            'model': _field(response, 'model'),
            'prompt_sha256': hashlib.sha256(system_text.encode('utf-8')).hexdigest(),
            'cache_ttl': ttl,
            'usage_available': usage is not None,
            **fields,
            'cache_write_5m_tokens': _tokens(details, 'ephemeral_5m_input_tokens'),
            'cache_write_1h_tokens': _tokens(details, 'ephemeral_1h_input_tokens'),
            'total_input_tokens': total,
            'cache_hit': (read > 0) if read is not None else None,
            'cache_read_fraction': round(read / total, 6) if total and read is not None else None,
            'duration_ms': max(0, round((time.monotonic() - started_at) * 1000)),
        }
        logger.info(json.dumps(event, ensure_ascii=False, separators=(',', ':')))
        return event
    except Exception:
        # Do not log exception details: third-party objects could include content.
        return None
