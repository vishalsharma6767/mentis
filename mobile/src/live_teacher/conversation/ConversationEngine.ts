// ──────────────────────────────────────────────────────────────────────────────
// ConversationEngine — natural dialogue management for the live teacher.
//
// Supports Hinglish-first dialogue, interruptions, clarification, follow-up
// questions, thinking pauses, and acknowledgements. Maintains conversation
// context across turns. Produces teacher utterances that feel natural, not
// robotic.
// ──────────────────────────────────────────────────────────────────────────────

import type {
  ConversationRole,
  ConversationState,
  ConversationTurn,
  ConversationContext,
  EmotionState,
  LiveTeacherEvent,
} from '../types';

export interface ConversationEngineConfig {
  max_context_turns: number;
  doubt_keywords: string[];
  acknowledgement_phrases: string[];
  thinking_pause_ms: number;
  onEvent?: (event: LiveTeacherEvent) => void;
}

const HINGLISH_ACKNOWLEDGEMENTS = [
  'Bahut badhiya!',
  'Sahi direction mein ho.',
  'Ek baar aur dekho.',
  'Yahan ek choti si galti hai.',
  'Haan, bilkul sahi.',
  'Achha sawaal hai.',
  'Thoda aur socho.',
  'Maine dekha, aapne sahi kiya.',
  'Bahut achha, aage badho.',
  'Sahi jawab!',
];

const THINKING_PHRASES = [
  'Achha, dekhte hain...',
  'Hmm, accha samajhte hain.',
  'Ruko, main sochta hoon...',
  'Dekho, aisa hai...',
  'To aapne kya likha? Achha...',
];

const DEFAULT_CONFIG: ConversationEngineConfig = {
  max_context_turns: 50,
  doubt_keywords: [
    'samajh', 'doubt', 'confuse', 'kaise', 'kyun', 'kya', 'sir',
    'maam', 'pls', 'please', 'help', 'nhi', 'nahi', 'fir se',
    'explain', 'repeat', 'eak bar',
  ],
  acknowledgement_phrases: HINGLISH_ACKNOWLEDGEMENTS,
  thinking_pause_ms: 800,
};

export class ConversationEngine {
  private _config: ConversationEngineConfig;
  private _turns: ConversationTurn[] = [];
  private _state: ConversationState = 'idle';
  private _doubtMode = false;
  private _interruptionCount = 0;
  private _topic = '';
  private _stateListeners: Set<(state: ConversationState) => void> = new Set();

  constructor(config: Partial<ConversationEngineConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── State ──────────────────────────────────────────────────────────────

  get state(): ConversationState {
    return this._state;
  }

  get context(): ConversationContext {
    return {
      turns: [...this._turns],
      current_state: this._state,
      topic: this._topic,
      doubt_mode: this._doubtMode,
      interruption_count: this._interruptionCount,
    };
  }

  set topic(value: string) {
    this._topic = value;
  }

  onStateChange(listener: (state: ConversationState) => void): () => void {
    this._stateListeners.add(listener);
    return () => this._stateListeners.delete(listener);
  }

  // ── Turn Management ────────────────────────────────────────────────────

  addTurn(role: ConversationRole, text: string, emotion?: EmotionState): void {
    const turn: ConversationTurn = {
      role,
      text,
      timestamp: Date.now(),
      emotion,
      turn_id: `turn_${Date.now()}_${this._turns.length}`,
    };

    this._turns.push(turn);

    if (this._turns.length > this._config.max_context_turns) {
      this._turns.splice(0, this._turns.length - this._config.max_context_turns);
    }

    this._config.onEvent?.({
      type: 'conversation:turn',
      timestamp: turn.timestamp,
      data: { role, text: text.slice(0, 100), turn_id: turn.turn_id },
    });

    if (role === 'student') {
      this._detectDoubt(text);
    }
  }

  // ── State Transitions ──────────────────────────────────────────────────

  setState(newState: ConversationState): void {
    if (this._state === newState) return;
    const prev = this._state;
    this._state = newState;
    for (const listener of this._stateListeners) {
      listener(newState);
    }
    this._config.onEvent?.({
      type: 'conversation:state_change',
      timestamp: Date.now(),
      data: { from: prev, to: newState },
    });
  }

  // ── Teacher Utterances ─────────────────────────────────────────────────

  getAcknowledgement(): string {
    const phrases = this._config.acknowledgement_phrases;
    return phrases[Math.floor(Math.random() * phrases.length)];
  }

  getThinkingPhrase(): string {
    return THINKING_PHRASES[Math.floor(Math.random() * THINKING_PHRASES.length)];
  }

  // ── Doubt Detection ────────────────────────────────────────────────────

  private _detectDoubt(text: string): void {
    const lower = text.toLowerCase();
    const hasDoubt = this._config.doubt_keywords.some((kw) => lower.includes(kw));
    if (hasDoubt) {
      this._doubtMode = true;
      this._interruptionCount++;
    }
  }

  isDoubtMode(): boolean {
    return this._doubtMode;
  }

  clearDoubtMode(): void {
    this._doubtMode = false;
  }

  getInterruptionCount(): number {
    return this._interruptionCount;
  }

  // ── Clarification ──────────────────────────────────────────────────────

  needsClarification(turn: ConversationTurn): boolean {
    const lower = turn.text.toLowerCase();
    return lower.includes('kaise') || lower.includes('kyun') || lower.includes('kya') || turn.text.length < 3;
  }

  generateClarificationPrompt(topic: string): string {
    return `Achha, aapne ${topic} ke baare mein poochha. Kya aap thoda aur bata sakte hain ki exactly kya samajh nahi aaya?`;
  }

  // ── Follow-up ──────────────────────────────────────────────────────────

  shouldAskFollowUp(): boolean {
    return this._state === 'evaluating' && Math.random() > 0.4;
  }

  generateFollowUp(): string {
    const followUps = [
      'Aur kuch poochna hai?',
      'Kya aapne yeh pehle dekha tha?',
      'Batao, aapko kaisa laga yeh?',
      'Is topic par aur koi doubt hai?',
      'Aap is example ko apne words mein samjha sakte ho?',
    ];
    return followUps[Math.floor(Math.random() * followUps.length)];
  }

  // ── Reset ──────────────────────────────────────────────────────────────

  reset(): void {
    this._turns = [];
    this._state = 'idle';
    this._doubtMode = false;
    this._interruptionCount = 0;
  }

  dispose(): void {
    this.reset();
    this._stateListeners.clear();
  }
}
