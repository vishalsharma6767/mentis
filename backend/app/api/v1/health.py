"""Health check and diagnostic endpoints."""

import asyncio
import json
import time as time_module

from fastapi import APIRouter

from app.core.logger import get_logger

log = get_logger(__name__)
router = APIRouter(tags=['health'])


@router.get('/health/groq-test')
async def test_groq():
    """Test the Groq API directly and return detailed results."""
    from app.ai.gateway import AIGateway

    result = {
        'groq_key_set': False,
        'providers': [],
        'simple_call': None,
        'json_call': None,
        'error': None,
    }

    try:
        gw = await AIGateway.get_instance()
        providers = [p.value for p in gw.available_providers]
        result['providers'] = providers
        result['groq_key_set'] = 'groq' in providers

        # Simple non-JSON call
        try:
            t0 = time_module.monotonic()
            resp = await gw.execute(
                messages=[{'role': 'user', 'content': 'Say hello in 3 words'}],
                expect_json=False,
                max_tokens=50,
                temperature=0.1,
            )
            result['simple_call'] = {
                'ok': True,
                'text': resp.text[:200],
                'latency_ms': round((time_module.monotonic() - t0) * 1000),
                'model': resp.model,
            }
        except Exception as e:
            result['simple_call'] = {'ok': False, 'error': str(e)[:200]}

        # JSON call
        try:
            t0 = time_module.monotonic()
            resp = await gw.execute(
                messages=[
                    {'role': 'system', 'content': 'Return valid JSON only'},
                    {'role': 'user', 'content': 'Return JSON: {"greeting": "hello"}'},
                ],
                expect_json=True,
                max_tokens=100,
                temperature=0.1,
            )
            result['json_call'] = {
                'ok': True,
                'text': resp.text[:200],
                'latency_ms': round((time_module.monotonic() - t0) * 1000),
            }
        except Exception as e:
            result['json_call'] = {'ok': False, 'error': str(e)[:200]}

    except Exception as e:
        result['error'] = str(e)[:300]

    return result
