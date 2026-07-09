"""Image Region Detector — detects and segments problem regions.

Identifies the problem area within an uploaded image. Returns bounding
box coordinates so the OCR engine can focus on the relevant region.
Uses OpenCV fallback when available.
"""

from __future__ import annotations

from typing import Optional

from app.core.logger import get_logger

log = get_logger(__name__)


class RegionDetector:
    """Detects the problem region within an image.

    Usage::

        detector = RegionDetector()
        region = detector.detect(image_array)
        # region is (x, y, width, height) or full image if no region found
    """

    def __init__(self) -> None:
        self._cv2_available = False
        self._check_dependencies()

    def _check_dependencies(self) -> None:
        """Check if OpenCV is available."""
        try:
            import cv2  # noqa: F401
            self._cv2_available = True
        except ImportError:
            self._cv2_available = False
            log.info('detector_cv2_not_available')

    def detect(self, image_array: 'array') -> tuple[int, int, int, int]:
        """Detect the problem region in the image.

        Args:
            image_array: Numpy array of the image (H, W, C).

        Returns:
            (x, y, width, height) bounding box. Returns full image
            dimensions if detection fails.
        """
        if not self._cv2_available or image_array is None:
            return self._fallback(image_array)

        try:
            import cv2
            import numpy as np

            gray = cv2.cvtColor(image_array, cv2.COLOR_BGR2GRAY)
            thresh = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 11, 2,
            )

            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                return self._fallback(image_array)

            # Find the largest contour (assumed to be the problem region)
            largest = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest)

            # Filter out tiny regions
            h_img, w_img = image_array.shape[:2]
            if w * h < w_img * h_img * 0.01:
                return self._fallback(image_array)

            # Add padding
            pad_x = int(w * 0.05)
            pad_y = int(h * 0.05)
            x = max(0, x - pad_x)
            y = max(0, y - pad_y)
            w = min(w_img - x, w + pad_x * 2)
            h = min(h_img - y, h + pad_y * 2)

            return (x, y, w, h)

        except Exception as exc:
            log.warning('detector_cv2_failed', error=str(exc)[:100])
            return self._fallback(image_array)

    def _fallback(self, image_array: Optional['array']) -> tuple[int, int, int, int]:
        """Return full image dimensions as the default region."""
        if image_array is not None:
            try:
                h, w = image_array.shape[:2]
                return (0, 0, w, h)
            except Exception:
                pass
        return (0, 0, 0, 0)
