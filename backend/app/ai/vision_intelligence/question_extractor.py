"""Question Extractor — separates questions from answers and notes.

Analyses the page layout and OCR text to identify:
  - Question text (what was asked)
  - Student answer (what the student wrote)
  - Teacher notes / corrections
  - Worked-out steps
  - Examples and instructions

Produces structured Question objects with associated answers and
mistakes, ready for the Scene Builder.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import numpy as np

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.vision_intelligence.schema import (
    BlockType,
    BoundingBox,
    DetectedMistake,
    MistakeType,
    Question,
    TextBlock,
)
from app.core.logger import get_logger

log = get_logger(__name__)

# Patterns suggesting a question
QUESTION_PATTERNS = [
    re.compile(r'^(?:Q\.|Question|Que|Prob|Problem|Solve|Find|Evaluate|Calculate|Determine|Show|Prove|Derive|Integrate|Differentiate|Simplify|Expand|Factor)', re.IGNORECASE),
    re.compile(r'^\d+[\.\)]\s+'),  # "1. " or "1) "
    re.compile(r'^\([a-zA-Z]\)\s+'),  # "(a) " or "(i) "
    re.compile(r'\?$'),
    re.compile(r'(?:find|solve|evaluate|calculate|determine|show|prove|derive)', re.IGNORECASE),
]

ANSWER_PATTERNS = [
    re.compile(r'^(?:Ans|Answer|Solution|Sol\.|Step)', re.IGNORECASE),
    re.compile(r'^[=xya-z]'),  # starts with variable or equals
    re.compile(r'^\d+\s*[=+\-*/]'),  # starts with equation
]


class QuestionExtractor:
    """Separates questions, answers, and notes from OCR output.

    Usage::

        qe = QuestionExtractor()
        questions = await qe.extract(text_blocks, image)
        # questions[0].question_text, questions[0].student_answer
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def extract(
        self,
        text_blocks: list[TextBlock],
        image: Optional[np.ndarray] = None,
        provider: Optional[LLMProvider] = None,
    ) -> list[Question]:
        """Extract structured questions from text blocks.

        Args:
            text_blocks: OCR text blocks with positions.
            image: Optional full image for AI vision refinement.
            provider: Optional LLM provider override.

        Returns:
            List of Question objects with associated answers.
        """
        log.info('question_extractor_start', blocks=len(text_blocks))

        questions: list[Question] = []
        current_q: Optional[Question] = None
        ordered_blocks = sorted(text_blocks, key=lambda b: (b.bbox.y, b.bbox.x))

        for block in ordered_blocks:
            if not block.text or not block.text.strip():
                continue

            text = block.text.strip()

            if self._is_question(text):
                if current_q and current_q.question_text:
                    questions.append(current_q)
                current_q = Question(
                    question_text=text[:1000],
                    bbox=block.bbox,
                    confidence=block.confidence,
                    step_number=len(questions) + 1,
                )

            elif current_q and self._is_answer(text):
                if current_q.student_answer:
                    current_q.student_answer += '\n' + text[:1000]
                else:
                    current_q.student_answer = text[:1000]
                current_q.is_complete = True

            elif current_q and block.block_type in (BlockType.TEACHER_NOTE, BlockType.MARGIN_NOTE):
                if current_q.teacher_notes:
                    current_q.teacher_notes += '\n' + text[:500]
                else:
                    current_q.teacher_notes = text[:500]

            elif current_q:
                # Continuation of the question or answer
                if not current_q.student_answer:
                    if current_q.question_text:
                        current_q.question_text += ' ' + text[:1000]
                else:
                    current_q.student_answer += '\n' + text[:1000]

        if current_q and current_q.question_text:
            questions.append(current_q)

        # Detect mistakes in student answers
        for q in questions:
            if q.student_answer:
                q.mistakes = self._detect_mistakes(q.student_answer)
                if not q.mistakes and image is not None:
                    ai_mistakes = await self._ai_detect_mistakes(
                        image, q.bbox, provider,
                    )
                    q.mistakes = ai_mistakes

        # AI refinement for complex pages
        if not questions and image is not None:
            questions = await self._fallback_ai_extract(image, provider)

        log.info('question_extractor_complete', questions=len(questions))
        return questions

    # ── Classification ─────────────────────────────────────────────────

    @staticmethod
    def _is_question(text: str) -> bool:
        """Check if text appears to be a question/problem statement."""
        return any(p.search(text) for p in QUESTION_PATTERNS)

    @staticmethod
    def _is_answer(text: str) -> bool:
        """Check if text appears to be an answer or solution."""
        return any(p.search(text) for p in ANSWER_PATTERNS)

    # ── Mistake detection ──────────────────────────────────────────────

    @staticmethod
    def _detect_mistakes(text: str) -> list[DetectedMistake]:
        """Detect common mistake patterns in student answers."""
        mistakes: list[DetectedMistake] = []

        # Sign errors
        sign_matches = re.finditer(r'(?:\+\s*-|-\s*\+|[=]\s*[-+]\s*[-+])', text)
        for m in sign_matches:
            mistakes.append(DetectedMistake(
                text=m.group(),
                bbox=BoundingBox(x=0, y=0, width=0, height=0),
                mistake_type=MistakeType.SIGN_ERROR,
                confidence=0.5,
            ))

        # Formula errors
        if re.search(r'\b[Ff]ormula\b', text) or re.search(r'\b[Ee]quation\b', text):
            mistakes.append(DetectedMistake(
                text='Possible formula error',
                bbox=BoundingBox(x=0, y=0, width=0, height=0),
                mistake_type=MistakeType.FORMULA_ERROR,
                confidence=0.3,
            ))

        return mistakes

    # ── AI detection ───────────────────────────────────────────────────

    async def _ai_detect_mistakes(
        self,
        image: np.ndarray,
        bbox: BoundingBox,
        provider: Optional[LLMProvider],
    ) -> list[DetectedMistake]:
        """Use AI to detect mistakes in a region."""
        h, w = image.shape[:2]
        x = int(bbox.x * w)
        y = int(bbox.y * h)
        rw = int(bbox.width * w)
        rh = int(bbox.height * h)

        if rw < 20 or rh < 20:
            return []

        crop = image[y:y + rh, x:x + rw]
        try:
            import base64
            success, buf = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not success:
                return []
            image_b64 = base64.b64encode(buf.tobytes()).decode('utf-8')

            gateway = await self._resolve_gateway()
            response = await gateway.execute(
                messages=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': (
                                    'This shows a student\'s answer to a problem. '
                                    'Identify any mistakes. '
                                    'Types: calculation, conceptual, careless, sign_error, '
                                    'formula_error, unit_error. '
                                    'Return JSON: {"mistakes": [{"text": "mistake description", '
                                    '"mistake_type": "...", "correction": "...", '
                                    '"confidence": 0.0-1.0}]}'
                                ),
                            },
                            {
                                'type': 'image_url',
                                'image_url': {'url': f'data:image/jpeg;base64,{image_b64}'},
                            },
                        ],
                    },
                ],
                provider=provider or LLMProvider.GROQ,
                expect_json=True,
                max_tokens=1024,
                temperature=0.1,
                use_cache=True,
            )

            parsed = json.loads(response.text) if isinstance(response.text, str) else response.text
            raw = parsed.get('mistakes', [])
            mistakes: list[DetectedMistake] = []
            for m in raw[:10]:
                if not isinstance(m, dict):
                    continue
                mtype = m.get('mistake_type', 'unknown')
                try:
                    mtype_enum = MistakeType(mtype.lower())
                except ValueError:
                    mtype_enum = MistakeType.UNKNOWN
                mistakes.append(DetectedMistake(
                    text=str(m.get('text', ''))[:300],
                    bbox=BoundingBox(x=0, y=0, width=0, height=0),
                    mistake_type=mtype_enum,
                    confidence=float(m.get('confidence', 0.3)),
                    correction=str(m.get('correction', '')),
                ))
            return mistakes

        except Exception as exc:
            log.debug('ai_mistake_detection_failed', error=str(exc)[:80])
            return []

    # ── Fallback ───────────────────────────────────────────────────────

    async def _fallback_ai_extract(
        self,
        image: np.ndarray,
        provider: Optional[LLMProvider],
    ) -> list[Question]:
        """Use AI vision to extract questions when layout analysis fails."""
        try:
            import base64
            success, buf = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not success:
                return []
            image_b64 = base64.b64encode(buf.tobytes()).decode('utf-8')

            gateway = await self._resolve_gateway()
            response = await gateway.execute(
                messages=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': (
                                    'This is a student\'s notebook page. '
                                    'Identify each question and the student\'s answer. '
                                    'Return JSON: {"questions": ['
                                    '{"question_text": "...", "student_answer": "...", '
                                    '"step_number": 1}]}'
                                ),
                            },
                            {
                                'type': 'image_url',
                                'image_url': {'url': f'data:image/jpeg;base64,{image_b64}'},
                            },
                        ],
                    },
                ],
                provider=provider or LLMProvider.GROQ,
                expect_json=True,
                max_tokens=2048,
                temperature=0.1,
                use_cache=True,
            )

            parsed = json.loads(response.text) if isinstance(response.text, str) else response.text
            raw = parsed.get('questions', [])
            return [
                Question(
                    question_text=str(q.get('question_text', ''))[:1000],
                    student_answer=str(q.get('student_answer', ''))[:2000],
                    bbox=BoundingBox(x=0, y=0, width=1, height=1),
                    confidence=0.5,
                    step_number=q.get('step_number', i + 1),
                )
                for i, q in enumerate(raw[:10])
                if isinstance(q, dict) and q.get('question_text')
            ]

        except Exception as exc:
            log.warning('fallback_ai_extract_failed', error=str(exc)[:80])
            return []

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway


try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore
    log.warning('OpenCV not available — QuestionExtractor disabled')
