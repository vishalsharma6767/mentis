// ──────────────────────────────────────────────────────────────────────────────
// SpeechManager — TTS orchestration for the live teacher.
//
// Manages speech queue, emotion-aware TTS requests, speech state transitions.
// Integrates with the streaming and timing engines so speech can be paused,
// resumed, skipped, and synchronised with pointer/board/animations.
// ──────────────────────────────────────────────────────────────────────────────

import type {
  SpeechState,
  SpeechRequest,
  SpeechSegment,
  EmotionState,
  LiveTeacherEvent,
} from '../types';

export interface SpeechManagerConfig {
  tts_url: string;
  tts_voice: string;
  tts_language: string;
  max_queue_size: number;
  thinking_pause_ms: number;
  onEvent?: (event: LiveTeacherEvent) => void;
}

const DEFAULT_CONFIG: SpeechManagerConfig = {
  tts_url: '',
  tts_voice: 'hi-IN-Standard-A',
  tts_language: 'hi-IN',
  max_queue_size: 20,
  thinking_pause_ms: 600,
};

export class SpeechManager {
  private _config: SpeechManagerConfig;
  private _state: SpeechState = 'idle';
  private _queue: SpeechRequest[] = [];
  private _currentSegment: SpeechSegment | null = null;
  private _currentResolve: (() => void) | null = null;
  private _isSpeaking = false;
  private _stateListeners: Set<(state: SpeechState) => void> = new Set();

  constructor(config: Partial<SpeechManagerConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── State ──────────────────────────────────────────────────────────────

  get state(): SpeechState {
    return this._state;
  }

  set state(value: SpeechState) {
    if (this._state === value) return;
    this._state = value;
    for (const listener of this._stateListeners) {
      listener(value);
    }
  }

  isSpeaking(): boolean {
    return this._isSpeaking;
  }

  onStateChange(listener: (state: SpeechState) => void): () => void {
    this._stateListeners.add(listener);
    return () => this._stateListeners.delete(listener);
  }

  // ── Queue ──────────────────────────────────────────────────────────────

  enqueue(request: Omit<SpeechRequest, 'queue_position'>): void {
    if (this._queue.length >= this._config.max_queue_size) {
      return;
    }
    const req: SpeechRequest = {
      ...request,
      queue_position: this._queue.length,
    };
    this._queue.push(req);
    if (!this._isSpeaking) {
      this._processNext();
    }
  }

  enqueueFront(request: Omit<SpeechRequest, 'queue_position'>): void {
    const req: SpeechRequest = {
      ...request,
      queue_position: 0,
    };
    this._queue.unshift(req);
    if (!this._isSpeaking) {
      this._processNext();
    }
  }

  clearQueue(): void {
    this._queue = [];
    if (this._isSpeaking) {
      this._cancelCurrent();
    }
  }

  skip(): void {
    this._cancelCurrent();
    this._processNext();
  }

  // ── Thinking / Pausing ─────────────────────────────────────────────────

  async think(durationMs?: number): Promise<void> {
    this.state = 'thinking';
    const ms = durationMs ?? this._config.thinking_pause_ms;
    await new Promise((resolve) => setTimeout(resolve, ms));
    if (this._queue.length > 0) {
      this._processNext();
    } else {
      this.state = 'idle';
    }
  }

  async wait(durationMs: number): Promise<void> {
    this.state = 'waiting';
    await new Promise((resolve) => setTimeout(resolve, durationMs));
    if (this._queue.length > 0) {
      this._processNext();
    } else {
      this.state = 'idle';
    }
  }

  // ── Queue Processing ───────────────────────────────────────────────────

  private async _processNext(): Promise<void> {
    if (this._queue.length === 0) {
      this._isSpeaking = false;
      this.state = 'idle';
      return;
    }

    const request = this._queue.shift()!;
    this._isSpeaking = true;
    this.state = 'speaking';

    await this._speak(request);
  }

  private async _speak(request: SpeechRequest): Promise<void> {
    return new Promise<void>((resolve) => {
      this._currentResolve = resolve;
      const segment: SpeechSegment = {
        text: request.text,
        start_ms: Date.now(),
        duration_ms: this._estimateDuration(request.text),
        emotion: request.emotion ?? {
          emotion: 'calmness',
          intensity: 0.5,
          duration_ms: 0,
          speech_style: 'warm',
          gesture_metadata: '',
        },
      };
      this._currentSegment = segment;

      this._config.onEvent?.({
        type: 'speech:start',
        timestamp: Date.now(),
        data: { text: request.text, emotion: segment.emotion },
      });

      // The actual TTS would be called here via the streaming engine.
      // For now we simulate duration then mark complete.
      const duration = segment.duration_ms;
      setTimeout(() => {
        this._currentSegment = null;
        this._currentResolve = null;
        this._config.onEvent?.({
          type: 'speech:end',
          timestamp: Date.now(),
          data: { text: request.text },
        });
        resolve();
        this._processNext();
      }, duration);
    });
  }

  private _cancelCurrent(): void {
    if (this._currentResolve) {
      this._config.onEvent?.({
        type: 'speech:pause',
        timestamp: Date.now(),
        data: { text: this._currentSegment?.text ?? '' },
      });
      this._currentResolve();
      this._currentResolve = null;
    }
    this._currentSegment = null;
    this._isSpeaking = false;
    this.state = 'idle';
  }

  private _estimateDuration(text: string): number {
    // Rough estimate: ~100ms per word for Hindi/English code-switched speech
    const words = text.split(/\s+/).length;
    return Math.max(300, words * 100);
  }

  // ── Cleanup ────────────────────────────────────────────────────────────

  dispose(): void {
    this.clearQueue();
    this._stateListeners.clear();
  }
}
