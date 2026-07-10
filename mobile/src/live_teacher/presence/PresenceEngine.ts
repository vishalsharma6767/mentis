// ──────────────────────────────────────────────────────────────────────────────
// PresenceEngine — generates metadata that makes the teacher feel alive.
//
// Produces real-time presence data: greeting, eye-contact flags, teaching rhythm
// decisions, natural pause durations, confidence/warmth/attention/curiosity/
// encouragement levels. This metadata is consumed by the UI renderer, speech
// system, animation engine, and pointer engine.
// ──────────────────────────────────────────────────────────────────────────────

import type {
  PresenceState,
  TeachingRhythm,
  LiveLessonPhase,
  EmotionType,
  LiveTeacherEvent,
} from '../types';

export interface PresenceEngineConfig {
  base_confidence: number;
  base_warmth: number;
  update_interval_ms: number;
  onEvent?: (event: LiveTeacherEvent) => void;
}

const DEFAULT_CONFIG: PresenceEngineConfig = {
  base_confidence: 0.85,
  base_warmth: 0.9,
  update_interval_ms: 200,
};

export class PresenceEngine {
  private _config: PresenceEngineConfig;
  private _state: PresenceState;
  private _listeners: Set<(state: PresenceState) => void> = new Set();
  private _interval: ReturnType<typeof setInterval> | null = null;

  constructor(config: Partial<PresenceEngineConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
    this._state = this._defaultState();
  }

  // ── Default State ──────────────────────────────────────────────────────

  private _defaultState(): PresenceState {
    return {
      greeting: undefined,
      eye_contact: true,
      teaching_rhythm: 'normal',
      natural_pause_ms: 400,
      thinking_pause_ms: 600,
      confidence: this._config.base_confidence,
      warmth: this._config.base_warmth,
      attention: 0.9,
      curiosity: 0.7,
      encouragement: 0.5,
    };
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────

  start(): void {
    if (this._interval) return;
    this._interval = setInterval(() => {
      this._decay();
    }, this._config.update_interval_ms);
  }

  stop(): void {
    if (this._interval) {
      clearInterval(this._interval);
      this._interval = null;
    }
  }

  // ── State Access ───────────────────────────────────────────────────────

  get state(): PresenceState {
    return { ...this._state };
  }

  onUpdate(listener: (state: PresenceState) => void): () => void {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  // ── Modifiers ──────────────────────────────────────────────────────────

  setGreeting(greeting: string): void {
    this._state.greeting = greeting;
    this._notify();
  }

  setEyeContact(value: boolean): void {
    this._state.eye_contact = value;
    this._notify();
  }

  setRhythm(rhythm: TeachingRhythm): void {
    this._state.teaching_rhythm = rhythm;
    this._updatePauseFromRhythm();
    this._notify();
  }

  setConfidence(value: number): void {
    this._state.confidence = Math.max(0, Math.min(1, value));
    this._notify();
  }

  setWarmth(value: number): void {
    this._state.warmth = Math.max(0, Math.min(1, value));
    this._notify();
  }

  setAttention(value: number): void {
    this._state.attention = Math.max(0, Math.min(1, value));
    this._notify();
  }

  setCuriosity(value: number): void {
    this._state.curiosity = Math.max(0, Math.min(1, value));
    this._notify();
  }

  setEncouragement(value: number): void {
    this._state.encouragement = Math.max(0, Math.min(1, value));
    this._notify();
  }

  // ── Phase-Based Updates ────────────────────────────────────────────────

  onPhaseChange(phase: LiveLessonPhase): void {
    switch (phase) {
      case 'greeting':
        this.setWarmth(0.95);
        this.setConfidence(0.9);
        this.setRhythm('normal');
        break;
      case 'explaining':
        this.setConfidence(0.85);
        this.setCuriosity(0.6);
        this.setRhythm('normal');
        break;
      case 'pointing':
        this.setAttention(0.95);
        this.setRhythm('slow');
        break;
      case 'writing':
        this.setAttention(0.9);
        this.setRhythm('slow');
        break;
      case 'pausing':
        this.setCuriosity(0.8);
        this.setWarmth(0.9);
        this.setRhythm('pause');
        break;
      case 'listening':
        this.setEyeContact(true);
        this.setPatience();
        break;
      case 'evaluating':
        this.setCuriosity(0.75);
        this.setRhythm('pause');
        break;
      case 'encouraging':
        this.setEncouragement(0.95);
        this.setWarmth(0.95);
        this.setRhythm('normal');
        break;
      default:
        this.setRhythm('normal');
        break;
    }
  }

  onEmotion(emotion: EmotionType): void {
    switch (emotion) {
      case 'excitement':
        this.setWarmth(0.9);
        this.setCuriosity(0.8);
        this.setRhythm('fast');
        break;
      case 'celebration':
        this.setEncouragement(1.0);
        this.setWarmth(1.0);
        this.setConfidence(0.95);
        break;
      case 'patience':
        this.setRhythm('slow');
        this.setWarmth(0.9);
        break;
      case 'concern':
        this.setAttention(1.0);
        this.setCuriosity(0.9);
        this.setRhythm('slow');
        break;
      case 'calmness':
        this.setRhythm('normal');
        this.setWarmth(0.85);
        break;
      case 'encouragement':
        this.setEncouragement(0.9);
        this.setWarmth(0.9);
        break;
      case 'curiosity':
        this.setCuriosity(0.95);
        this.setRhythm('pause');
        break;
    }
  }

  // ── Natural Variation ──────────────────────────────────────────────────

  addNaturalVariation(): void {
    const jitter = () => (Math.random() - 0.5) * 0.08;
    this._state.confidence = Math.max(0.5, Math.min(1, this._state.confidence + jitter()));
    this._state.warmth = Math.max(0.5, Math.min(1, this._state.warmth + jitter()));
    this._state.attention = Math.max(0.5, Math.min(1, this._state.attention + jitter()));
  }

  // ── Private ────────────────────────────────────────────────────────────

  private setPatience(): void {
    const current = this._state.warmth;
    this._state.warmth = Math.min(1, current + 0.05);
    this._state.attention = Math.min(1, this._state.attention + 0.05);
  }

  private _updatePauseFromRhythm(): void {
    switch (this._state.teaching_rhythm) {
      case 'fast':
        this._state.natural_pause_ms = 200;
        this._state.thinking_pause_ms = 300;
        break;
      case 'normal':
        this._state.natural_pause_ms = 400;
        this._state.thinking_pause_ms = 600;
        break;
      case 'slow':
        this._state.natural_pause_ms = 800;
        this._state.thinking_pause_ms = 1000;
        break;
      case 'pause':
        this._state.natural_pause_ms = 1200;
        this._state.thinking_pause_ms = 1500;
        break;
    }
  }

  private _decay(): void {
    // Gentle decay toward baseline
    const baseline = this._config;
    this._state.confidence += (baseline.base_confidence - this._state.confidence) * 0.01;
    this._state.warmth += (baseline.base_warmth - this._state.warmth) * 0.01;
    this._state.encouragement = Math.max(0.3, this._state.encouragement - 0.005);
    this._state.curiosity = Math.max(0.3, this._state.curiosity - 0.003);
  }

  private _notify(): void {
    const snapshot = this.state;
    for (const listener of this._listeners) {
      listener(snapshot);
    }
    this._config.onEvent?.({
      type: 'presence:update',
      timestamp: Date.now(),
      data: snapshot,
    });
  }

  dispose(): void {
    this.stop();
    this._listeners.clear();
  }
}
