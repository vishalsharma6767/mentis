// ──────────────────────────────────────────────────────────────────────────────
// GestureEngine — teacher gesture system.
//
// Gestures come from the Teacher Agent metadata and are rendered as
// animated visual cues on top of the notebook.  Each gesture has a
// type, position, duration, and intensity.
//
// Supported gestures: point, wave, tap, circle, underline, focus,
// highlight_region, count.
// ──────────────────────────────────────────────────────────────────────────────

import type { GestureAction, GestureType, Point } from '../types';
import type { SharedValue } from 'react-native-reanimated';
import {
  useSharedValue,
  withTiming,
  withSequence,
  withDelay,
  Easing,
} from 'react-native-reanimated';

// ── Configuration ────────────────────────────────────────────────────────────

export interface GestureConfig {
  defaultDurationMs: number;
  pointDurationMs: number;
  waveDurationMs: number;
  tapDurationMs: number;
  circleDurationMs: number;
  underlineDurationMs: number;
  focusDurationMs: number;
  pointColor: string;
  waveColor: string;
  tapColor: string;
  circleColor: string;
  underlineColor: string;
  focusColor: string;
}

const DEFAULT_CONFIG: GestureConfig = {
  defaultDurationMs: 800,
  pointDurationMs: 1200,
  waveDurationMs: 1500,
  tapDurationMs: 400,
  circleDurationMs: 1000,
  underlineDurationMs: 600,
  focusDurationMs: 2000,
  pointColor: '#ff4444',
  waveColor: '#4488ff',
  tapColor: '#ffaa00',
  circleColor: '#22cc66',
  underlineColor: '#ff6600',
  focusColor: 'rgba(255, 255, 0, 0.25)',
};

// ── Active gesture state ─────────────────────────────────────────────────────

interface ActiveGesture {
  type: GestureType;
  position: Point;
  progress: SharedValue<number>;
  opacity: SharedValue<number>;
  scale: SharedValue<number>;
  isActive: SharedValue<boolean>;
  resolve: (() => void) | null;
}

// ── GestureEngine ────────────────────────────────────────────────────────────

export class GestureEngine {
  private _config: GestureConfig;
  private _activeGestures: ActiveGesture[] = [];
  private _nextGestureId = 1;
  private _isPlaying = false;

  constructor(config: Partial<GestureConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── Public API ──────────────────────────────────────────────────────────

  async playGesture(gesture: GestureAction): Promise<void> {
    if (gesture.type === 'none') return;

    this._isPlaying = true;

    return new Promise<void>((resolve) => {
      switch (gesture.type) {
        case 'point':
          this._doPoint(gesture, resolve);
          break;
        case 'wave':
          this._doWave(gesture, resolve);
          break;
        case 'tap':
          this._doTap(gesture, resolve);
          break;
        case 'circle':
          this._doCircle(gesture, resolve);
          break;
        case 'underline':
          this._doUnderline(gesture, resolve);
          break;
        case 'focus':
          this._doFocus(gesture, resolve);
          break;
        case 'highlight_region':
          this._doHighlightRegion(gesture, resolve);
          break;
        case 'count':
          this._doCount(gesture, resolve);
          break;
        default:
          resolve();
          break;
      }
    });

    this._isPlaying = false;
  }

  cancelGesture(): void {
    this._activeGestures.forEach((g) => {
      g.isActive.value = false;
      g.resolve?.();
    });
    this._activeGestures = [];
    this._isPlaying = false;
  }

  isPlaying(): boolean {
    return this._isPlaying;
  }

  getActiveGestures(): ActiveGesture[] {
    return this._activeGestures.filter((g) => g.isActive.value);
  }

  // ── Gesture implementations ─────────────────────────────────────────────

  /** Quick flash at a point — "look here" */
  private _doPoint(gesture: GestureAction, resolve: () => void): void {
    const g = this._createGesture(gesture, this._config.pointDurationMs);
    g.opacity.value = withSequence(
      withTiming(1, { duration: 100 }),
      withTiming(0, { duration: this._config.pointDurationMs - 100 }),
    );
    g.scale.value = withSequence(
      withTiming(1.3, { duration: 200 }),
      withTiming(0.8, { duration: this._config.pointDurationMs - 200 }),
    );
    this._scheduleCleanup(g, this._config.pointDurationMs, resolve);
  }

  /** Side-to-side motion — "pay attention to this" */
  private _doWave(gesture: GestureAction, resolve: () => void): void {
    const g = this._createGesture(gesture, this._config.waveDurationMs);
    const waveCount = Math.max(1, Math.round(gesture.intensity * 4));
    const halfWave = this._config.waveDurationMs / waveCount / 2;

    const anims: number[] = [];
    for (let i = 0; i < waveCount; i++) {
      anims.push(15, -15);
    }
    // Wave using progress as horizontal offset
    const sequence = anims.map((offset, i) =>
      withDelay(i * halfWave, withTiming(offset, { duration: halfWave })),
    );
    g.progress.value = withSequence(...sequence);
    this._scheduleCleanup(g, this._config.waveDurationMs, resolve);
  }

  /** Quick pulse — "click here" */
  private _doTap(gesture: GestureAction, resolve: () => void): void {
    const g = this._createGesture(gesture, this._config.tapDurationMs);
    g.opacity.value = withSequence(
      withTiming(1, { duration: 50 }),
      withTiming(0.3, { duration: 100 }),
      withTiming(0, { duration: this._config.tapDurationMs - 150 }),
    );
    g.scale.value = withSequence(
      withTiming(1.5, { duration: 150 }),
      withTiming(0.9, { duration: this._config.tapDurationMs - 150 }),
    );
    this._scheduleCleanup(g, this._config.tapDurationMs, resolve);
  }

  /** Expanding ring — "this area" */
  private _doCircle(gesture: GestureAction, resolve: () => void): void {
    const g = this._createGesture(gesture, this._config.circleDurationMs);
    g.scale.value = withSequence(
      withTiming(2, {
        duration: this._config.circleDurationMs,
        easing: Easing.out(Easing.cubic),
      }),
    );
    g.opacity.value = withSequence(
      withTiming(1, { duration: 100 }),
      withTiming(0, {
        duration: this._config.circleDurationMs - 100,
        easing: Easing.in(Easing.cubic),
      }),
    );
    this._scheduleCleanup(g, this._config.circleDurationMs, resolve);
  }

  /** Line drawn under text — "this is important" */
  private _doUnderline(gesture: GestureAction, resolve: () => void): void {
    const g = this._createGesture(gesture, this._config.underlineDurationMs);
    g.progress.value = withTiming(1, {
      duration: this._config.underlineDurationMs,
      easing: Easing.out(Easing.cubic),
    });
    this._scheduleCleanup(g, this._config.underlineDurationMs, resolve);
  }

  /** Dim everything except a highlighted region — "focus here" */
  private _doFocus(gesture: GestureAction, resolve: () => void): void {
    const g = this._createGesture(gesture, this._config.focusDurationMs);
    g.opacity.value = withSequence(
      withTiming(0.6, { duration: 200 }),
      withDelay(
        this._config.focusDurationMs - 400,
        withTiming(0, { duration: 200 }),
      ),
    );
    this._scheduleCleanup(g, this._config.focusDurationMs, resolve);
  }

  /** Highlight a rectangular region */
  private _doHighlightRegion(gesture: GestureAction, resolve: () => void): void {
    const duration = gesture.duration_ms || this._config.focusDurationMs;
    const g = this._createGesture(gesture, duration);
    g.opacity.value = withSequence(
      withTiming(0.4, { duration: 200 }),
      withDelay(duration - 400, withTiming(0, { duration: 200 })),
    );
    this._scheduleCleanup(g, duration, resolve);
  }

  /** Count gestures (1, 2, 3... fingers) for enumerating items */
  private _doCount(gesture: GestureAction, resolve: () => void): void {
    const count = Math.max(1, Math.round((gesture.metadata?.count as number) ?? 1));
    const totalDuration = gesture.duration_ms || count * 500;
    const g = this._createGesture(gesture, totalDuration);
    g.progress.value = withTiming(count, { duration: totalDuration });
    this._scheduleCleanup(g, totalDuration, resolve);
  }

  // ── Helpers ─────────────────────────────────────────────────────────────

  private _createGesture(
    gesture: GestureAction,
    durationMs: number,
  ): ActiveGesture {
    const active: ActiveGesture = {
      type: gesture.type,
      position: gesture.position,
      progress: useSharedValue(0),
      opacity: useSharedValue(0),
      scale: useSharedValue(1),
      isActive: useSharedValue(true),
      resolve: null,
    };

    this._activeGestures.push(active);
    // Limit active gestures
    if (this._activeGestures.length > 10) {
      this._activeGestures.shift();
    }

    return active;
  }

  private _scheduleCleanup(
    gesture: ActiveGesture,
    delayMs: number,
    resolve: () => void,
  ): void {
    gesture.resolve = resolve;
    setTimeout(() => {
      gesture.isActive.value = false;
      // Remove from active list
      const idx = this._activeGestures.indexOf(gesture);
      if (idx !== -1) {
        this._activeGestures.splice(idx, 1);
      }
    }, delayMs + 50);
  }
}
