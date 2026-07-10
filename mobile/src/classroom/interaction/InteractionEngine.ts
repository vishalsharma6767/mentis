// ──────────────────────────────────────────────────────────────────────────────
// InteractionEngine — handles student interaction with the classroom.
//
// The student can:
//   - Speak (ask a doubt, answer a question)
//   - Touch (tap on something in the scene)
//   - Draw (write on the board / notebook)
//   - Interrupt the teacher mid-lesson
//
// The engine detects interruptions, pauses the timeline, and notifies
// the backend so the teacher can adapt in real time.
// ──────────────────────────────────────────────────────────────────────────────

import type { StudentInputType, StudentInteraction, StudentState } from '../types';

// ── Configuration ────────────────────────────────────────────────────────────

export interface InteractionConfig {
  /** Debounce time (ms) for repeated interactions of the same type */
  debounceMs: number;
  /** Minimum confidence to accept an interaction */
  minConfidence: number;
  /** Maximum queued interactions before oldest is dropped */
  maxQueueSize: number;
  /** Whether to auto-pause timeline on interruption */
  autoPauseOnInterrupt: boolean;
}

const DEFAULT_CONFIG: InteractionConfig = {
  debounceMs: 500,
  minConfidence: 0.4,
  maxQueueSize: 10,
  autoPauseOnInterrupt: true,
};

// ── InteractionEngine ────────────────────────────────────────────────────────

export class InteractionEngine {
  private _config: InteractionConfig;
  private _interactionQueue: StudentInteraction[] = [];
  private _lastInteractionTime = 0;
  private _lastInteractionType: StudentInputType | null = null;
  private _isInterrupting = false;

  private _interactionCallbacks: Array<(interaction: StudentInteraction) => void> = [];
  private _interruptCallbacks: Array<() => void> = [];

  private _externalPauseFn: (() => void) | null = null;

  constructor(config: Partial<InteractionConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── Public API ─────────────────────────────────────────────────────────

  handleStudentInteraction(interaction: StudentInteraction): void {
    // Debounce check
    const now = Date.now();
    if (
      interaction.type === this._lastInteractionType &&
      now - this._lastInteractionTime < this._config.debounceMs
    ) {
      return;
    }

    if (interaction.confidence < this._config.minConfidence) {
      return;
    }

    this._lastInteractionTime = now;
    this._lastInteractionType = interaction.type;

    // Queue
    this._interactionQueue.push(interaction);
    if (this._interactionQueue.length > this._config.maxQueueSize) {
      this._interactionQueue.shift();
    }

    // Notify
    this._interactionCallbacks.forEach((cb) => cb(interaction));

    // Check if this is an interruption
    if (this._isInterruptingInteraction(interaction)) {
      this._triggerInterrupt();
    }
  }

  // ── Input handlers ─────────────────────────────────────────────────────

  handleSpeechInput(text: string, confidence: number): void {
    this.handleStudentInteraction({
      type: 'speech',
      timestamp: Date.now(),
      data: { text, duration_ms: 0 },
      confidence,
    });
  }

  handleTouchInput(x: number, y: number, confidence: number): void {
    this.handleStudentInteraction({
      type: 'touch',
      timestamp: Date.now(),
      data: { x, y },
      confidence,
    });
  }

  handleDrawInput(strokeData: Record<string, unknown>, confidence: number): void {
    this.handleStudentInteraction({
      type: 'draw',
      timestamp: Date.now(),
      data: strokeData,
      confidence,
    });
  }

  handleTextInput(text: string, confidence: number): void {
    this.handleStudentInteraction({
      type: 'text',
      timestamp: Date.now(),
      data: { text },
      confidence,
    });
  }

  // ── Interruption detection ─────────────────────────────────────────────

  isInterrupting(): boolean {
    return this._isInterrupting;
  }

  clearInteraction(): void {
    this._isInterrupting = false;
    this._interactionQueue = [];
  }

  setExternalPauseFn(pauseFn: () => void): void {
    this._externalPauseFn = pauseFn;
  }

  // ── State queries ──────────────────────────────────────────────────────

  getState(): StudentState {
    return {
      is_interrupting: this._isInterrupting,
      current_input: this._interactionQueue[this._interactionQueue.length - 1] ?? null,
      last_doubt: this._getLastDoubt(),
      attention_score: this._estimateAttentionScore(),
    };
  }

  getInteractionQueue(): StudentInteraction[] {
    return [...this._interactionQueue];
  }

  getLastInteraction(): StudentInteraction | null {
    return this._interactionQueue[this._interactionQueue.length - 1] ?? null;
  }

  // ── Subscriptions ──────────────────────────────────────────────────────

  onInteraction(cb: (interaction: StudentInteraction) => void): () => void {
    this._interactionCallbacks.push(cb);
    return () => {
      this._interactionCallbacks = this._interactionCallbacks.filter(
        (f) => f !== cb,
      );
    };
  }

  onInterrupt(cb: () => void): () => void {
    this._interruptCallbacks.push(cb);
    return () => {
      this._interruptCallbacks = this._interruptCallbacks.filter((f) => f !== cb);
    };
  }

  // ── Internals ──────────────────────────────────────────────────────────

  private _isInterruptingInteraction(interaction: StudentInteraction): boolean {
    if (interaction.type === 'speech') {
      const text = (interaction.data.text as string) ?? '';
      const doubtKeywords = [
        'doubt', 'question', 'how', 'why', 'what', 'explain',
        'samajh', 'nahi', 'kya', 'kaise', 'kyu', 'please',
        'wait', 'stop', 'hold on', 'ek minute',
      ];
      const lower = text.toLowerCase();
      return doubtKeywords.some((kw) => lower.includes(kw));
    }

    if (interaction.type === 'touch') {
      // Multiple rapid taps indicate interruption
      const recentTaps = this._interactionQueue.filter(
        (i) => i.type === 'touch' && Date.now() - i.timestamp < 2000,
      );
      return recentTaps.length >= 3;
    }

    return false;
  }

  private _triggerInterrupt(): void {
    if (this._isInterrupting) return;

    this._isInterrupting = true;

    // Auto-pause timeline if configured
    if (this._config.autoPauseOnInterrupt && this._externalPauseFn) {
      this._externalPauseFn();
    }

    this._interruptCallbacks.forEach((cb) => cb());
  }

  private _getLastDoubt(): string | null {
    const speechInteractions = this._interactionQueue.filter(
      (i) => i.type === 'speech',
    );
    if (speechInteractions.length === 0) return null;
    const last = speechInteractions[speechInteractions.length - 1];
    return (last.data.text as string) ?? null;
  }

  private _estimateAttentionScore(): number {
    // Simple heuristic: more recent interaction = higher attention
    if (this._interactionQueue.length === 0) return 0.5;
    const lastTime = this._interactionQueue[this._interactionQueue.length - 1].timestamp;
    const elapsed = Date.now() - lastTime;
    if (elapsed < 10000) return 1.0; // interacted within last 10 seconds
    if (elapsed < 30000) return 0.8;
    if (elapsed < 60000) return 0.6;
    if (elapsed < 300000) return 0.4; // 5 minutes
    return 0.2;
  }
}
