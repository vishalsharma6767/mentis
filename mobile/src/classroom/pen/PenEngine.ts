// ──────────────────────────────────────────────────────────────────────────────
// PenEngine — teacher handwriting engine.
//
// Manages ink strokes with pressure simulation, stroke animation,
// and natural writing replay.  Every stroke can be replayed to give the
// impression the teacher is writing in real time.
// ──────────────────────────────────────────────────────────────────────────────

import type { InkPoint, InkStroke, Point } from '../types';

// ── Configuration ────────────────────────────────────────────────────────────

export interface PenEngineConfig {
  /** Default stroke width in logical pixels */
  defaultStrokeWidth: number;
  /** Minimum stroke width when pressure is 0 */
  minStrokeWidth: number;
  /** Maximum stroke width when pressure is 1 */
  maxStrokeWidth: number;
  /** How many points per second to sample */
  sampleRate: number;
  /** Smoothing factor for point positions (0=raw, 1=max smoothed) */
  smoothingFactor: number;
  /** Default replay speed multiplier */
  defaultReplaySpeed: number;
  /** Whether to simulate pressure variation automatically */
  autoPressure: boolean;
}

const DEFAULT_CONFIG: PenEngineConfig = {
  defaultStrokeWidth: 3,
  minStrokeWidth: 1,
  maxStrokeWidth: 8,
  sampleRate: 120,
  smoothingFactor: 0.3,
  defaultReplaySpeed: 1.5,
  autoPressure: true,
};

// ── PenEngine ────────────────────────────────────────────────────────────────

export class PenEngine {
  private _config: PenEngineConfig;
  private _activeStroke: InkPoint[] = [];
  private _isActive = false;
  private _strokeId: string | null = null;
  private _completedStrokes: InkStroke[] = [];
  private _nextStrokeId = 1;
  private _lastPoint: InkPoint | null = null;

  constructor(config: Partial<PenEngineConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── Stroke lifecycle ────────────────────────────────────────────────────

  startStroke(x: number, y: number, pressure = 0.5): void {
    if (this._isActive) {
      this.endStroke();
    }
    this._isActive = true;
    this._activeStroke = [];
    this._strokeId = this._generateStrokeId();

    const point: InkPoint = {
      x,
      y,
      pressure: this._config.autoPressure ? 0.6 : pressure,
      timestamp: Date.now(),
    };
    this._activeStroke.push(point);
    this._lastPoint = point;
  }

  continueStroke(x: number, y: number, pressure = 0.5): void {
    if (!this._isActive) return;

    const smoothed = this._smoothPoint(x, y);
    const point: InkPoint = {
      x: smoothed.x,
      y: smoothed.y,
      pressure: this._config.autoPressure
        ? this._simulatePressure(smoothed.x, smoothed.y)
        : pressure,
      timestamp: Date.now(),
    };
    this._activeStroke.push(point);
    this._lastPoint = point;
  }

  endStroke(): string | null {
    if (!this._isActive || !this._strokeId) return null;

    if (this._activeStroke.length < 2) {
      this._isActive = false;
      this._strokeId = null;
      return null;
    }

    const stroke: InkStroke = {
      id: this._strokeId,
      points: [...this._activeStroke],
      color: '#1a1a1a',
      stroke_width: this._config.defaultStrokeWidth,
      opacity: 1,
      is_replay: false,
      replay_speed: this._config.defaultReplaySpeed,
    };

    this._completedStrokes.push(stroke);
    this._isActive = false;
    const id = this._strokeId;
    this._strokeId = null;
    return id;
  }

  cancelStroke(): void {
    this._isActive = false;
    this._activeStroke = [];
    this._strokeId = null;
  }

  // ── Stroke management ───────────────────────────────────────────────────

  clear(): void {
    this._completedStrokes = [];
    this._activeStroke = [];
    this._isActive = false;
    this._strokeId = null;
  }

  removeStroke(id: string): boolean {
    const idx = this._completedStrokes.findIndex((s) => s.id === id);
    if (idx === -1) return false;
    this._completedStrokes.splice(idx, 1);
    return true;
  }

  getStroke(id: string): InkStroke | undefined {
    return this._completedStrokes.find((s) => s.id === id);
  }

  getCompletedStrokes(): InkStroke[] {
    return [...this._completedStrokes];
  }

  getActiveStrokePoints(): InkPoint[] {
    return [...this._activeStroke];
  }

  getActiveStrokeId(): string | null {
    return this._strokeId;
  }

  isActive(): boolean {
    return this._isActive;
  }

  strokeCount(): number {
    return this._completedStrokes.length;
  }

  // ── Replay ──────────────────────────────────────────────────────────────

  async replayStroke(strokeId: string, speed = 1.5): Promise<void> {
    const stroke = this._completedStrokes.find((s) => s.id === strokeId);
    if (!stroke) return;

    const replayStroke: InkStroke = {
      ...stroke,
      is_replay: true,
      replay_speed: speed,
    };

    const intervalMs = 1000 / this._config.sampleRate / speed;
    let pointIndex = 0;

    return new Promise((resolve) => {
      const replay = (): void => {
        if (pointIndex >= replayStroke.points.length) {
          resolve();
          return;
        }
        this._activeStroke.push(replayStroke.points[pointIndex]);
        pointIndex++;
        setTimeout(replay, intervalMs);
      };
      replay();
    });
  }

  async replayAllStrokes(speed = 1.5): Promise<void> {
    const ids = this._completedStrokes.map((s) => s.id);
    for (const id of ids) {
      await this.replayStroke(id, speed);
    }
  }

  // ── Ink physics ─────────────────────────────────────────────────────────

  setStrokeProperties(
    color: string,
    strokeWidth: number,
    opacity: number,
  ): void {
    this._config.defaultStrokeWidth = strokeWidth;
    // Update last stroke if active
    if (this._isActive && this._completedStrokes.length > 0) {
      const last = this._completedStrokes[this._completedStrokes.length - 1];
      last.color = color;
      last.stroke_width = strokeWidth;
      last.opacity = opacity;
    }
  }

  // ── Serialization ───────────────────────────────────────────────────────

  serialize(): string {
    return JSON.stringify({
      strokes: this._completedStrokes.map((s) => ({
        id: s.id,
        points: s.points,
        color: s.color,
        stroke_width: s.stroke_width,
        opacity: s.opacity,
      })),
      version: 1,
    });
  }

  deserialize(json: string): void {
    try {
      const data = JSON.parse(json);
      if (data.version === 1 && Array.isArray(data.strokes)) {
        this._completedStrokes = data.strokes.map(
          (s: Record<string, unknown>) =>
            ({
              ...s,
              is_replay: false,
              replay_speed: 1,
            }) as InkStroke,
        );
      }
    } catch {
      console.warn('[PenEngine] failed to deserialize strokes');
    }
  }

  // ── Private ─────────────────────────────────────────────────────────────

  private _generateStrokeId(): string {
    return `stroke_${Date.now()}_${this._nextStrokeId++}`;
  }

  private _smoothPoint(x: number, y: number): Point {
    if (!this._lastPoint) return { x, y };
    const s = this._config.smoothingFactor;
    return {
      x: x * (1 - s) + this._lastPoint.x * s,
      y: y * (1 - s) + this._lastPoint.y * s,
    };
  }

  private _simulatePressure(x: number, y: number): number {
    // Simulate natural pressure variation based on movement speed
    if (!this._lastPoint) return 0.5;
    const dx = x - this._lastPoint.x;
    const dy = y - this._lastPoint.y;
    const speed = Math.sqrt(dx * dx + dy * dy);
    // Faster movement = lighter touch
    const pressure = Math.max(0.2, Math.min(1, 1 - speed / 50));
    return pressure;
  }
}
