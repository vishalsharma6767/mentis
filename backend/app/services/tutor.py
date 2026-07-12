"""Legacy tutor endpoints backed by the shared Gemini -> Groq gateway."""

from __future__ import annotations

from typing import Any, Optional

from app.ai.gateway import AIGateway
from app.core.exceptions import AIProviderError
from app.utils.json_utils import extract_json


SYSTEM_PROMPT = """You are Mentis, an experienced Indian teacher.
Teach in warm, natural Hinglish and adapt to the student's level.
Guide students through small logical steps before revealing any answer.
Never say that you are an AI. Return only the requested JSON."""


class TutorService:
    """Compatibility service for the older /api/tutor routes.

    These routes use the same provider chain as the V1 streaming experience,
    so they no longer return hardcoded lessons when a model is available.
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def generate_lesson(
        self,
        problem: dict[str, Any],
        level: str = 'intermediate',
        mode: str = 'math',
    ) -> dict[str, Any]:
        prompt = f"""Create a complete, personalised lesson for this student.

Learning mode: {mode}
Student level: {level}
Problem type: {problem.get('type', 'general')}
Problem: {problem.get('content', '')}

Return JSON exactly in this shape:
{{
  "steps": [
    {{"number": 1, "instruction": "...", "explanation": "...", "hint": "...", "answer": "...", "ar_annotation": "...", "focus": "..."}}
  ],
  "final_answer": "...",
  "key_concept": "...",
  "confidence_check": "...",
  "recommended_practice": ["..."]
}}
Use 3 to 6 useful steps. Every field must be grounded in the student's problem."""
        return await self._request_json(prompt, max_tokens=2048, temperature=0.3)

    async def get_step_help(
        self,
        problem: dict[str, Any],
        completed: list[Any],
        current: dict[str, Any],
    ) -> str:
        completed_text = '\n'.join(
            f"Step {item.get('number', '?')}: {item.get('instruction', '')}"
            for item in completed
            if isinstance(item, dict)
        )
        prompt = f"""The student needs help with one step.

Problem: {problem.get('content', '')}
Completed work:
{completed_text or 'No completed steps yet.'}
Current step: {current.get('instruction', '')}

Give a concise Hinglish explanation and one hint. Do not invent a generic
example; refer to the actual problem."""
        gateway = await self._resolve_gateway()
        try:
            response = await gateway.execute(
                messages=[
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': prompt},
                ],
                expect_json=False,
                max_tokens=700,
                temperature=0.4,
                use_cache=False,
            )
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError(
                provider='all',
                message='The AI teacher could not generate step help',
            ) from exc

        if not response.text.strip():
            raise AIProviderError(provider='all', message='The AI teacher returned an empty step-help response')
        return response.text.strip()

    async def answer_doubt(
        self,
        content: str,
        question: str,
        current_step: Optional[dict[str, Any]] = None,
        level: str = 'intermediate',
        mode: str = 'math',
    ) -> dict[str, Any]:
        current = current_step or {}
        prompt = f"""Answer this student doubt like a patient Indian teacher.

Learning mode: {mode}
Student level: {level}
Problem: {content}
Current step: {current.get('instruction', 'No step selected')}
Student doubt: {question}

Return JSON exactly in this shape:
{{
  "reply": "specific Hinglish explanation",
  "pen_annotation": "short text to write on the board",
  "follow_up": "one useful question for the student"
}}
All three values must address the actual doubt."""
        return await self._request_json(prompt, max_tokens=900, temperature=0.35)

    async def _request_json(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        gateway = await self._resolve_gateway()
        try:
            response = await gateway.execute(
                messages=[
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': prompt},
                ],
                expect_json=True,
                max_tokens=max_tokens,
                temperature=temperature,
                use_cache=False,
            )
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError(
                provider='all',
                message='The AI teacher could not generate a response',
            ) from exc

        parsed = extract_json(response.text)
        if not isinstance(parsed, dict):
            raise AIProviderError(provider='all', message='The AI teacher returned an invalid structured response')
        return parsed

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway


tutor_service = TutorService()
