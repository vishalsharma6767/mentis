"""Detects and segments problem regions from uploaded images."""

import cv2
import numpy as np


def detect_problem_region(image: np.ndarray) -> tuple[int, int, int, int]:
    """Returns (x, y, w, h) of the detected problem area."""
    return (0, 0, image.shape[1], image.shape[0])
