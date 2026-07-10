// ──────────────────────────────────────────────────────────────────────────────
// PointerEngine — teacher pointer system.
//
// Supports laser pointer, finger pointer, pen pointer, animated arrows,
// animated circles, and animated highlights.  Every pointer action is
// interpolated smoothly so it feels like the teacher is gesturing naturally.
//
// The pointer always operates in notebook-local coordinates (0..1 normalized)
// so it stays attached to the notebook even when the camera moves.
// ──────────────────────────────────────────────────────────────────────────────

import type { Point, PointerMode, PointerPath } from '../types';
import type { SharedValue } from 'react-native-reanimated';
import { useSharedValue, withTiming, withSpring } from 'react-native-reanimated';

// ── Configuration ────────────────────────────────────────────────────────────

export interface PointerEngineConfig {
  defaultMode: PointerMode;
  springStiffness: number;
  springDamping: number;
  laserColor: string;
  fingerColor: string;
  penColor: string;
  arrowColor: string;
  circleColor: string;
  highlightColor: string;
  defaultSize: number;
  pathHistoryLength: number;
}

const DEFAULT_CONFIG: PointerEngineConfig = {
  defaultMode: 'finger',
  springStiffness: 200,
  springDamping: 20,
  laserColor: '#ff4444',
  fingerColor: '#4488ff',
  penColor: '#22cc66',
  arrowColor: '#ffaa00',
  circleColor: '#ff6600',
  highlightColor: 'rgba(255, 255, 0, 0.3)',
  defaultSize: 8,
  pathHistoryLength: 100,
};

// ── Animated guide state ─────────────────────────────────────────────────────

interface AnimatedGuide {
  type: 'arrow' | 'circle' | 'highlight';
  id: string;
  startPoint: Point;
  endPoint: Point;
  progress: SharedValue<number>;
  is_active: SharedValue<boolean>;
}

// ── PointerEngine ────────────────────────────────────────────────────────────

export class PointerEngine {
  private _config: PointerEngineConfig;

  // Reactive state shared with Skia renderer
  public readonly mode: SharedValue<PointerMode>;
  public readonly position: SharedValue<Point>;
  public readonly isVisible: SharedValue<boolean>;
  public readonly color: SharedValue<string>;
  public readonly size: SharedValue<number>;

  // Path history for trails and debug visualization
  private _pathHistory: PointerPath[] = [];
  private _recentPoints: Point[] = [];
  private _activeGuides: AnimatedGuide[] = [];
  private _nextGuideId = 1;

  constructor(config: Partial<PointerEngineConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };

    this.mode = useSharedValue(this._config.defaultMode);
    this.position = useSharedValue<Point>({ x: 0.5, y: 0.5 });
    this.isVisible = useSharedValue(true);
    this.color = useSharedValue(this._config.fingerColor);
    this.size = useSharedValue(this._config.defaultSize);
  }

  // ── Mode control ────────────────────────────────────────────────────────

  setMode(mode: PointerMode): void {
    this.mode.value = mode;
    switch (mode) {
      case 'laser':
        this.color.value = this._config.laserColor;
        this.size.value = 3;
        break;
      case 'finger':
        this.color.value = this._config.fingerColor;
        this.size.value = this._config.defaultSize;
        break;
      case 'pen':
        this.color.value = this._config.penColor;
        this.size.value = 5;
        break;
      case 'arrow':
        this.color.value = this._config.arrowColor;
        this.size.value = 4;
        break;
      case 'circle':
        this.color.value = this._config.circleColor;
        this.size.value = 6;
        break;
      case 'highlight':
        this.color.value = this._config.highlightColor;
        this.size.value = 20;
        break;
    }
  }

  // ── Position control ────────────────────────────────────────────────────

  moveTo(x: number, y: number, animated = true): void {
    if (animated) {
      this.position.value = withSpring(
        { x, y },
        {
          stiffness: this._config.springStiffness,
          damping: this._config.springDamping,
        },
      );
    } else {
      this.position.value = { x, y };
    }

    this._recentPoints.push({ x, y });
    if (this._recentPoints.length > this._config.pathHistoryLength) {
      this._recentPoints.shift();
    }
  }

  moveToImmediate(x: number, y: number): void {
    this.position.value = { x, y };
  }

  tap(x: number, y: number): void {
    this.moveTo(x, y);
    // Briefly scale up to simulate a tap
    this.size.value = withTiming(this._config.defaultSize * 1.5, { duration: 100 });
    setTimeout(() => {
      this.size.value = withTiming(this._config.defaultSize, { duration: 200 });
    }, 100);
  }

  // ── Animated guides ─────────────────────────────────────────────────────

  drawArrow(from: Point, to: Point): string {
    const id = `guide_arrow_${this._nextGuideId++}`;
    const guide: AnimatedGuide = {
      type: 'arrow',
      id,
      startPoint: from,
      endPoint: to,
      progress: useSharedValue(0),
      is_active: useSharedValue(true),
    };
    guide.progress.value = withTiming(1, { duration: 500 });
    this._activeGuides.push(guide);
    setTimeout(() => {
      guide.is_active.value = false;
    }, 2000);
    return id;
  }

  drawCircle(center: Point, _radius: number): string {
    const id = `guide_circle_${this._nextGuideId++}`;
    const guide: AnimatedGuide = {
      type: 'circle',
      id,
      startPoint: center,
      endPoint: center,
      progress: useSharedValue(0),
      is_active: useSharedValue(true),
    };
    guide.progress.value = withTiming(1, { duration: 800 });
    this._activeGuides.push(guide);
    setTimeout(() => {
      guide.is_active.value = false;
    }, 3000);
    return id;
  }

  highlight(region: { x: number; y: number; width: number; height: number }): string {
    const id = `guide_highlight_${this._nextGuideId++}`;
    const guide: AnimatedGuide = {
      type: 'highlight',
      id,
      startPoint: { x: region.x, y: region.y },
      endPoint: { x: region.x + region.width, y: region.y + region.height },
      progress: useSharedValue(0),
      is_active: useSharedValue(true),
    };
    guide.progress.value = withTiming(1, { duration: 300 });
    this._activeGuides.push(guide);
    setTimeout(() => {
      guide.is_active.value = false;
    }, 4000);
    return id;
  }

  // ── State queries ───────────────────────────────────────────────────────

  hide(): void {
    this.isVisible.value = false;
  }

  show(): void {
    this.isVisible.value = true;
  }

  getPosition(): Point {
    return this.position.value;
  }

  getMode(): PointerMode {
    return this.mode.value;
  }

  getRecentPoints(): Point[] {
    return [...this._recentPoints];
  }

  getActiveGuides(): AnimatedGuide[] {
    return this._activeGuides.filter((g) => g.is_active.value);
  }

  clearGuides(): void {
    this._activeGuides.forEach((g) => {
      g.is_active.value = false;
    });
    this._activeGuides = [];
  }

  clearPath(): void {
    this._recentPoints = [];
  }

  // ── Path recording ──────────────────────────────────────────────────────

  startRecording(): void {
    this._pathHistory.push({
      points: [],
      timestamps: [],
      mode: this.mode.value,
    });
  }

  recordPoint(x: number, y: number): void {
    if (this._pathHistory.length === 0) return;
    const current = this._pathHistory[this._pathHistory.length - 1];
    current.points.push({ x, y });
    current.timestamps.push(Date.now());
  }

  stopRecording(): PointerPath | null {
    if (this._pathHistory.length === 0) return null;
    return this._pathHistory.pop() ?? null;
  }

  getPathHistory(): PointerPath[] {
    return [...this._pathHistory];
  }
}
