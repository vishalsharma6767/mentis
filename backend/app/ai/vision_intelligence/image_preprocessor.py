"""Image Preprocessor — enhances raw camera frames for downstream vision.

Pipeline entry point. Transforms the raw camera image so every
downstream module receives a clean, standardised input.

Operations applied in order:
  1. Decode + convert to grayscale / RGB
  2. Adaptive brightness and contrast equalisation (CLAHE)
  3. Noise removal (bilateral filter)
  4. Skew detection and correction (deskew)
  5. Shadow removal (top-hat transform)
  6. Blur detection (Laplacian variance)
  7. Global quality scoring
  8. Rejection of unusable images
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from app.ai.vision_intelligence.schema import ImageQuality
from app.core.logger import get_logger

log = get_logger(__name__)

# Quality thresholds
MIN_BRIGHTNESS = 0.15
MAX_BRIGHTNESS = 0.95
MIN_CONTRAST = 0.10
MIN_SHARPNESS_VARIANCE = 50.0
MAX_NOISE_SCORE = 0.6
MIN_QUALITY_PASS = 0.35


class ImagePreprocessor:
    """Enhances and validates raw camera images.

    Usage::

        pre = ImagePreprocessor()
        result = await pre.process(image_array)
        if result.quality.is_acceptable:
            clean = result['image']
        else:
            # ask student to recapture
    """

    def __init__(self) -> None:
        self._stats: dict[str, float] = {}

    async def process(self, image: np.ndarray) -> dict[str, Any]:
        """Process a raw camera image and return enhanced version + quality.

        Args:
            image: Raw image as numpy array (H, W, C) in BGR or RGB.

        Returns:
            Dict with keys:
              - 'image': preprocessed image array
              - 'quality': ImageQuality assessment
              - 'processing_time_ms': elapsed milliseconds
        """
        import time
        t0 = time.monotonic()

        if image is None or image.size == 0:
            return self._reject('Empty image received')

        if cv2 is None:
            return {
                'image': image,
                'quality': ImageQuality(
                    brightness=0.5, contrast=0.3, sharpness=0.5,
                    blur_score=1.0, noise_level=0.1, overall_score=0.5,
                    is_acceptable=True, rejection_reason='',
                ),
                'processing_time_ms': 0,
            }

        log.info('preprocessor_start', shape=image.shape)

        # Ensure 3-channel RGB
        if len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)

        original = image.copy()

        # 1. Quality assessment on original
        quality = self._assess_quality(original)

        if not quality.is_acceptable:
            elapsed = (time.monotonic() - t0) * 1000
            return {
                'image': original,
                'quality': quality,
                'processing_time_ms': int(elapsed),
            }

        # 2. Shadow removal
        image = self._remove_shadows(image)

        # 3. Brightness and contrast enhancement
        image = self._enhance_contrast(image)

        # 4. Noise removal
        image = self._denoise(image)

        # 5. Deskew
        image, skew = self._deskew(image)
        quality.skew_angle_degrees = skew

        elapsed = (time.monotonic() - t0) * 1000
        log.info(
            'preprocessor_complete',
            elapsed_ms=int(elapsed),
            quality=round(quality.overall_score, 3),
        )

        return {
            'image': image,
            'quality': quality,
            'processing_time_ms': int(elapsed),
        }

    # ── Quality assessment ───────────────────────────────────────────────

    def _assess_quality(self, image: np.ndarray) -> ImageQuality:
        """Score image quality across multiple dimensions."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        brightness = float(np.mean(gray)) / 255.0
        contrast = float(np.std(gray)) / 128.0
        blur_var = self._laplacian_variance(gray)
        sharpness = min(blur_var / 500.0, 1.0)
        noise = self._estimate_noise(gray)

        is_blurry = blur_var < MIN_SHARPNESS_VARIANCE
        is_dark = brightness < MIN_BRIGHTNESS
        is_washed = brightness > MAX_BRIGHTNESS
        is_low_contrast = contrast < MIN_CONTRAST
        is_noisy = noise > MAX_NOISE_SCORE

        reasons: list[str] = []
        if is_blurry:
            reasons.append(f'Image is blurry (variance={blur_var:.1f})')
        if is_dark:
            reasons.append('Image is too dark')
        if is_washed:
            reasons.append('Image is overexposed')
        if is_low_contrast:
            reasons.append('Image has very low contrast')
        if is_noisy:
            reasons.append('Image has excessive noise')

        # Weighted overall score
        overall = (
            brightness * 0.20 +
            contrast * 0.25 +
            sharpness * 0.30 +
            (1.0 - noise) * 0.25
        )
        overall = max(0.0, min(1.0, overall))

        is_acceptable = overall >= MIN_QUALITY_PASS and len(reasons) <= 1

        self._stats = {
            'brightness': brightness,
            'contrast': contrast,
            'blur_variance': blur_var,
            'noise': noise,
            'overall': overall,
        }

        return ImageQuality(
            brightness=round(brightness, 3),
            contrast=round(contrast, 3),
            sharpness=round(sharpness, 3),
            blur_score=round(min(blur_var / 1000.0, 1.0), 3),
            noise_level=round(noise, 3),
            shadow_present=self._has_shadows(gray),
            overall_score=round(overall, 3),
            is_acceptable=is_acceptable,
            rejection_reason='; '.join(reasons) if reasons else '',
        )

    @staticmethod
    def _laplacian_variance(gray: np.ndarray) -> float:
        """Compute variance of Laplacian — blur detection metric."""
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        return float(np.var(lap))

    @staticmethod
    def _estimate_noise(gray: np.ndarray) -> float:
        """Estimate noise level using median deviation."""
        blurred = cv2.medianBlur(gray, 5)
        diff = cv2.absdiff(gray, blurred)
        return float(np.mean(diff)) / 255.0

    @staticmethod
    def _has_shadows(gray: np.ndarray) -> bool:
        """Detect presence of strong shadows."""
        blurred = cv2.GaussianBlur(gray, (0, 0), 3)
        high = cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)
        shadow_mask = high < 30
        return float(np.sum(shadow_mask)) / shadow_mask.size > 0.05

    # ── Enhancement ──────────────────────────────────────────────────────

    @staticmethod
    def _remove_shadows(image: np.ndarray) -> np.ndarray:
        """Remove shadows using morphological top-hat transform."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        dilated = cv2.morphologyEx(gray, cv2.MORPH_DILATE, kernel)
        bg = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel)
        diff = cv2.absdiff(gray, bg)
        normalized = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX)
        return cv2.cvtColor(normalized, cv2.COLOR_GRAY2BGR)

    @staticmethod
    def _enhance_contrast(image: np.ndarray) -> np.ndarray:
        """Apply CLAHE for adaptive contrast enhancement."""
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b_ = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l_eq = clahe.apply(l)
        merged = cv2.merge([l_eq, a, b_])
        return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)

    @staticmethod
    def _denoise(image: np.ndarray) -> np.ndarray:
        """Remove noise while preserving edges."""
        return cv2.bilateralFilter(image, d=7, sigmaColor=50, sigmaSpace=50)

    @staticmethod
    def _deskew(image: np.ndarray) -> tuple[np.ndarray, float]:
        """Detect and correct skew angle.

        Returns (corrected_image, skew_degrees).
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.bitwise_not(gray)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thresh > 0))

        if len(coords) < 10:
            return image, 0.0

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) < 0.5:
            return image, 0.0

        h, w = image.shape[:2]
        centre = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(centre, angle, 1.0)
        corrected = cv2.warpAffine(
            image, matrix, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

        return corrected, round(angle, 2)

    @staticmethod
    def _reject(reason: str) -> dict[str, Any]:
        log.warning('preprocessor_reject', reason=reason)
        return {
            'image': np.zeros((100, 100, 3), dtype=np.uint8),
            'quality': ImageQuality(
                overall_score=0.0,
                is_acceptable=False,
                rejection_reason=reason,
            ),
            'processing_time_ms': 0,
        }


# Lazy import to avoid hard dependency at module level
try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore
    log.warning('OpenCV not available — ImagePreprocessor disabled')
