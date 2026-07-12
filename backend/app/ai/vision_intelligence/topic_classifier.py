"""Topic Classifier + Difficulty Estimator — subject, chapter, concept, and difficulty.

Predicts from the extracted page content:
  - Subject (math, physics, chemistry, biology, coding, general)
  - Chapter / topic name
  - Specific concepts being tested
  - Difficulty level (beginner, intermediate, advanced)
  - Learning objective (what the student should learn)

Uses keyword heuristics for fast inference and AIGateway for
deep understanding when confidence is low.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.ai.gateway import AIGateway, LLMProvider
from app.ai.vision_intelligence.schema import Difficulty, Subject
from app.core.logger import get_logger

log = get_logger(__name__)

# ── Keyword maps for fast heuristic classification ──────────────────────

SUBJECT_KEYWORDS: dict[str, list[str]] = {
    'math': [
        'equation', 'solve', 'graph', 'derivative', 'integral', 'matrix',
        'triangle', 'angle', 'percentage', 'algebra', 'calculus', 'geometry',
        'arithmetic', 'fraction', 'decimal', 'ratio', 'proportion', 'function',
        'polynomial', 'quadratic', 'linear', 'logarithm', 'trigonometric',
        'statistics', 'probability', 'permutation', 'combination',
    ],
    'physics': [
        'force', 'velocity', 'acceleration', 'energy', 'momentum',
        'wavelength', 'frequency', 'circuit', 'resistance', 'current',
        'voltage', 'newton', 'gravity', 'friction', 'work', 'power',
        'kinematics', 'dynamics', 'optics', 'thermodynamics', 'electromagnetism',
        'wave', 'sound', 'light', 'lens', 'mirror', 'capacitor',
    ],
    'chemistry': [
        'reaction', 'molecule', 'atom', 'element', 'compound', 'acid',
        'base', 'oxidation', 'reduction', 'molarity', 'concentration',
        'ph', 'electron', 'proton', 'neutron', 'bond', 'periodic',
        'chemical', 'organic', 'inorganic', 'precipitate', 'catalyst',
        'enthalpy', 'entropy', 'equilibrium',
    ],
    'biology': [
        'cell', 'dna', 'rna', 'photosynthesis', 'respiration', 'enzyme',
        'protein', 'carbohydrate', 'lipid', 'nucleus', 'mitochondria',
        'chromosome', 'gene', 'evolution', 'ecosystem', 'habitat',
        'biology', 'anatomy', 'physiology', 'genetics', 'taxonomy',
    ],
    'coding': [
        'function', 'variable', 'loop', 'array', 'algorithm', 'python',
        'java', 'javascript', 'code', 'program', 'compile', 'syntax',
        'class', 'object', 'recursion', 'iteration', 'data structure',
        'binary', 'tree', 'graph', 'sort', 'search',
    ],
}

DIFFICULTY_KEYWORDS: dict[str, list[str]] = {
    'beginner': [
        'basic', 'simple', 'easy', 'introduction', 'define', 'what is',
        'identify', 'list', 'name', 'true or false', 'fill in',
    ],
    'advanced': [
        'prove', 'derive', 'generalize', 'complex', 'in-depth',
        'non-linear', 'multivariable', 'differential equation',
        'quantum', 'relativity', 'spectroscopy', 'retrosynthesis',
    ],
}

CHAPTER_KEYWORDS: dict[str, list[tuple[str, list[str]]]] = {
    'math': [
        ('linear_equations', ['linear equation', 'variable', 'solve for x', 'ax + b', 'slope', 'intercept']),
        ('quadratic_equations', ['quadratic', 'ax²', 'x²', 'discriminant', 'roots', 'parabola']),
        ('trigonometry', ['sin', 'cos', 'tan', 'angle', 'triangle', 'sine', 'cosine', 'tangent']),
        ('calculus', ['derivative', 'integral', 'limit', 'differentiation', 'integration']),
        ('statistics', ['mean', 'median', 'mode', 'standard deviation', 'probability']),
        ('geometry', ['triangle', 'circle', 'area', 'perimeter', 'volume', 'angle']),
    ],
    'physics': [
        ('kinematics', ['velocity', 'acceleration', 'displacement', 'speed', 'motion']),
        ('dynamics', ['force', 'newton', 'friction', 'mass', 'weight']),
        ('optics', ['lens', 'mirror', 'refraction', 'reflection', 'light']),
        ('electricity', ['current', 'voltage', 'resistance', 'circuit', 'ohm']),
    ],
    'chemistry': [
        ('atomic_structure', ['atom', 'electron', 'proton', 'neutron', 'shell', 'orbital']),
        ('chemical_bonding', ['bond', 'covalent', 'ionic', 'metallic', 'molecule']),
        ('organic_chemistry', ['carbon', 'hydrocarbon', 'functional group', 'alkane', 'alkene']),
    ],
    'biology': [
        ('cell_biology', ['cell', 'membrane', 'nucleus', 'mitochondria', 'organelle']),
        ('genetics', ['dna', 'gene', 'chromosome', 'allele', 'inheritance']),
        ('ecology', ['ecosystem', 'habitat', 'food chain', 'population', 'biodiversity']),
    ],
    'coding': [
        ('basics', ['variable', 'data type', 'print', 'input', 'function']),
        ('data_structures', ['array', 'list', 'stack', 'queue', 'tree', 'graph']),
        ('algorithms', ['sort', 'search', 'recursion', 'complexity', 'binary']),
    ],
}


class TopicClassifier:
    """Predicts subject, chapter, concepts, and difficulty from page content.

    Usage::

        tc = TopicClassifier()
        result = await tc.classify(text, formulas, diagrams)
        # result['subject'], result['topic'], result['difficulty']
        # result['concepts']
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def classify(
        self,
        full_text: str,
        formulas: Optional[list[dict[str, Any]]] = None,
        diagrams: Optional[list[dict[str, Any]]] = None,
        provider: Optional[LLMProvider] = None,
    ) -> dict[str, Any]:
        """Classify the page content.

        Args:
            full_text: All OCR text from the page.
            formulas: Detected formula descriptors.
            diagrams: Detected diagram descriptors.
            provider: Optional LLM provider override.

        Returns:
            Dict with: subject, topic, difficulty, concepts, learning_objective.
        """
        log.info('classifier_start')

        if not full_text or not full_text.strip():
            return self._fallback()

        lower = full_text.lower()

        # 1. Heuristic subject classification
        subject = self._heuristic_subject(lower)
        subject_conf = self._heuristic_subject_confidence(lower)

        # 2. Heuristic chapter detection
        topic = self._heuristic_chapter(lower, subject)

        # 3. Concepts
        concepts = self._extract_concepts(lower, subject)

        # 4. Heuristic difficulty
        difficulty = self._heuristic_difficulty(lower)

        result = {
            'subject': subject,
            'topic': topic,
            'difficulty': difficulty,
            'concepts': concepts[:8],
            'learning_objective': self._infer_objective(subject, topic),
            'confidence': subject_conf,
        }

        # AI refinement if heuristic confidence is low
        if subject_conf < 0.5 or topic == 'general':
            refined = await self._refine_with_ai(
                full_text, formulas, diagrams, provider,
            )
            if refined:
                result.update(refined)

        log.info(
            'classifier_complete',
            subject=result['subject'],
            topic=result['topic'],
            difficulty=result['difficulty'],
            confidence=round(result['confidence'], 3),
        )
        return result

    # ── Heuristics ──────────────────────────────────────────────────────

    @staticmethod
    def _heuristic_subject(text: str) -> str:
        """Fast keyword-based subject detection."""
        scores: dict[str, int] = {}
        for subject, keywords in SUBJECT_KEYWORDS.items():
            scores[subject] = sum(1 for kw in keywords if kw in text)

        if not scores or max(scores.values()) == 0:
            return 'general'
        return max(scores, key=scores.get)

    @staticmethod
    def _heuristic_subject_confidence(text: str) -> float:
        """Confidence in the heuristic subject prediction."""
        total = sum(len(kws) for kws in SUBJECT_KEYWORDS.values())
        matches = sum(
            1 for kws in SUBJECT_KEYWORDS.values()
            for kw in kws if kw in text
        )
        return min(matches / max(total * 0.1, 1), 1.0)

    def _heuristic_chapter(self, text: str, subject: str) -> str:
        """Detect the specific chapter/topic."""
        chapters = CHAPTER_KEYWORDS.get(subject, [])
        if not chapters:
            return 'general'

        scores: list[tuple[str, int]] = []
        for chapter_name, keywords in chapters:
            score = sum(1 for kw in keywords if kw in text)
            scores.append((chapter_name, score))

        if not scores or max(s[1] for s in scores) == 0:
            return 'general'
        return max(scores, key=lambda s: s[1])[0]

    @staticmethod
    def _extract_concepts(text: str, subject: str) -> list[str]:
        """Extract specific concept terms from the text."""
        concepts: list[str] = []
        keywords = SUBJECT_KEYWORDS.get(subject, [])
        for kw in keywords:
            if kw in text and kw not in concepts:
                concepts.append(kw)
        return concepts[:8]

    @staticmethod
    def _heuristic_difficulty(text: str) -> str:
        """Estimate difficulty from keyword presence."""
        lower = text.lower()
        adv_score = sum(1 for kw in DIFFICULTY_KEYWORDS['advanced'] if kw in lower)
        beg_score = sum(1 for kw in DIFFICULTY_KEYWORDS['beginner'] if kw in lower)

        if adv_score >= 2:
            return 'advanced'
        if beg_score >= 3 and adv_score == 0:
            return 'beginner'
        return 'intermediate'

    @staticmethod
    def _infer_objective(subject: str, topic: str) -> str:
        """Generate a learning objective from subject + topic."""
        if topic and topic != 'general':
            return f'Understand and apply concepts of {topic.replace("_", " ")}'
        if subject != 'general':
            return f'Master fundamental {subject} concepts'
        return 'Develop problem-solving skills'

    # ── AI refinement ───────────────────────────────────────────────────

    async def _refine_with_ai(
        self,
        text: str,
        formulas: Optional[list[dict[str, Any]]],
        diagrams: Optional[list[dict[str, Any]]],
        provider: Optional[LLMProvider],
    ) -> Optional[dict[str, Any]]:
        """Use AI for deeper classification when heuristics are uncertain."""
        formula_text = ''
        if formulas:
            formula_text = 'Formulas: ' + ', '.join(
                f.get('latex', f.get('plain_text', '')) for f in formulas[:5]
            )

        diagram_text = ''
        if diagrams:
            diagram_text = 'Diagrams: ' + ', '.join(
                d.get('diagram_type', d.get('description', '')) for d in diagrams[:3]
            )

        prompt = f"""Classify this educational content.

Text: {text[:2000]}
{formula_text}
{diagram_text}

Return JSON:
{{
  "subject": "math|physics|chemistry|biology|coding|general",
  "topic": "specific chapter or topic name",
  "difficulty": "beginner|intermediate|advanced",
  "concepts": ["concept1", "concept2"],
  "learning_objective": "what the student should learn",
  "confidence": 0.0-1.0
}}"""

        try:
            gateway = await self._resolve_gateway()
            response = await gateway.execute(
                messages=[
                    {
                        'role': 'system',
                        'content': 'You classify educational content into subject, topic, difficulty, and concepts.',
                    },
                    {'role': 'user', 'content': prompt},
                ],
                provider=provider,
                expect_json=True,
                max_tokens=1024,
                temperature=0.3,
                use_cache=True,
            )

            parsed = json.loads(response.text) if isinstance(response.text, str) else response.text
            return {
                'subject': parsed.get('subject', 'general'),
                'topic': parsed.get('topic', 'general'),
                'difficulty': parsed.get('difficulty', 'intermediate'),
                'concepts': [str(c) for c in (parsed.get('concepts', []) or [])][:8],
                'learning_objective': parsed.get('learning_objective', ''),
                'confidence': float(parsed.get('confidence', 0.5)),
            }

        except Exception as exc:
            log.debug('ai_refine_failed', error=str(exc)[:80])
            return None

    @staticmethod
    def _fallback() -> dict[str, Any]:
        return {
            'subject': 'general',
            'topic': 'general',
            'difficulty': 'intermediate',
            'concepts': [],
            'learning_objective': '',
            'confidence': 0.0,
        }

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway
