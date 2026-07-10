// ──────────────────────────────────────────────────────────────────────────────
// LayeredRenderer — compositing layer system for the classroom.
//
// Renders in order:
//   1. Background (solid color / gradient)
//   2. Notebook (camera feed with homography warp)
//   3. Teacher Ink (pen strokes, board elements)
//   4. Highlights (animated highlights, underlines)
//   5. Pointer (laser/finger/pen pointer)
//   6. Animations (active animation overlays)
//   7. Widgets (speech bubble, progress bar, controls)
//   8. Speech Captions (text overlay)
//   9. Debug (developer overlay)
//
// Only changed layers are re-drawn (incremental rendering).
// Uses Skia Canvas for GPU-accelerated rendering.
// ──────────────────────────────────────────────────────────────────────────────

import type {
  DebugInfo,
  LayerName,
  PerformanceMetrics,
  Point,
  Rect,
} from '../types';

// ── Layer state ──────────────────────────────────────────────────────────────

interface LayerState {
  name: LayerName;
  zIndex: number;
  isVisible: boolean;
  needsRedraw: boolean;
  opacity: number;
}

const LAYER_ORDER: LayerName[] = [
  'background',
  'notebook',
  'teacher_ink',
  'highlights',
  'pointer',
  'animations',
  'widgets',
  'speech_captions',
  'debug',
];

// ── Performance tracking ─────────────────────────────────────────────────────

interface FrameTiming {
  timestamp: number;
  durationMs: number;
}

// ── LayeredRenderer ──────────────────────────────────────────────────────────

export class LayeredRenderer {
  private _layers: Map<LayerName, LayerState> = new Map();
  private _canvasSize: { width: number; height: number } = { width: 0, height: 0 };
  private _frameCount = 0;
  private _lastFpsUpdate = Date.now();
  private _currentFps = 60;

  // Frame timing ring buffer
  private _frameTimings: FrameTiming[] = [];
  private readonly _maxFrameTimings = 60;

  // Debug info accumulator
  private _debugInfo: DebugInfo = this._emptyDebugInfo();

  constructor() {
    this._initLayers();
  }

  // ── Layer management ───────────────────────────────────────────────────

  private _initLayers(): void {
    LAYER_ORDER.forEach((name, index) => {
      this._layers.set(name, {
        name,
        zIndex: index,
        isVisible: true,
        needsRedraw: true,
        opacity: 1,
      });
    });
  }

  setLayerVisibility(name: string, visible: boolean): void {
    const layer = this._layers.get(name as LayerName);
    if (layer) {
      layer.isVisible = visible;
      layer.needsRedraw = true;
    }
  }

  setLayerOpacity(name: string, opacity: number): void {
    const layer = this._layers.get(name as LayerName);
    if (layer) {
      layer.opacity = Math.max(0, Math.min(1, opacity));
      layer.needsRedraw = true;
    }
  }

  getLayer(name: LayerName): LayerState | undefined {
    return this._layers.get(name);
  }

  requestRedraw(layerName?: string): void {
    if (layerName) {
      const layer = this._layers.get(layerName as LayerName);
      if (layer) {
        layer.needsRedraw = true;
      }
    } else {
      this._layers.forEach((l) => {
        l.needsRedraw = true;
      });
    }
  }

  // ── Rendering (called by Skia Canvas on each frame) ────────────────────

  beginFrame(canvasSize: { width: number; height: number }): void {
    this._canvasSize = canvasSize;
    this._trackFrameTiming();

    // Reset redraw flags for visible, non-changed layers
    // (Callers mark dirty via requestRedraw)
    this._updateFps();
  }

  /** Render all visible layers in order. Returns the ordered list for the Skia canvas. */
  getVisibleLayers(): Array<{ name: LayerName; opacity: number; needsRedraw: boolean }> {
    const result: Array<{ name: LayerName; opacity: number; needsRedraw: boolean }> = [];

    for (const name of LAYER_ORDER) {
      const layer = this._layers.get(name);
      if (layer && layer.isVisible) {
        result.push({
          name: layer.name,
          opacity: layer.opacity,
          needsRedraw: layer.needsRedraw,
        });
      }
    }

    return result;
  }

  /** Called after rendering to clear redraw flags. */
  endFrame(): void {
    this._layers.forEach((l) => {
      l.needsRedraw = false;
    });
  }

  getCanvasSize(): { width: number; height: number } {
    return this._canvasSize;
  }

  /** Transform a normalized (0..1) point to canvas pixel coordinates. */
  normalizePoint(p: Point): Point {
    return {
      x: p.x * this._canvasSize.width,
      y: p.y * this._canvasSize.height,
    };
  }

  /** Transform canvas pixels to normalized (0..1) coordinates. */
  denormalizePoint(p: Point): Point {
    return {
      x: this._canvasSize.width > 0 ? p.x / this._canvasSize.width : 0,
      y: this._canvasSize.height > 0 ? p.y / this._canvasSize.height : 0,
    };
  }

  /** Clip a normalized rect to the canvas. */
  clipRect(rect: Rect, margin = 0): Rect {
    return {
      x: Math.max(-margin, rect.x),
      y: Math.max(-margin, rect.y),
      width: Math.min(this._canvasSize.width + margin, rect.width),
      height: Math.min(this._canvasSize.height + margin, rect.height),
    };
  }

  // ── Performance ────────────────────────────────────────────────────────

  getPerformanceMetrics(): PerformanceMetrics {
    const avgFrameTime = this._frameTimings.length > 0
      ? this._frameTimings.reduce((s, f) => s + f.durationMs, 0) / this._frameTimings.length
      : 0;

    return {
      fps: this._currentFps,
      frame_time_ms: Math.round(avgFrameTime * 100) / 100,
      render_latency_ms: 0,
      tracking_latency_ms: 0,
      streaming_latency_ms: 0,
      memory_mb: 0,
      layer_count: this._layers.size,
    };
  }

  setDebugInfo(info: Partial<DebugInfo>): void {
    this._debugInfo = { ...this._debugInfo, ...info };
  }

  getDebugInfo(): DebugInfo {
    return this._debugInfo;
  }

  getLayerCount(): number {
    return this._layers.size;
  }

  // ── Internals ──────────────────────────────────────────────────────────

  private _trackFrameTiming(): void {
    const now = Date.now();
    if (this._frameTimings.length > 0) {
      const lastFrame = this._frameTimings[this._frameTimings.length - 1];
      const duration = now - lastFrame.timestamp;
      this._frameTimings.push({ timestamp: now, durationMs: duration });
    } else {
      this._frameTimings.push({ timestamp: now, durationMs: 16 }); // Assume 60fps initially
    }

    if (this._frameTimings.length > this._maxFrameTimings) {
      this._frameTimings.shift();
    }

    this._frameCount++;
  }

  private _updateFps(): void {
    const now = Date.now();
    if (now - this._lastFpsUpdate >= 1000) {
      // Count frames in the last second
      const oneSecondAgo = now - 1000;
      const framesInLastSecond = this._frameTimings.filter(
        (f) => f.timestamp >= oneSecondAgo,
      ).length;
      this._currentFps = framesInLastSecond;
      this._lastFpsUpdate = now;
    }
  }

  private _emptyDebugInfo(): DebugInfo {
    return {
      tracking: { quality: 'lost', confidence: 0, corner_count: 0, homography_valid: false },
      scene_graph: { node_count: 0, edge_count: 0, last_update: 0 },
      board: { element_count: 0, layer_count: 0, current_stroke_count: 0 },
      timeline: { state: 'idle', current_index: 0, progress: 0, event_count: 0 },
      pointer: { mode: 'finger', position: { x: 0, y: 0 }, is_visible: true },
      streaming: { connected: false, latency_ms: 0, messages_sent: 0, messages_received: 0 },
      performance: this.getPerformanceMetrics(),
    };
  }
}
