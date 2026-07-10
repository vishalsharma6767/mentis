// ──────────────────────────────────────────────────────────────────────────────
// SyncEngine — maintains precise synchronisation between all teacher subsystems.
//
// Monitors drift between speech, pointer, pen, animations, timeline, board,
// camera, and student input. Applies corrections when drift exceeds thresholds
// to ensure no component falls out of sync.
// ──────────────────────────────────────────────────────────────────────────────

import type { SyncState, LiveTeacherEvent } from '../types';

export interface SyncEngineConfig {
  max_allowed_drift_ms: number;
  correction_threshold_ms: number;
  check_interval_ms: number;
  onEvent?: (event: LiveTeacherEvent) => void;
}

const DEFAULT_CONFIG: SyncEngineConfig = {
  max_allowed_drift_ms: 50,
  correction_threshold_ms: 30,
  check_interval_ms: 100,
};

interface SyncSource {
  name: string;
  currentTimeMs: () => number;
}

export class SyncEngine {
  private _config: SyncEngineConfig;
  private _state: SyncState;
  private _sources: Map<string, SyncSource> = new Map();
  private _listeners: Set<(state: SyncState) => void> = new Set();
  private _interval: ReturnType<typeof setInterval> | null = null;
  private _correctionCallbacks: Array<(sourceName: string, correctionMs: number) => void> = [];

  constructor(config: Partial<SyncEngineConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
    this._state = {
      speech_offset_ms: 0,
      pointer_offset_ms: 0,
      board_offset_ms: 0,
      animation_offset_ms: 0,
      timeline_offset_ms: 0,
      drift_ms: 0,
      last_sync_at: Date.now(),
    };
  }

  // ── Source Registration ────────────────────────────────────────────────

  registerSource(name: string, timeFn: () => number): void {
    this._sources.set(name, { name, currentTimeMs: timeFn });
  }

  unregisterSource(name: string): void {
    this._sources.delete(name);
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────

  start(): void {
    if (this._interval) return;
    this._interval = setInterval(() => {
      this._checkSync();
    }, this._config.check_interval_ms);
  }

  stop(): void {
    if (this._interval) {
      clearInterval(this._interval);
      this._interval = null;
    }
  }

  // ── Corrections ────────────────────────────────────────────────────────

  onCorrection(callback: (sourceName: string, correctionMs: number) => void): () => void {
    this._correctionCallbacks.push(callback);
    return () => {
      this._correctionCallbacks = this._correctionCallbacks.filter((c) => c !== callback);
    };
  }

  applyCorrection(sourceName: string, offsetMs: number): void {
    switch (sourceName) {
      case 'speech':
        this._state.speech_offset_ms = offsetMs;
        break;
      case 'pointer':
        this._state.pointer_offset_ms = offsetMs;
        break;
      case 'board':
        this._state.board_offset_ms = offsetMs;
        break;
      case 'animation':
        this._state.animation_offset_ms = offsetMs;
        break;
      case 'timeline':
        this._state.timeline_offset_ms = offsetMs;
        break;
    }
    this._state.last_sync_at = Date.now();
    this._recalcDrift();
    this._notify();
  }

  // ── State Access ───────────────────────────────────────────────────────

  get state(): SyncState {
    return { ...this._state };
  }

  get isDrifting(): boolean {
    return Math.abs(this._state.drift_ms) > this._config.max_allowed_drift_ms;
  }

  onUpdate(listener: (state: SyncState) => void): () => void {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  // ── Private ────────────────────────────────────────────────────────────

  private _checkSync(): void {
    if (this._sources.size < 2) return;

    let minTime = Infinity;
    let maxTime = -Infinity;
    const times: Array<{ name: string; time: number }> = [];

    for (const source of this._sources.values()) {
      const time = source.currentTimeMs();
      times.push({ name: source.name, time });
      if (time < minTime) minTime = time;
      if (time > maxTime) maxTime = time;
    }

    const drift = maxTime - minTime;
    this._state.drift_ms = drift;
    this._state.last_sync_at = Date.now();

    if (drift > this._config.correction_threshold_ms) {
      const referenceTime = maxTime;
      for (const { name, time } of times) {
        const correction = referenceTime - time;
        if (correction > this._config.correction_threshold_ms) {
          this._applyCorrectionToSource(name, correction);
        }
      }
    }

    this._notify();

    if (drift > this._config.max_allowed_drift_ms) {
      this._config.onEvent?.({
        type: 'sync:drift',
        timestamp: Date.now(),
        data: { drift_ms: drift, max_allowed: this._config.max_allowed_drift_ms },
      });
    }
  }

  private _applyCorrectionToSource(name: string, correctionMs: number): void {
    for (const cb of this._correctionCallbacks) {
      cb(name, correctionMs);
    }
  }

  private _recalcDrift(): void {
    const offsets = [
      this._state.speech_offset_ms,
      this._state.pointer_offset_ms,
      this._state.board_offset_ms,
      this._state.animation_offset_ms,
      this._state.timeline_offset_ms,
    ];
    const max = Math.max(...offsets);
    const min = Math.min(...offsets);
    this._state.drift_ms = max - min;
  }

  private _notify(): void {
    const snapshot = this.state;
    for (const listener of this._listeners) {
      listener(snapshot);
    }
  }

  dispose(): void {
    this.stop();
    this._sources.clear();
    this._listeners.clear();
    this._correctionCallbacks = [];
  }
}
