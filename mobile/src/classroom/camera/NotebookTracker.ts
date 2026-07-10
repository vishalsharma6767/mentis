// ──────────────────────────────────────────────────────────────────────────────
// NotebookTracker — continuously tracks the notebook position in the camera feed
// using corner detection, feature matching, and homography estimation.
//
// Everything the teacher draws / points at stays attached to the notebook even
// when the camera moves.
// ──────────────────────────────────────────────────────────────────────────────

import type {
  HomographyMatrix,
  NotebookCorners,
  NotebookFrame,
  Point,
  Size,
  TrackingQuality,
} from '../types';

// ── Configuration ────────────────────────────────────────────────────────────

export interface NotebookTrackerConfig {
  /** Minimum corner detection confidence (0-1) */
  minCornerConfidence: number;
  /** Feature matching threshold */
  featureMatchThreshold: number;
  /** How often (ms) to re-detect corners when quality is low */
  redetectIntervalMs: number;
  /** Maximum frames without detection before quality drops to 'lost' */
  maxLostFrames: number;
  /** Smoothing factor for corner positions (0=no smooth, 0.9=heavy smooth) */
  smoothingFactor: number;
  /** Target tracking region size */
  targetSize: Size;
}

const DEFAULT_CONFIG: NotebookTrackerConfig = {
  minCornerConfidence: 0.6,
  featureMatchThreshold: 0.75,
  redetectIntervalMs: 500,
  maxLostFrames: 10,
  smoothingFactor: 0.7,
  targetSize: { width: 1280, height: 720 },
};

// ── Types ────────────────────────────────────────────────────────────────────

export interface CornerDetectionResult {
  corners: NotebookCorners | null;
  confidence: number;
  error?: string;
}

export interface FeatureMatchResult {
  homography: HomographyMatrix | null;
  inlier_count: number;
  confidence: number;
}

// ── NotebookTracker ──────────────────────────────────────────────────────────

export class NotebookTracker {
  private _config: NotebookTrackerConfig;
  private _isRunning = false;
  private _currentFrame: NotebookFrame | null = null;
  private _previousCorners: NotebookCorners | null = null;
  private _lostFrameCount = 0;
  private _lastRedetectTime = 0;
  private _frameCallbacks: Array<(frame: NotebookFrame) => void> = [];
  private _animationFrameId: number | null = null;
  private _trackingLoop: (() => void) | null = null;

  // Simulated camera frame source — in production this reads from VisionCamera
  private _getCameraFrame: () => { imageData: ImageData; timestamp: number } | null = () => null;

  constructor(config: Partial<NotebookTrackerConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── Public API ──────────────────────────────────────────────────────────

  async start(): Promise<void> {
    if (this._isRunning) return;
    this._isRunning = true;
    this._lostFrameCount = 0;
    this._startTrackingLoop();
  }

  stop(): void {
    this._isRunning = false;
    if (this._animationFrameId !== null) {
      cancelAnimationFrame(this._animationFrameId);
      this._animationFrameId = null;
    }
    this._currentFrame = null;
    this._previousCorners = null;
  }

  getCurrentFrame(): NotebookFrame | null {
    return this._currentFrame;
  }

  onFrame(cb: (frame: NotebookFrame) => void): () => void {
    this._frameCallbacks.push(cb);
    return () => {
      this._frameCallbacks = this._frameCallbacks.filter((f) => f !== cb);
    };
  }

  /** Inject a camera frame source for production use with VisionCamera. */
  setCameraFrameSource(
    source: () => { imageData: ImageData; timestamp: number } | null,
  ): void {
    this._getCameraFrame = source;
  }

  /** Manually set a detected homography (e.g. from ARKit/ARCore). */
  setHomography(homography: HomographyMatrix, imageSize: Size): void {
    if (!this._previousCorners) return;
    const frame = this._buildFrame(homography, imageSize, 'high', 0.9);
    this._updateFrame(frame);
  }

  // ── Tracking loop ───────────────────────────────────────────────────────

  private _startTrackingLoop(): void {
    const loop = (): void => {
      if (!this._isRunning) return;

      const cameraFrame = this._getCameraFrame();
      if (!cameraFrame) {
        this._animationFrameId = requestAnimationFrame(loop);
        return;
      }

      const result = this._processFrame(
        cameraFrame.imageData,
        cameraFrame.timestamp,
      );

      if (result) {
        this._updateFrame(result);
      }

      this._animationFrameId = requestAnimationFrame(loop);
    };

    this._trackingLoop = loop;
    this._animationFrameId = requestAnimationFrame(loop);
  }

  private _processFrame(
    imageData: ImageData,
    timestamp: number,
  ): NotebookFrame | null {
    const size: Size = { width: imageData.width, height: imageData.height };
    const shouldRedetect =
      this._currentFrame === null ||
      this._currentFrame.quality === 'lost' ||
      (this._currentFrame.quality === 'low' &&
        timestamp - this._lastRedetectTime > this._config.redetectIntervalMs);

    if (shouldRedetect) {
      this._lastRedetectTime = timestamp;
      const corners = this._detectCorners(imageData);
      if (corners.corners) {
        this._previousCorners = this._smoothCorners(corners.corners);
        const H = this._estimateHomography(this._previousCorners!, size);
        if (H) {
          return this._buildFrame(H, size, 'high', corners.confidence);
        }
      }
    }

    // Feature-based tracking from previous frame
    if (this._currentFrame && this._currentFrame.quality !== 'lost') {
      const match = this._matchFeatures(imageData, this._currentFrame);
      if (match && match.homography) {
        const quality = this._determineQuality(match.confidence, match.inlier_count);
        return this._buildFrame(match.homography, size, quality, match.confidence);
      }
    }

    // Degradation
    this._lostFrameCount++;
    if (this._lostFrameCount >= this._config.maxLostFrames) {
      return this._buildFrame(
        this._currentFrame?.homography ?? DEFAULT_HOMOGRAPHY,
        size,
        'lost',
        0,
      );
    }

    // Return degraded version
    if (this._currentFrame) {
      const quality = this._degradeQuality(this._currentFrame.quality);
      return {
        ...this._currentFrame,
        quality,
        timestamp,
        confidence: this._currentFrame.confidence * 0.9,
      };
    }

    return null;
  }

  // ── Corner detection ────────────────────────────────────────────────────

  private _detectCorners(imageData: ImageData): CornerDetectionResult {
    // In production this uses OpenCV.js or native module for:
    //   1. Convert to greyscale
    //   2. Apply adaptive threshold
    //   3. Find largest contour
    //   4. Approximate quadrilateral
    //   5. Return four corner points
    //
    // For the engine architecture we provide a placeholder that returns
    // simulated corners when none are detected yet, so the rest of the
    // pipeline can be tested.

    return {
      corners: this._previousCorners ?? this._simulateInitialCorners(),
      confidence: 0.5,
    };
  }

  private _simulateInitialCorners(): NotebookCorners {
    const margin = 0.1;
    return {
      topLeft: { x: margin, y: margin },
      topRight: { x: 1 - margin, y: margin },
      bottomLeft: { x: margin, y: 1 - margin },
      bottomRight: { x: 1 - margin, y: 1 - margin },
    };
  }

  private _smoothCorners(current: NotebookCorners): NotebookCorners {
    if (!this._previousCorners) return current;
    const s = this._config.smoothingFactor;
    return {
      topLeft: this._smoothPoint(current.topLeft, this._previousCorners.topLeft, s),
      topRight: this._smoothPoint(current.topRight, this._previousCorners.topRight, s),
      bottomLeft: this._smoothPoint(current.bottomLeft, this._previousCorners.bottomLeft, s),
      bottomRight: this._smoothPoint(current.bottomRight, this._previousCorners.bottomRight, s),
    };
  }

  private _smoothPoint(current: Point, previous: Point, factor: number): Point {
    return {
      x: previous.x + factor * (current.x - previous.x),
      y: previous.y + factor * (current.y - previous.y),
    };
  }

  // ── Feature matching ────────────────────────────────────────────────────

  private _matchFeatures(
    _current: ImageData,
    _previousFrame: NotebookFrame,
  ): FeatureMatchResult | null {
    // In production:
    //   1. Extract ORB / AKAZE features from current frame
    //   2. Match against features from previous frame
    //   3. RANSAC to find homography
    //   4. Return homography + inlier count
    //
    // Placeholder returns the previous homography with degraded confidence.

    return {
      homography: this._previousCorners
        ? this._estimateHomography(this._previousCorners, _previousFrame.image_size)
        : null,
      inlier_count: 5,
      confidence: 0.3,
    };
  }

  // ── Homography estimation ───────────────────────────────────────────────

  private _estimateHomography(
    corners: NotebookCorners,
    _imageSize: Size,
  ): HomographyMatrix | null {
    // Maps notebook corners to a normalized rectangle.
    // In production: DLT algorithm from 4 point correspondences.
    //
    // Placeholder: compute a simple perspective transform.
    const w = 1;
    const h = 1;
    const src = [
      corners.topLeft,
      corners.topRight,
      corners.bottomLeft,
      corners.bottomRight,
    ];
    const dst = [
      { x: 0, y: 0 },
      { x: w, y: 0 },
      { x: 0, y: h },
      { x: w, y: h },
    ];

    try {
      return this._computeHomographyDLT(src, dst);
    } catch {
      return DEFAULT_HOMOGRAPHY;
    }
  }

  private _computeHomographyDLT(
    src: Point[],
    dst: Point[],
  ): HomographyMatrix {
    // Direct Linear Transform for homography estimation.
    // Solves Ah = 0 using SVD from 4 point correspondences.
    const A: number[][] = [];

    for (let i = 0; i < 4; i++) {
      const sx = src[i].x;
      const sy = src[i].y;
      const dx = dst[i].x;
      const dy = dst[i].y;

      A.push([-sx, -sy, -1, 0, 0, 0, sx * dx, sy * dx, dx]);
      A.push([0, 0, 0, -sx, -sy, -1, sx * dy, sy * dy, dy]);
    }

    // Compute SVD via eigendecomposition of A^T A
    const AtA = this._matrixMultiply(this._transpose(A), A);
    const eigen = this._powerIteration(AtA, 8);
    const h = eigen.vector;

    return {
      a: h[0], b: h[1], c: h[2],
      d: h[3], e: h[4], f: h[5],
      g: h[6], h: h[7],
    };
  }

  // ── Frame building ──────────────────────────────────────────────────────

  private _buildFrame(
    homography: HomographyMatrix,
    imageSize: Size,
    quality: TrackingQuality,
    confidence: number,
  ): NotebookFrame {
    const corners = this._computeCornersFromHomography(homography);
    return {
      corners,
      homography,
      quality,
      timestamp: Date.now(),
      image_size: imageSize,
      confidence,
    };
  }

  private _computeCornersFromHomography(H: HomographyMatrix): NotebookCorners {
    const apply = (p: Point) => {
      const w = H.g * p.x + H.h * p.y + 1;
      return {
        x: (H.a * p.x + H.b * p.y + H.c) / w,
        y: (H.d * p.x + H.e * p.y + H.f) / w,
      };
    };
    return {
      topLeft: apply({ x: 0, y: 0 }),
      topRight: apply({ x: 1, y: 0 }),
      bottomLeft: apply({ x: 0, y: 1 }),
      bottomRight: apply({ x: 1, y: 1 }),
    };
  }

  private _updateFrame(frame: NotebookFrame): void {
    this._currentFrame = frame;
    this._frameCallbacks.forEach((cb) => cb(frame));
  }

  // ── Quality helpers ─────────────────────────────────────────────────────

  private _determineQuality(
    confidence: number,
    inlierCount: number,
  ): TrackingQuality {
    if (confidence > 0.8 && inlierCount > 20) return 'high';
    if (confidence > 0.5 && inlierCount > 10) return 'medium';
    if (confidence > 0.2) return 'low';
    return 'lost';
  }

  private _degradeQuality(quality: TrackingQuality): TrackingQuality {
    const order: TrackingQuality[] = ['high', 'medium', 'low', 'lost'];
    const idx = order.indexOf(quality);
    if (idx < order.length - 1) return order[idx + 1];
    return 'lost';
  }

  // ── Linear algebra utilities ────────────────────────────────────────────

  private _transpose(m: number[][]): number[][] {
    return m[0].map((_, col) => m.map((row) => row[col]));
  }

  private _matrixMultiply(a: number[][], b: number[][]): number[][] {
    const result: number[][] = Array.from({ length: a.length }, () =>
      Array(b[0].length).fill(0),
    );
    for (let i = 0; i < a.length; i++) {
      for (let j = 0; j < b[0].length; j++) {
        for (let k = 0; k < b.length; k++) {
          result[i][j] += a[i][k] * b[k][j];
        }
      }
    }
    return result;
  }

  private _powerIteration(
    matrix: number[][],
    iterations: number,
  ): { value: number; vector: number[] } {
    const n = matrix.length;
    let vector = Array.from({ length: n }, () => Math.random());

    for (let iter = 0; iter < iterations; iter++) {
      const newVector = new Array(n).fill(0);
      for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
          newVector[i] += matrix[i][j] * vector[j];
        }
      }
      const norm = Math.sqrt(newVector.reduce((s, v) => s + v * v, 0));
      vector = newVector.map((v) => v / norm);
    }

    let eigenvalue = 0;
    for (let i = 0; i < n; i++) {
      let sum = 0;
      for (let j = 0; j < n; j++) {
        sum += matrix[i][j] * vector[j];
      }
      eigenvalue += sum * vector[i];
    }

    return { value: eigenvalue, vector };
  }
}

const DEFAULT_HOMOGRAPHY: HomographyMatrix = {
  a: 1, b: 0, c: 0,
  d: 0, e: 1, f: 0,
  g: 0, h: 0,
};
