"""Health check and diagnostic endpoints."""

import asyncio
import json as _json
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
    """Run the EXACT planner + teacher prompts and show raw results."""
    from app.ai.gateway import AIGateway
    from app.ai.teacher.personality import TeacherPersonality
    from app.ai.teacher.prompts import planner_agent_prompt, teacher_agent_prompt
    from app.core.constants import Subject, Difficulty

    personality = TeacherPersonality()
    planner_prompt = planner_agent_prompt(personality)
    teacher_prompt = teacher_agent_prompt(personality)

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

    result = {
        'planner': None,
        'teacher': None,
        'error': None,
    }

    gw = await AIGateway.get_instance()
    providers_available = [p.value for p in gw.available_providers]

    # ── Planner test ──────────────────────────────────────────────
    planner_msgs = [
        {'role': 'system', 'content': planner_prompt},
        {'role': 'user', 'content': input_data},
    ]
    try:
        t0 = time_module.monotonic()
        resp = await gw.execute(
            messages=planner_msgs,
            expect_json=True,
            max_tokens=2048,
            temperature=0.2,
        )
        plan_result = {
            'ok': True,
            'text_preview': resp.text[:400],
            'text_len': len(resp.text),
            'latency_ms': round((time_module.monotonic() - t0) * 1000),
            'model': resp.model,
            'provider': resp.provider.value if hasattr(resp.provider, 'value') else str(resp.provider),
            'input_tokens': resp.input_tokens,
            'output_tokens': resp.output_tokens,
        }
        from app.utils.json_utils import extract_json as _extract_json
        parsed = _extract_json(resp.text)
        plan_result['parsed_ok'] = parsed is not None
        if parsed:
            steps = parsed.get('lesson_plan', {}).get('steps', [])
            plan_result['step_count'] = len(steps)
            plan_result['first_step'] = steps[0].get('explanation', '')[:200] if steps else 'no steps'
        result['planner'] = plan_result
    except Exception as e:
        result['planner'] = {'ok': False, 'error': str(e)[:400]}

    # ── Teacher test (EXACT same format as _build_input_prompt) ───
    parts: list[str] = []
    parts.append(_json.dumps({'problem': {
        'text': 'What is the formula for force?',
        'subject': 'physics', 'difficulty': 'intermediate',
        'topics': ['force', 'newtons_laws'], 'type': 'word_problem',
        'formulas': ['F=ma'], 'diagram': None,
    }}, indent=2))
    steps_text = '\n'.join([
        '  Step 1: [observe] Problem ko samjho',
        '  Step 2: [concept] Force ka concept',
        '  Step 3: [example] Real life example',
    ])
    parts.append(f'Lesson plan:\nStrategy: example_first')
    parts.append(f'Adaptations: simplify_language, more_examples')
    parts.append(f'Steps:\n{steps_text}')
    parts.append(f'Current step to teach: 1 of 3')
    parts.append(_json.dumps({'current_step': {
        'phase': 'observe', 'title': 'Problem ko samjho',
        'explanation': 'Dekhte hain problem kya keh rahi hai',
        'hint': 'Force aur mass ka relation dekho',
        'duration_seconds': 45,
    }}, indent=2))
    parts.append(_json.dumps({'student': {
        'level': 'intermediate', 'weak_topics': ['force_diagrams'],
        'strong_topics': ['basic_math'], 'confidence': 'medium',
    }, 'student_message': 'What is force formula?', 'emotion': 'neutral', 'language': 'hinglish'}, indent=2))
    parts.append('Previous dialogue:\nStudent asked about force. Teacher started explaining.')
    parts.append('Teach this step in Hinglish like an experienced Indian classroom teacher. Never give the final answer.')
    teacher_input = '\n\n'.join(parts)

    teacher_msgs = [
        {'role': 'system', 'content': teacher_prompt},
        {'role': 'user', 'content': teacher_input},
    ]
    try:
        t0 = time_module.monotonic()
        resp = await gw.execute(
            messages=teacher_msgs,
            expect_json=True,
            max_tokens=2048,
            temperature=0.2,
        )
        teacher_result = {
            'ok': True,
            'text_preview': resp.text[:400],
            'text_len': len(resp.text),
            'latency_ms': round((time_module.monotonic() - t0) * 1000),
            'model': resp.model,
            'provider': resp.provider.value if hasattr(resp.provider, 'value') else str(resp.provider),
            'input_tokens': resp.input_tokens,
            'output_tokens': resp.output_tokens,
        }
        parsed = _extract_json(resp.text)
        teacher_result['parsed_ok'] = parsed is not None
        if parsed:
            explanation = parsed.get('step', {}).get('explanation', '')
            teacher_result['explanation_preview'] = explanation[:300]
        result['teacher'] = teacher_result
    except Exception as e:
        result['teacher'] = {'ok': False, 'error': str(e)[:400]}

    return result
