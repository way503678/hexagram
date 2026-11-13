"""Two provider requests, one output token each; no member or billing records.

Run after deployment:
  docker exec -i hexagram python - < scripts/verify_prompt_cache.py
This diagnostic incurs normal prompt-cache write/read fees. It is not scheduled.
"""
import json
import time

import prompt_cache

def main():
    ttl = prompt_cache.cache_ttl()
    if ttl == 'off':
        raise SystemExit('Prompt cache is disabled; explicitly select 5m or 1h before running this paid diagnostic.')
    import anthropic
    import app
    client = anthropic.Anthropic()
    system = app._MANUAL_AI_PROMPT
    if not system:
        raise RuntimeError('Manual fixed rules unavailable')
    results = []
    for marker in ('A', 'B'):
        started = time.monotonic()
        response = client.messages.create(
            model=app._AI_READING_MODEL,
            max_tokens=1,
            system=prompt_cache.system_blocks(system, ttl=ttl),
            messages=[{'role': 'user', 'content': f'固定規則快取驗證 {marker}。這是合成測試，沒有會員資料。'}],
        )
        event = prompt_cache.record_usage(response, operation='cache_probe', system_text=system,
                                          ttl=ttl, started_at=started)
        if not event or not event['usage_available']:
            raise RuntimeError('Provider usage unavailable; cannot confirm a cache hit')
        results.append(event)
    if not results[1]['cache_hit']:
        raise RuntimeError('Second request did not hit the shared fixed-rule cache')
    print(json.dumps({
        'verified': True,
        'model': app._AI_READING_MODEL,
        'ttl': ttl,
        'prompt_chars': len(system),
        'first_write_tokens': results[0]['cache_creation_input_tokens'],
        'first_read_tokens': results[0]['cache_read_input_tokens'],
        'second_read_tokens': results[1]['cache_read_input_tokens'],
        'second_uncached_input_tokens': results[1]['input_tokens'],
        'second_cache_read_fraction': results[1]['cache_read_fraction'],
        'second_output_tokens': results[1]['output_tokens'],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
