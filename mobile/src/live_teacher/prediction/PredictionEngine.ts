// ──────────────────────────────────────────────────────────────────────────────
// PredictionEngine — anticipates teacher and student actions to reduce latency.
//
// Predicts notebook movement, pointer movement, teacher timing, animation
// timing, and speech timing. Preloads resources and prepares actions before
// they are needed, reducing the perceived latency of the live teaching system.
// ──────────────────────────────────────────────────────────────────────────────

import type {
  PredictionResult,
  LiveLessonPhase,
  ConversationState,
  LiveTeacherEvent,
} from '../types';

export interface PredictionEngineConfig {
  prediction_horizon_ms: number;
  min_confidence: number;
  onEvent?: (event: LiveTeacherEvent) => void;
}

const DEFAULT_CONFIG: PredictionEngineConfig = {
  prediction_horizon_ms: 2000,
  min_confidence: 0.6,
};

interface PredictionRule {
  pattern: string;
  next_phase: LiveLessonPhase;
  confidence: number;
  resources: string[];
}

const PHASE_TRANSITIONS: PredictionRule[] = [
  { pattern: 'greeting', next_phase: 'observing', confidence: 0.95, resources: ['camera:focus'] },
  { pattern: 'observing', next_phase: 'explaining', confidence: 0.9, resources: ['llm:response', 'board:clear'] },
  { pattern: 'explaining', next_phase: 'pointing', confidence: 0.7, resources: ['pointer:activate'] },
  { pattern: 'explaining', next_phase: 'writing', confidence: 0.6, resources: ['pen:activate', 'board:ink'] },
  { pattern: 'pointing', next_phase: 'writing', confidence: 0.55, resources: ['pen:activate'] },
  { pattern: 'writing', next_phase: 'pausing', confidence: 0.8, resources: ['speech:think'] },
  { pattern: 'pausing', next_phase: 'listening', confidence: 0.85, resources: ['mic:listen'] },
  { pattern: 'listening', next_phase: 'evaluating', confidence: 0.9, resources: ['llm:evaluate'] },
  { pattern: 'evaluating', next_phase: 'encouraging', confidence: 0.7, resources: ['speech:encourage'] },
  { pattern: 'evaluating', next_phase: 'explaining', confidence: 0.6, resources: ['llm:rephrase', 'board:update'] },
  { pattern: 'encouraging', next_phase: 'updating_board', confidence: 0.6, resources: ['board:update'] },
  { pattern: 'encouraging', next_phase: 'continuing', confidence: 0.7, resources: ['timeline:advance'] },
  { pattern: 'continuing', next_phase: 'explaining', confidence: 0.9, resources: ['llm:next_topic'] },
  { pattern: 'idle', next_phase: 'greeting', confidence: 0.9, resources: ['speech:greeting'] },
];

export class PredictionEngine {
  private _config: PredictionEngineConfig;
  private _lastPrediction: PredictionResult | null = null;
  private _listeners: Set<(prediction: PredictionResult) => void> = new Set();

  constructor(config: Partial<PredictionEngineConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── Prediction ─────────────────────────────────────────────────────────

  predictPhase(currentPhase: LiveLessonPhase): PredictionResult {
    const rules = PHASE_TRANSITIONS.filter((r) => r.pattern === currentPhase);

    if (rules.length === 0) {
      return {
        next_action: currentPhase,
        confidence: 0,
        preload_resources: [],
        estimated_timing_ms: 1000,
      };
    }

    // Pick the highest-confidence transition
    const best = rules.reduce((a, b) => (a.confidence > b.confidence ? a : b));

    if (best.confidence < this._config.min_confidence) {
      return {
        next_action: currentPhase,
        confidence: best.confidence,
        preload_resources: [],
        estimated_timing_ms: 1500,
      };
    }

    const result: PredictionResult = {
      next_action: best.next_phase,
      confidence: best.confidence,
      preload_resources: [...best.resources],
      estimated_timing_ms: 2000 * best.confidence,
    };

    this._lastPrediction = result;
    this._notify(result);

    return result;
  }

  predictConversationTransition(state: ConversationState): PredictionResult {
    const nextMap: Partial<Record<ConversationState, { next: ConversationState; confidence: number; resources: string[] }>> = {
      greeting: { next: 'explaining', confidence: 0.9, resources: ['llm:intro'] },
      explaining: { next: 'questioning', confidence: 0.7, resources: ['speech:question'] },
      questioning: { next: 'listening', confidence: 0.95, resources: ['mic:listen'] },
      listening: { next: 'evaluating', confidence: 0.9, resources: ['llm:evaluate'] },
      evaluating: { next: 'encouraging', confidence: 0.65, resources: ['speech:encourage'] },
      encouraging: { next: 'explaining', confidence: 0.7, resources: ['llm:next'] },
      clarifying: { next: 'explaining', confidence: 0.8, resources: ['llm:rephrase'] },
    };

    const transition = nextMap[state];
    if (!transition || transition.confidence < this._config.min_confidence) {
      return {
        next_action: state,
        confidence: 0,
        preload_resources: [],
        estimated_timing_ms: 1000,
      };
    }

    const result: PredictionResult = {
      next_action: transition.next,
      confidence: transition.confidence,
      preload_resources: [...transition.resources],
      estimated_timing_ms: 1500 * transition.confidence,
    };

    this._lastPrediction = result;
    this._notify(result);

    return result;
  }

  preloadResources(action: string): string[] {
    const rule = PHASE_TRANSITIONS.find((r) => r.next_phase === action);
    return rule ? [...rule.resources] : [];
  }

  // ── State ──────────────────────────────────────────────────────────────

  get lastPrediction(): PredictionResult | null {
    return this._lastPrediction;
  }

  onPrediction(listener: (prediction: PredictionResult) => void): () => void {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  // ── Private ────────────────────────────────────────────────────────────

  private _notify(result: PredictionResult): void {
    for (const listener of this._listeners) {
      listener(result);
    }
    this._config.onEvent?.({
      type: 'prediction:ready',
      timestamp: Date.now(),
      data: result,
    });
  }

  dispose(): void {
    this._listeners.clear();
    this._lastPrediction = null;
  }
}
