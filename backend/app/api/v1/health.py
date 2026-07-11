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


@router.get('/health/pipeline-test')
async def test_pipeline():
    """Run the EXACT planner prompt through Groq and show raw result."""
    from app.ai.gateway import AIGateway
    from app.ai.teacher.personality import TeacherPersonality
    from app.ai.teacher.prompts import planner_agent_prompt
    from app.core.constants import Subject, Difficulty

    personality = TeacherPersonality()
    prompt = planner_agent_prompt(personality)

    import json as _json
    input_data = _json.dumps({
        'problem': {
            'text': 'Test physics problem about force and motion',
            'subject': 'physics',
            'difficulty': 'intermediate',
            'topics': ['force', 'newtons_laws'],
            'type': 'word_problem',
            'formulas': ['F=ma'],
            'diagram': None,
        },
        'student': {
            'level': 'intermediate',
            'weak_topics': ['force_diagrams'],
            'strong_topics': ['basic_math'],
            'recent_topics': [],
            'revision_due': [],
            'recent_mistakes': [],
            'session_count': 1,
            'confidence': 'medium',
            'streak': 0,
        },
    }, indent=2)

    messages = [
        {'role': 'system', 'content': prompt},
        {'role': 'user', 'content': input_data},
    ]

    result = {
        'prompt_chars': len(prompt),
        'input_chars': len(input_data),
        'total_chars': len(prompt) + len(input_data),
        'call': None,
        'extracted': None,
        'error': None,
    }

    try:
        gw = await AIGateway.get_instance()
        t0 = time_module.monotonic()
        resp = await gw.execute(
            messages=messages,
            expect_json=True,
            max_tokens=2048,
            temperature=0.2,
        )
        result['call'] = {
            'ok': True,
            'text_preview': resp.text[:500],
            'text_len': len(resp.text),
            'latency_ms': round((time_module.monotonic() - t0) * 1000),
            'model': resp.model,
            'input_tokens': resp.input_tokens,
            'output_tokens': resp.output_tokens,
        }
        from app.utils.json_utils import extract_json as _extract_json
        parsed = _extract_json(resp.text)
        result['extracted'] = parsed is not None
        if parsed:
            steps = parsed.get('lesson_plan', {}).get('steps', [])
            result['step_count'] = len(steps)
            result['first_step_explanation'] = (steps[0]['explanation'][:200] if steps else 'no steps')
    except Exception as e:
        result['error'] = str(e)[:500]

    return result
