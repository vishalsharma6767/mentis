"""Integration adapter — bridges the Scene Graph system with the existing
Teacher Orchestrator, Planner, Recommendation Engine, Memory Engine,
Homework Agent, Quiz Agent, AR Planner, and Response Composer.

Every downstream module consumes the TeachingDecision, not the raw graph.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.scene_graph.builder import SceneGraphBuilder
from app.ai.scene_graph.concept_graph import ConceptGraphBuilder
from app.ai.scene_graph.graph import EducationalSceneGraph
from app.ai.scene_graph.reasoner import EducationalReasoner
from app.ai.scene_graph.schemas import (
    ConceptDependencies,
    StudentAttempt,
    TeacherFocus,
    TeachingDecision,
    TeachingPriority,
)
from app.ai.scene_graph.student_attempt import StudentAttemptAnalyzer
from app.ai.scene_graph.validator import SceneGraphValidator
from app.ai.gateway import AIGateway
from app.ai.vision_intelligence.schema import EducationalScene

logger = logging.getLogger(__name__)


class SceneGraphIntegration:
    """Top-level facade for the entire Scene Graph pipeline.

    The Teacher Orchestrator calls one method — ``process()`` — and
    receives a ``TeachingDecision``.  No graph internals are exposed.
    """

    def __init__(self, gateway: Optional[AIGateway] = None) -> None:
        self._gateway = gateway
        self._scene_builder = SceneGraphBuilder()
        self._validator = SceneGraphValidator(strict_mode=True)
        self._attempt_analyzer = StudentAttemptAnalyzer(gateway=gateway)
        self._concept_builder = ConceptGraphBuilder(gateway=gateway)
        self._reasoner = EducationalReasoner(gateway=gateway)

        # Caching state
        self._cache: dict[str, TeachingDecision] = {}

    # ── Primary pipeline ─────────────────────────────────────────────────

    async def process(
        self,
        scene: EducationalScene,
        scene_id: str = '',
        bypass_cache: bool = False,
    ) -> TeachingDecision:
        """Run the full Scene Graph pipeline on an EducationalScene.

        Args:
            scene: The structured scene from Vision Intelligence.
            scene_id: Optional unique scene identifier.
            bypass_cache: If True, rebuild even if cached.

        Returns:
            A TeachingDecision ready for the Teacher Orchestrator.
        """
        # Cache check
        cache_key = f'{scene_id or id(scene)}'
        if not bypass_cache and cache_key in self._cache:
            logger.debug('Returning cached TeachingDecision for %s', cache_key)
            return self._cache[cache_key]

        # 1. Build the scene graph
        graph = self._scene_builder.build(scene, scene_id=scene_id)

        # 2. Validate the graph
        try:
            self._validator.assert_valid(graph)
        except ValueError as exc:
            logger.warning('Scene graph validation failed: %s', exc)
            return self._fallback_decision(scene, str(exc))

        # 3. Analyze student attempts
        student_attempts = self._attempt_analyzer.analyze(graph)

        # 4. Build concept dependencies
        concept_deps = self._concept_builder.build(
            subject=scene.subject,
            topic=scene.topic,
            concepts=scene.concepts,
        )

        # 5. Reason over the graph
        decision = self._reasoner.reason(
            graph=graph,
            student_attempts=student_attempts,
            concept_deps=concept_deps,
        )

        # Cache
        self._cache[cache_key] = decision
        if len(self._cache) > 100:
            self._cache.clear()

        logger.info('Scene Graph pipeline complete: confidence=%.2f', decision.confidence)
        return decision

    def process_sync(
        self,
        scene: EducationalScene,
        scene_id: str = '',
    ) -> TeachingDecision:
        """Synchronous wrapper of the async pipeline.

        Intended for environments where async is unavailable.  For new
        code prefer the async ``process()`` method.
        """
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.process(scene, scene_id), loop,
            )
            return future.result(timeout=30)

        return asyncio.run(self.process(scene, scene_id))

    # ── Fallback ─────────────────────────────────────────────────────────

    def _fallback_decision(self, scene: EducationalScene, reason: str) -> TeachingDecision:
        """Return a safe fallback decision when the pipeline fails."""
        logger.warning('Returning fallback decision: %s', reason)
        return TeachingDecision(
            focus=TeacherFocus(
                current_focus='Review the problem step by step',
                learning_objective='Understand the core concept',
                visual_focus='Question text and given data',
                concept_to_teach=scene.topic,
                confidence=0.3,
            ),
            priority=TeachingPriority(
                immediate=[f'Read the question carefully'],
                next=[f'Identify known and unknown values'],
                revision=[c for c in scene.concepts[:2]],
            ),
            hints=['Start by writing what is given in the problem.'],
            confidence=0.3,
        )

    # ── Cache management ─────────────────────────────────────────────────

    def invalidate_cache(self, scene_id: Optional[str] = None) -> None:
        if scene_id:
            self._cache.pop(scene_id, None)
        else:
            self._cache.clear()
        logger.debug('SceneGraph cache invalidated')

    # ── Individual module access (for testing / advanced use) ────────────

    def build_graph(self, scene: EducationalScene, scene_id: str = '') -> EducationalSceneGraph:
        return self._scene_builder.build(scene, scene_id=scene_id)

    def validate_graph(self, graph: EducationalSceneGraph) -> bool:
        return self._validator.validate(graph).is_valid

    def analyze_attempts(self, graph: EducationalSceneGraph) -> list[StudentAttempt]:
        return self._attempt_analyzer.analyze(graph)

    def build_concept_graph(self, subject: str, topic: str, concepts: list[str]) -> ConceptDependencies:
        return self._concept_builder.build(subject, topic, concepts)
