// ──────────────────────────────────────────────────────────────────────────────
// TimingEngine — synchronises all teacher output timelines.
//
// Manages a master clock that coordinates speech, pointer, pen, animations,
// highlights, board updates, and the lesson timeline. Supports play/pause/
// resume/skip/replay/slow/fast operations.
// ──────────────────────────────────────────────────────────────────────────────

import type {
  LessonSpeed,
  TimelineCommand,
  TimingState,
  TimedAction,
  LiveTeacherEvent,
} from '../types';

export type TimingClockListener = (state: TimingState) => void;
export type TimingActionListener = (action: TimedAction) => void;

export interface TimingEngineConfig {
  base_speed: LessonSpeed;
  tick_interval_ms: number;
  onEvent?: (event: LiveTeacherEvent) => void;
}

const DEFAULT_CONFIG: TimingEngineConfig = {
  base_speed: 'normal',
  tick_interval_ms: 16, // ~60fps
};

export class TimingEngine {
  private _config: TimingEngineConfig;
  private _state: TimingState;
  private _actions: TimedAction[] = [];
  private _clockListeners: Set<TimingClockListener> = new Set();
  private _actionListeners: Set<TimingActionListener> = new Set();
  private _interval: ReturnType<typeof setInterval> | null = null;
  private _speedMultiplier: Record<LessonSpeed, number> = {
    slow: 0.5,
    normal: 1.0,
    fast: 2.0,
  };

  constructor(config: Partial<TimingEngineConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
    this._state = {
      speed: this._config.base_speed,
      current_time_ms: 0,
      is_paused: false,
      is_playing: false,
    };
  }

  // ── Clock Control ──────────────────────────────────────────────────────

  play(): void {
    if (this._state.is_playing) return;
    this._state.is_playing = true;
    this._state.is_paused = false;
    this._startClock();
    this._notify();
    this._emitEvent('timing:state_change', { command: 'play' });
  }

  pause(): void {
    if (!this._state.is_playing || this._state.is_paused) return;
    this._state.is_paused = true;
    this._stopClock();
    this._notify();
    this._emitEvent('timing:state_change', { command: 'pause' });
  }

  resume(): void {
    if (!this._state.is_paused) return;
    this._state.is_paused = false;
    this._startClock();
    this._notify();
    this._emitEvent('timing:state_change', { command: 'resume' });
  }

  togglePause(): void {
    if (this._state.is_paused) {
      this.resume();
    } else {
      this.pause();
    }
  }

  stop(): void {
    this._state.is_playing = false;
    this._state.is_paused = false;
    this._state.current_time_ms = 0;
    this._stopClock();
    this._notify();
  }

  seek(timeMs: number): void {
    this._state.current_time_ms = Math.max(0, timeMs);
    this._evaluateActions();
    this._notify();
    this._emitEvent('timing:state_change', { command: 'seek', time_ms: timeMs });
  }

  skip(amountMs: number): void {
    this.seek(this._state.current_time_ms + amountMs);
  }

  replay(): void {
    this.seek(0);
    this._resetActions();
    if (!this._state.is_playing) {
      this.play();
    }
    this._emitEvent('timing:state_change', { command: 'replay' });
  }

  setSpeed(speed: LessonSpeed): void {
    this._state.speed = speed;
    this._notify();
    this._emitEvent('timing:state_change', { command: 'seek', speed });
  }

  // ── Actions ────────────────────────────────────────────────────────────

  scheduleAction(action: Omit<TimedAction, 'completed'>): void {
    const timed: TimedAction = { ...action, completed: false };
    this._actions.push(timed);
    this._actions.sort((a, b) => a.start_ms - b.start_ms);
    this._evaluateActions();
  }

  removeAction(actionId: string): void {
    this._actions = this._actions.filter((a) => a.action_id !== actionId);
  }

  clearActions(): void {
    this._actions = [];
  }

  getActions(): readonly TimedAction[] {
    return this._actions;
  }

  getPendingActions(): TimedAction[] {
    return this._actions.filter((a) => !a.completed && a.start_ms <= this._state.current_time_ms + 1000);
  }

  // ── State Access ───────────────────────────────────────────────────────

  get state(): TimingState {
    return { ...this._state };
  }

  get currentTimeMs(): number {
    return this._state.current_time_ms;
  }

  onClock(listener: TimingClockListener): () => void {
    this._clockListeners.add(listener);
    return () => this._clockListeners.delete(listener);
  }

  onAction(listener: TimingActionListener): () => void {
    this._actionListeners.add(listener);
    return () => this._actionListeners.delete(listener);
  }

  // ── Private ────────────────────────────────────────────────────────────

  private _startClock(): void {
    if (this._interval) return;
    this._interval = setInterval(() => {
      this._tick();
    }, this._config.tick_interval_ms);
  }

  private _stopClock(): void {
    if (this._interval) {
      clearInterval(this._interval);
      this._interval = null;
    }
  }

  private _tick(): void {
    if (!this._state.is_playing || this._state.is_paused) return;
    const delta = this._config.tick_interval_ms * this._speedMultiplier[this._state.speed];
    this._state.current_time_ms += delta;
    this._evaluateActions();
    this._notify();
  }

  private _evaluateActions(): void {
    const now = this._state.current_time_ms;
    for (const action of this._actions) {
      if (!action.completed && action.start_ms <= now) {
        action.completed = true;
        for (const listener of this._actionListeners) {
          listener(action);
        }
      }
    }
  }

  private _resetActions(): void {
    for (const action of this._actions) {
      action.completed = false;
    }
  }

  private _notify(): void {
    const snapshot = this.state;
    for (const listener of this._clockListeners) {
      listener(snapshot);
    }
  }

  private _emitEvent(type: LiveTeacherEvent['type'], data: Record<string, unknown>): void {
    this._config.onEvent?.({
      type,
      timestamp: Date.now(),
      data,
    });
  }

  dispose(): void {
    this.stop();
    this._clockListeners.clear();
    this._actionListeners.clear();
    this._actions = [];
  }
}
