"""Vision Validator — validates scene predictions and handles low confidence.

Checks every component of the EducationalScene for:
  - Minimum confidence thresholds per module
  - Consistency between modules (e.g., formulas match subject)
  - Image quality acceptability
  - Overall scene reliability

When confidence is too low, the validator provides structured
rejection reasons so the frontend can request a better image.
"""

from __future__ import annotations

from typing import Any, Optional

from app.ai.vision_intelligence.schema import EducationalScene
from app.core.logger import get_logger

log = get_logger(__name__)

# ── Confidence thresholds ────────────────────────────────────────────────

MIN_OVERALL_CONFIDENCE = 0.35
MIN_OCR_CONFIDENCE = 0.30
MIN_CLASSIFICATION_CONFIDENCE = 0.30
MIN_LAYOUT_CONFIDENCE = 0.20
MIN_QUALITY_SCORE = 0.30


class VisionValidator:
    """Validates the EducationalScene and provides structured feedback.

    Usage::

        validator = VisionValidator()
        if validator.validate(scene):
            # scene is reliable enough to send to teacher
        else:
            reasons = validator.rejection_reasons
            # "Image too blurry", "OCR confidence too low", etc.
    """

    def __init__(self) -> None:
        self.rejection_reasons: set[str] = set()
        self._warnings: list[str] = []

    def validate(self, scene: EducationalScene) -> bool:
        """Validate the full scene against quality thresholds.

        Args:
            scene: The assembled EducationalScene.

        Returns:
            True if the scene passes all checks, False if any critical
            component fails.
        """
        self.rejection_reasons.clear()
        self._warnings.clear()

        log.info('validator_start', overall=scene.confidence.overall)

        # 1. Image quality check
        if not scene.image_quality.is_acceptable:
            self.rejection_reasons.add(scene.image_quality.rejection_reason or 'Image quality unacceptable')

        if scene.image_quality.overall_score < MIN_QUALITY_SCORE:
            self.rejection_reasons.add(f'Image quality too low ({scene.image_quality.overall_score:.2f})')

        # 2. Overall confidence
        if scene.confidence.overall < MIN_OVERALL_CONFIDENCE:
            self.rejection_reasons.add(
                f'Overall confidence too low ({scene.confidence.overall:.2f} < {MIN_OVERALL_CONFIDENCE})',
            )

        # 3. OCR confidence
        if scene.confidence.ocr > 0 and scene.confidence.ocr < MIN_OCR_CONFIDENCE:
            self.rejection_reasons.add(
                f'OCR confidence too low ({scene.confidence.ocr:.2f})',
            )

        # 4. Classification confidence
        if scene.confidence.classification > 0 and scene.confidence.classification < MIN_CLASSIFICATION_CONFIDENCE:
            self.rejection_reasons.add(
                f'Classification confidence too low ({scene.confidence.classification:.2f})',
            )

        # 5. Layout confidence
        if scene.confidence.layout > 0 and scene.confidence.layout < MIN_LAYOUT_CONFIDENCE:
            self._warnings.append('Layout analysis may be unreliable')

        # 6. Empty scene check
        if not scene.text_blocks and not scene.questions:
            self.rejection_reasons.add('No text or questions detected in image')

        # 7. Consistency: formulas should match subject
        if scene.formulas and scene.subject:
            self._check_formula_consistency(scene)

        # 8. Diagram reliability
        if scene.diagrams:
            low_conf_diagrams = [d for d in scene.diagrams if d.confidence < 0.4]
            if low_conf_diagrams:
                self._warnings.append(f'{len(low_conf_diagrams)} diagram(s) have low confidence')

        is_valid = len(self.rejection_reasons) == 0

        if not is_valid:
            log.warning(
                'validator_rejected',
                reasons=list(self.rejection_reasons),
                warnings=self._warnings,
            )
        elif self._warnings:
            log.info('validator_passed_with_warnings', warnings=self._warnings)

        log.info('validator_complete', is_valid=is_valid)
        return is_valid

    # ── Consistency checks ──────────────────────────────────────────────

    @staticmethod
    def _check_formula_consistency(scene: EducationalScene) -> None:
        """Check that formulas match the detected subject."""
        formula_subjects = {
            'physics': ['F=', 'E=', 'P=', 'V=', 'I=', 'R='],
            'chemistry': ['H₂O', 'CO₂', 'NaCl', 'CH₄', '→', '⇌'],
            'math': ['=', '+', '-', '×', '÷', '∫', '∑', '√', 'x²'],
        }

        formula_text = ' '.join(f.latex + ' ' + f.plain_text for f in scene.formulas)
        subject_str = scene.subject.value if hasattr(scene.subject, 'value') else str(scene.subject)

        expected_markers = formula_subjects.get(subject_str, [])
        if expected_markers:
            match_count = sum(1 for m in expected_markers if m in formula_text)
            if match_count == 0 and len(scene.formulas) > 0:
                log.debug(
                    'formula_subject_mismatch',
                    subject=subject_str,
                    formulas=formula_text[:100],
                )

    def get_rejection_message(self) -> str:
        """Get a user-facing message explaining why the image is rejected."""
        if not self.rejection_reasons:
            return ''

        reasons = list(self.rejection_reasons)[:3]
        message = 'Kripya dobara photo len. ' if any('blurr' in r.lower() for r in reasons) else ''
        message += 'Please capture a clearer image. '
        message += ' '.join(reasons)
        return message

    def get_warnings(self) -> list[str]:
        """Get non-critical warnings about the scene."""
        return self._warnings.copy()
