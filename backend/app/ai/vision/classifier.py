"""Problem Classifier — detects subject and difficulty from problem text.

Analyses extracted problem text to determine:
  - Subject (math, physics, chemistry, biology, coding, general)
  - Difficulty (beginner, intermediate, advanced)
  - Problem type (equation, graph, word_problem, diagram, code)
  - Key topics and formulas
"""

from __future__ import annotations

import json
from typing import Optional

from app.ai.gateway import AIGateway, LLMProvider
from app.core.constants import Difficulty, Subject
from app.core.logger import get_logger

log = get_logger(__name__)

KEYWORD_SUBJECTS: dict[str, str] = {
    'math': [
        'equation', 'solve', 'graph', 'derivative', 'integral', 'matrix',
        'triangle', 'angle', 'percentage', 'algebra', 'calculus', 'geometry',
        'arithmetic', 'fraction', 'decimal', 'ratio', 'proportion',
    ],
    'physics': [
        'force', 'velocity', 'acceleration', 'energy', 'momentum',
        'wavelength', 'frequency', 'circuit', 'resistance', 'current',
        'voltage', 'newton', 'gravity', 'friction', 'work', 'power',
    ],
    'chemistry': [
        'reaction', 'molecule', 'atom', 'element', 'compound', 'acid',
        'base', 'oxidation', 'reduction', 'molarity', 'concentration',
        'pH', 'electron', 'proton', 'neutron', 'bond', 'periodic',
    ],
    'biology': [
        'cell', 'dna', 'rna', 'photosynthesis', 'respiration', 'enzyme',
        'protein', 'carbohydrate', 'lipid', 'nucleus', 'mitochondria',
        'chromosome', 'gene', 'evolution', 'ecosystem', 'habitat',
    ],
    'coding': [
        'function', 'variable', 'loop', 'array', 'algorithm', 'python',
        'java', 'javascript', 'code', 'program', 'compile', 'syntax',
        'class', 'object', 'recursion', 'iteration',
    ],
}


class ProblemClassifier:
    """Classifies problem subject, difficulty, and type from text.

    Usage::

        classifier = ProblemClassifier()
        result = await classifier.classify("Solve for x: 2x + 5 = 15")
        # result['subject'] == Subject.MATH
        # result['difficulty'] == Difficulty.BEGINNER
        # result['topics'] == ["Linear Equations"]
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def classify(
        self,
        text: str,
        provider: Optional[LLMProvider] = None,
    ) -> dict:
        """Classify the problem from its text.

        Args:
            text: The extracted problem text.
            provider: Optional LLM provider override.

        Returns:
            Dict with subject, difficulty, topics, problem_type, formulas.
        """
        if not text or not text.strip():
            return self._fallback()

        # Fast heuristic classification
        heuristic = self._heuristic_classify(text)

        # Use LLM for deeper analysis
        return await self._llm_classify(text, heuristic, provider)

    def _heuristic_classify(self, text: str) -> dict:
        """Quick keyword-based classification."""
        lower = text.lower()
        best_subject = 'general'
        best_score = 0

        for subject, keywords in KEYWORD_SUBJECTS.items():
            score = sum(1 for kw in keywords if kw in lower)
            if score > best_score:
                best_score = score
                best_subject = subject

        return {
            'subject': best_subject,
            'confidence': min(best_score / 5.0, 1.0),
        }

    async def _llm_classify(
        self,
        text: str,
        heuristic: dict,
        provider: Optional[LLMProvider],
    ) -> dict:
        """Use AIGateway for detailed classification."""
        gateway = await self._resolve_gateway()

        try:
            response = await gateway.execute(
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            'Classify this problem text. Return JSON with:\n'
                            '  subject: math|physics|chemistry|biology|coding|general\n'
                            '  difficulty: beginner|intermediate|advanced\n'
                            '  topics: [list of topic names]\n'
                            '  problem_type: equation|graph|word_problem|diagram|code|general\n'
                            '  formulas: [relevant formulas or equations]'
                        ),
                    },
                    {
                        'role': 'user',
                        'content': f'Heuristic suggests: {heuristic.get("subject")}\n\nProblem text:\n{text[:2000]}',
                    },
                ],
                provider=provider or LLMProvider.GROQ,
                expect_json=True,
                max_tokens=1024,
                temperature=0.3,
                use_cache=True,
            )

            parsed = json.loads(response.text)
            return {
                'subject': self._resolve_subject(parsed.get('subject', heuristic.get('subject', 'general'))),
                'difficulty': self._resolve_difficulty(parsed.get('difficulty', 'intermediate')),
                'topics': parsed.get('topics', []),
                'problem_type': parsed.get('problem_type', 'general'),
                'formulas': parsed.get('formulas', []),
                'confidence': heuristic.get('confidence', 0.5),
            }

        except Exception as exc:
            log.warning('classifier_llm_failed', error=str(exc)[:100])
            return {
                'subject': self._resolve_subject(heuristic.get('subject', 'general')),
                'difficulty': Difficulty.INTERMEDIATE,
                'topics': [],
                'problem_type': 'general',
                'formulas': [],
                'confidence': heuristic.get('confidence', 0.3),
            }

    def _fallback(self) -> dict:
        return {
            'subject': Subject.GENERAL,
            'difficulty': Difficulty.INTERMEDIATE,
            'topics': [],
            'problem_type': 'general',
            'formulas': [],
            'confidence': 0.0,
        }

    @staticmethod
    def _resolve_subject(val: str) -> Subject:
        if isinstance(val, Subject):
            return val
        try:
            return Subject(val.lower())
        except ValueError:
            return Subject.GENERAL

    @staticmethod
    def _resolve_difficulty(val: str) -> Difficulty:
        if isinstance(val, Difficulty):
            return val
        try:
            return Difficulty(val.lower())
        except ValueError:
            return Difficulty.INTERMEDIATE

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway
