"""Problem Parser — extracts structured data from problem text.

Parses raw OCR-extracted problem text into structured components:
  - Question text
  - Equations and formulas
  - Variables and their values
  - Problem type classification
  - Known/given values vs unknowns
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.ai.gateway import AIGateway, LLMProvider
from app.core.logger import get_logger

log = get_logger(__name__)

EQUATION_PATTERN = re.compile(r'[=<>]')
VARIABLE_PATTERN = re.compile(r'\b([a-zA-Z])\s*(?:\s*=\s*|[=<>])')
NUMBER_PATTERN = re.compile(r'\b\d+(?:\.\d+)?\b')


class ParsedProblem:
    """Structured representation of a parsed problem."""

    def __init__(
        self,
        question: str = '',
        equations: Optional[list[str]] = None,
        variables: Optional[dict[str, str]] = None,
        problem_type: str = 'general',
        given_values: Optional[dict[str, str]] = None,
        unknown: Optional[str] = None,
        confidence: float = 0.0,
    ) -> None:
        self.question = question
        self.equations = equations or []
        self.variables = variables or {}
        self.problem_type = problem_type
        self.given_values = given_values or {}
        self.unknown = unknown or ''
        self.confidence = confidence


class ProblemParser:
    """Parses problem text into structured components.

    Uses regex heuristics for fast extraction and falls back to
    AIGateway for complex problem structures.

    Usage::

        parser = ProblemParser()
        parsed = await parser.parse("Solve for x: 2x + 5 = 15")
        # parsed.question, parsed.equations, parsed.variables
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway

    async def parse(
        self,
        text: str,
        provider: Optional[LLMProvider] = None,
    ) -> ParsedProblem:
        """Parse raw problem text into structured components.

        Args:
            text: Raw problem text from OCR or user input.
            provider: Optional LLM provider override.

        Returns:
            ParsedProblem with structured fields.
        """
        if not text or not text.strip():
            return ParsedProblem(question='', confidence=0.0)

        # Fast heuristic parse
        heuristic = self._heuristic_parse(text)

        # If heuristic is confident enough, use it directly
        if heuristic.confidence >= 0.7:
            return heuristic

        # Otherwise use LLM for deeper parsing
        return await self._llm_parse(text, heuristic, provider) or heuristic

    def _heuristic_parse(self, text: str) -> ParsedProblem:
        """Quick regex-based problem parsing."""
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        equations: list[str] = []
        variables: dict[str, str] = {}

        for line in lines:
            if EQUATION_PATTERN.search(line):
                equations.append(line)
                vars_found = VARIABLE_PATTERN.findall(line)
                for v in vars_found:
                    if v not in variables:
                        variables[v] = '?'

        question = ' '.join(lines)
        if not equations:
            equations = [line for line in lines if NUMBER_PATTERN.search(line)]

        return ParsedProblem(
            question=question[:1000],
            equations=equations[:5],
            variables=variables,
            problem_type=self._detect_type(text),
            confidence=0.5 if equations else 0.2,
        )

    async def _llm_parse(
        self,
        text: str,
        heuristic: ParsedProblem,
        provider: Optional[LLMProvider],
    ) -> Optional[ParsedProblem]:
        """Use AIGateway for complex problem parsing."""
        gateway = await self._resolve_gateway()

        try:
            response = await gateway.execute(
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            'Parse this problem into structured components. '
                            'Return JSON with:\n'
                            '  question: string\n'
                            '  equations: [string]\n'
                            '  variables: {name: description}\n'
                            '  problem_type: string\n'
                            '  given_values: {name: value}\n'
                            '  unknown: string'
                        ),
                    },
                    {
                        'role': 'user',
                        'content': f'Problem:\n{text[:2000]}',
                    },
                ],
                provider=provider or LLMProvider.GROQ,
                expect_json=True,
                max_tokens=1024,
                temperature=0.3,
                use_cache=True,
            )

            parsed = json.loads(response.text)
            return ParsedProblem(
                question=str(parsed.get('question', heuristic.question))[:1000],
                equations=[str(e) for e in (parsed.get('equations', heuristic.equations) or [])],
                variables={str(k): str(v) for k, v in (parsed.get('variables', heuristic.variables) or {}).items()},
                problem_type=str(parsed.get('problem_type', heuristic.problem_type)),
                given_values={str(k): str(v) for k, v in (parsed.get('given_values', {}) or {}).items()},
                unknown=str(parsed.get('unknown', '')),
                confidence=0.8,
            )

        except Exception as exc:
            log.warning('parser_llm_failed', error=str(exc)[:100])
            return None

    @staticmethod
    def _detect_type(text: str) -> str:
        """Detect problem type from text patterns."""
        lower = text.lower()
        if any(w in lower for w in ['equation', 'solve', 'find x', 'find y']):
            return 'equation'
        if any(w in lower for w in ['graph', 'plot', 'axis', 'coordinate']):
            return 'graph'
        if any(w in lower for w in ['if', 'then', 'given that', 'suppose']):
            return 'word_problem'
        if any(w in lower for w in ['diagram', 'figure', 'shape', 'circle', 'triangle']):
            return 'diagram'
        if any(w in lower for w in ['def ', 'function', 'class ', 'print']):
            return 'code'
        return 'general'

    async def _resolve_gateway(self) -> AIGateway:
        if self._gateway is None:
            self._gateway = await AIGateway.get_instance()
        return self._gateway
