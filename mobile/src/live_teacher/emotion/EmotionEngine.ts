// ──────────────────────────────────────────────────────────────────────────────
// EmotionEngine — enriches every teacher response with authentic emotion.
//
// Every teacher utterance and action carries emotion metadata: emotion type,
// intensity, duration, speech style, and a gesture hint. The engine selects
// appropriate emotions based on lesson phase, student performance, and
// conversation context.
// ──────────────────────────────────────────────────────────────────────────────

import type { EmotionType, EmotionState, SpeechStyle, LiveLessonPhase, LiveTeacherEvent } from '../types';

export interface EmotionEngineConfig {
  base_emotion: EmotionType;
  onEvent?: (event: LiveTeacherEvent) => void;
}

const DEFAULT_CONFIG: EmotionEngineConfig = {
  base_emotion: 'calmness',
};

const GESTURE_MAP: Record<EmotionType, string> = {
  encouragement: 'nod_smile',
  curiosity: 'head_tilt',
  excitement: 'hand_gesture_open',
  patience: 'gentle_nod',
  concern: 'lean_forward',
  celebration: 'clap_raise_hands',
  calmness: 'neutral_stand',
};

const SPEECH_STYLE_MAP: Record<EmotionType, SpeechStyle> = {
  encouragement: 'warm',
  curiosity: 'gentle',
  excitement: 'energetic',
  patience: 'gentle',
  concern: 'serious',
  celebration: 'playful',
  calmness: 'warm',
};

export class EmotionEngine {
  private _config: EmotionEngineConfig;
  private _current: EmotionState;
  private _listeners: Set<(emotion: EmotionState) => void> = new Set();

  constructor(config: Partial<EmotionEngineConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
    this._current = this._createEmotion(this._config.base_emotion, 0.5);
  }

  // ── State ──────────────────────────────────────────────────────────────

  get current(): EmotionState {
    return { ...this._current };
  }

  onUpdate(listener: (emotion: EmotionState) => void): () => void {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  // ── Emotion Selection ──────────────────────────────────────────────────

  setEmotion(emotion: EmotionType, intensity: number, durationMs?: number): void {
    this._current = this._createEmotion(emotion, intensity, durationMs);
    this._notify();
  }

  setFromPhase(phase: LiveLessonPhase): void {
    switch (phase) {
      case 'greeting':
        this._current = this._createEmotion('excitement', 0.7, 1500);
        break;
      case 'explaining':
        this._current = this._createEmotion('calmness', 0.6);
        break;
      case 'pointing':
        this._current = this._createEmotion('curiosity', 0.7);
        break;
      case 'writing':
        this._current = this._createEmotion('patience', 0.6);
        break;
      case 'pausing':
        this._current = this._createEmotion('curiosity', 0.8);
        break;
      case 'listening':
        this._current = this._createEmotion('patience', 0.8);
        break;
      case 'evaluating':
        this._current = this._createEmotion('curiosity', 0.6);
        break;
      case 'encouraging':
        this._current = this._createEmotion('encouragement', 0.9);
        break;
      case 'idle':
        this._current = this._createEmotion('calmness', 0.4);
        break;
      default:
        this._current = this._createEmotion('calmness', 0.5);
        break;
    }
    this._notify();
  }

  setFromStudentCorrectness(correct: boolean): void {
    if (correct) {
      this._current = this._createEmotion('celebration', 0.85, 2000);
    } else {
      this._current = this._createEmotion('encouragement', 0.8, 1500);
    }
    this._notify();
  }

  setFromInterruption(): void {
    this._current = this._createEmotion('patience', 0.9, 1000);
    this._notify();
  }

  setFromDoubts(): void {
    this._current = this._createEmotion('curiosity', 0.85, 1200);
    this._notify();
  }

  // ── Factory ────────────────────────────────────────────────────────────

  private _createEmotion(emotion: EmotionType, intensity: number, durationMs?: number): EmotionState {
    return {
      emotion,
      intensity: Math.max(0, Math.min(1, intensity)),
      duration_ms: durationMs ?? 1500,
      speech_style: SPEECH_STYLE_MAP[emotion],
      gesture_metadata: GESTURE_MAP[emotion],
    };
  }

  // ── Notify ─────────────────────────────────────────────────────────────

  private _notify(): void {
    const snapshot = this.current;
    for (const listener of this._listeners) {
      listener(snapshot);
    }
    this._config.onEvent?.({
      type: 'emotion:change',
      timestamp: Date.now(),
      data: snapshot,
    });
  }

  // ── Reset ──────────────────────────────────────────────────────────────

  reset(): void {
    this._current = this._createEmotion(this._config.base_emotion, 0.5);
    this._notify();
  }

  dispose(): void {
    this._listeners.clear();
  }
}
