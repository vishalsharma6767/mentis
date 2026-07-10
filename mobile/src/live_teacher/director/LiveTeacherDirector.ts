// ──────────────────────────────────────────────────────────────────────────────
// LiveTeacherDirector — central coordinator for the live teaching experience.
//
// The director never renders. It orchestrates all live subsystems:
//   - StreamingManager    (LLM/speech/drawing/pointer/AR/captions/…)
//   - SpeechManager       (TTS queue, thinking pauses)
//   - ConversationEngine  (dialogue state, interruptions, Hinglish)
//   - PresenceEngine      (warmth, confidence, rhythm metadata)
//   - TimingEngine        (master clock, play/pause/skip/replay)
//   - SyncEngine          (drift correction across subsystems)
//   - EmotionEngine       (emotion metadata for every response)
//   - LiveInteractionEngine (priority student interaction queue)
//   - PredictionEngine    (preloading, next-action prediction)
//   - ResourceManager     (caching, lazy loading)
//   - LatencyEngine       (performance monitoring)
//   - AnalyticsEngine     (lesson quality metrics)
//
// The director implements the Live Lesson Loop:
//   greet → observe → explain → point → write → pause →
//   listen → evaluate → encourage → update board → continue
//
// No blocking operations. Every phase transition is asynchronous and
// non-blocking. The director polls the interaction queue between phases
// to handle interruptions, doubts, and student input.
// ──────────────────────────────────────────────────────────────────────────────

import { StreamingManager } from '../streaming/StreamingManager';
import { SpeechManager } from '../speech/SpeechManager';
import { ConversationEngine } from '../conversation/ConversationEngine';
import { PresenceEngine } from '../presence/PresenceEngine';
import { TimingEngine } from '../timing/TimingEngine';
import { SyncEngine } from '../synchronization/SyncEngine';
import { EmotionEngine } from '../emotion/EmotionEngine';
import { LiveInteractionEngine } from '../interaction/LiveInteractionEngine';
import { PredictionEngine } from '../prediction/PredictionEngine';
import { ResourceManager } from '../resource_manager/ResourceManager';
import { LatencyEngine } from '../latency/LatencyEngine';
import { AnalyticsEngine } from '../analytics/AnalyticsEngine';
import type {
  LiveLessonPhase,
  DirectorState,
  LiveTeacherEvent,
  EmotionState,
  LessonAnalytics,
  LatencyReport,
} from '../types';

export interface LiveTeacherDirectorConfig {
  onEvent?: (event: LiveTeacherEvent) => void;
  streaming?: Partial<ConstructorParameters<typeof StreamingManager>[0]>;
  speech?: Partial<ConstructorParameters<typeof SpeechManager>[0]>;
  conversation?: Partial<ConstructorParameters<typeof ConversationEngine>[0]>;
  presence?: Partial<ConstructorParameters<typeof PresenceEngine>[0]>;
  timing?: Partial<ConstructorParameters<typeof TimingEngine>[0]>;
  sync?: Partial<ConstructorParameters<typeof SyncEngine>[0]>;
  emotion?: Partial<ConstructorParameters<typeof EmotionEngine>[0]>;
  interaction?: Partial<ConstructorParameters<typeof LiveInteractionEngine>[0]>;
  prediction?: Partial<ConstructorParameters<typeof PredictionEngine>[0]>;
  resource?: Partial<ConstructorParameters<typeof ResourceManager>[0]>;
  latency?: Partial<ConstructorParameters<typeof LatencyEngine>[0]>;
  analytics?: Partial<ConstructorParameters<typeof AnalyticsEngine>[0]>;
}

// ── Subsystem Interfaces (the director depends on abstractions) ──────────

export interface DirectorSubsystems {
  streaming: StreamingManager;
  speech: SpeechManager;
  conversation: ConversationEngine;
  presence: PresenceEngine;
  timing: TimingEngine;
  sync: SyncEngine;
  emotion: EmotionEngine;
  interaction: LiveInteractionEngine;
  prediction: PredictionEngine;
  resource: ResourceManager;
  latency: LatencyEngine;
  analytics: AnalyticsEngine;
}

export class LiveTeacherDirector {
  // ── Public Subsystems ──────────────────────────────────────────────────
  readonly streaming: StreamingManager;
  readonly speech: SpeechManager;
  readonly conversation: ConversationEngine;
  readonly presence: PresenceEngine;
  readonly timing: TimingEngine;
  readonly sync: SyncEngine;
  readonly emotion: EmotionEngine;
  readonly interaction: LiveInteractionEngine;
  readonly prediction: PredictionEngine;
  readonly resource: ResourceManager;
  readonly latency: LatencyEngine;
  readonly analytics: AnalyticsEngine;

  private _config: LiveTeacherDirectorConfig;
  private _state: DirectorState;
  private _phaseListeners: Set<(phase: LiveLessonPhase) => void> = new Set();
  private _stateListeners: Set<(state: DirectorState) => void> = new Set();
  private _running = false;
  private _currentLessonId: string | null = null;

  constructor(config: LiveTeacherDirectorConfig = {}) {
    this._config = config;

    const onEvent = (event: LiveTeacherEvent) => {
      this._config.onEvent?.(event);
    };

    const spread = <T>(x: T | undefined): T => ({ ...(x ?? {}) } as T);
    this.streaming = new StreamingManager({ ...spread(config.streaming), onEvent });
    this.speech = new SpeechManager({ ...spread(config.speech), onEvent });
    this.conversation = new ConversationEngine({ ...spread(config.conversation), onEvent });
    this.presence = new PresenceEngine({ ...spread(config.presence), onEvent });
    this.timing = new TimingEngine({ ...spread(config.timing), onEvent });
    this.sync = new SyncEngine({ ...spread(config.sync), onEvent });
    this.emotion = new EmotionEngine({ ...spread(config.emotion), onEvent });
    this.interaction = new LiveInteractionEngine({ ...spread(config.interaction), onEvent });
    this.prediction = new PredictionEngine({ ...spread(config.prediction), onEvent });
    this.resource = new ResourceManager({ ...spread(config.resource), onEvent });
    this.latency = new LatencyEngine({ ...spread(config.latency), onEvent });
    this.analytics = new AnalyticsEngine({ ...spread(config.analytics), onEvent });

    this._state = this._defaultState();
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────

  startLesson(lessonId: string): void {
    if (this._running) return;
    this._running = true;
    this._currentLessonId = lessonId;

    // Start background subsystems
    this.presence.start();
    this.sync.start();
    this.latency.start();
    this.analytics.start();

    // Begin the live lesson loop
    this._runLessonLoop();
  }

  stopLesson(): void {
    this._running = false;
    this._currentLessonId = null;

    this.streaming.cancelAll();
    this.speech.clearQueue();
    this.timing.stop();
    this.presence.stop();
    this.sync.stop();
    this.latency.stop();
    this.analytics.stop();
    this.interaction.clear();
    this.conversation.reset();
    this.emotion.reset();

    this._state = this._defaultState();
    this._notifyState();
  }

  isRunning(): boolean {
    return this._running;
  }

  get currentLessonId(): string | null {
    return this._currentLessonId;
  }

  // ── State Access ───────────────────────────────────────────────────────

  get state(): DirectorState {
    return { ...this._state };
  }

  get phase(): LiveLessonPhase {
    return this._state.phase;
  }

  onPhaseChange(listener: (phase: LiveLessonPhase) => void): () => void {
    this._phaseListeners.add(listener);
    return () => this._phaseListeners.delete(listener);
  }

  onStateChange(listener: (state: DirectorState) => void): () => void {
    this._stateListeners.add(listener);
    return () => this._stateListeners.delete(listener);
  }

  // ── Phase Transitions ──────────────────────────────────────────────────

  private async _transitionTo(phase: LiveLessonPhase): Promise<void> {
    const prev = this._state.phase;
    this._state.phase = phase;
    this._state.phase_started_at = Date.now();
    this._state.is_streaming = false;
    this._state.is_speaking = false;
    this._state.is_writing = false;
    this._state.is_pointing = false;

    // Update all subsystems that need to know about the phase change
    this.presence.onPhaseChange(phase);
    this.emotion.setFromPhase(phase);
    this.prediction.predictPhase(phase);

    for (const listener of this._phaseListeners) {
      listener(phase);
    }
    this._notifyState();

    this._config.onEvent?.({
      type: 'director:phase_change',
      timestamp: Date.now(),
      data: { from: prev, to: phase },
    });
  }

  private async _setPhaseFlag(flags: Partial<DirectorState>): Promise<void> {
    Object.assign(this._state, flags);
    this._notifyState();
  }

  // ── Live Lesson Loop ───────────────────────────────────────────────────
  //
  //   greet → observe → explain → point → write → pause →
  //   listen → evaluate → encourage → update board → continue
  //
  // Each phase is non-blocking. Between phases the director checks for
  // interruptions, doubts, and student input.
  // ────────────────────────────────────────────────────────────────────────

  private async _runLessonLoop(): Promise<void> {
    while (this._running) {
      // Check for critical interactions before each phase
      if (await this._handleCriticalInteractions()) {
        continue; // Re-check after handling
      }

      switch (this._state.phase) {
        case 'idle':
          await this._doGreeting();
          break;
        case 'greeting':
          await this._doObserve();
          break;
        case 'observing':
          await this._doExplain();
          break;
        case 'explaining':
          await this._doPoint();
          break;
        case 'pointing':
          await this._doWrite();
          break;
        case 'writing':
          await this._doPause();
          break;
        case 'pausing':
          await this._doListen();
          break;
        case 'listening':
          await this._doEvaluate();
          break;
        case 'evaluating':
          await this._doEncourage();
          break;
        case 'encouraging':
          await this._doUpdateBoard();
          break;
        case 'updating_board':
          await this._doContinue();
          break;
        case 'continuing':
          await this._doExplain(); // Loop back
          break;
        default:
          await this._idleWait();
          break;
      }
    }
  }

  // ── Phase Implementations ──────────────────────────────────────────────

  private async _doGreeting(): Promise<void> {
    await this._transitionTo('greeting');

    const greeting = 'Namaste! Aaj hum seekhenge mathematics ka ek naya concept.';
    this.conversation.topic = 'mathematics';
    this.conversation.addTurn('teacher', greeting);
    this.speech.enqueue({ text: greeting, priority: 0 });

    this.analytics.trackEvent('lesson_start', { lesson_id: this._currentLessonId });

    // Wait for greeting speech to finish
    await this._waitForSpeech();
  }

  private async _doObserve(): Promise<void> {
    await this._transitionTo('observing');
    await this._setPhaseFlag({ is_streaming: true });

    // In production, wait for the camera/OCR pipeline to produce a scene graph
    // For now, simulate a brief observation period
    await this._delayedCheck(800, 'observing');
    await this._setPhaseFlag({ is_streaming: false });
  }

  private async _doExplain(): Promise<void> {
    await this._transitionTo('explaining');
    await this._setPhaseFlag({ is_streaming: true, is_speaking: true });

    // The LLM streaming is triggered here via the streaming manager.
    // Speech chunks are fed from the streaming callback to the speech queue.
    const explanation = 'Dekho, jab hum do numbers ko jodte hain, to unka sum aata hai. Ye bahut simple hai.';

    this.conversation.addTurn('teacher', explanation);
    this.speech.enqueue({ text: explanation, priority: 0, emotion: this.emotion.current });
    this.presence.setCuriosity(0.6);

    await this._waitForSpeech();
    await this._setPhaseFlag({ is_streaming: false, is_speaking: false });
  }

  private async _doPoint(): Promise<void> {
    await this._transitionTo('pointing');
    await this._setPhaseFlag({ is_pointing: true });

    this.presence.setRhythm('slow');
    this.presence.setAttention(0.95);

    // Pointer animations are driven by the classroom engine's pointer.
    // The director just signals the start and waits for natural duration.
    await this._delayedCheck(1200, 'pointing');
    await this._setPhaseFlag({ is_pointing: false });
  }

  private async _doWrite(): Promise<void> {
    await this._transitionTo('writing');
    await this._setPhaseFlag({ is_writing: true });

    this.presence.setRhythm('slow');

    // Board writing is handled by the whiteboard engine.
    // The director waits for the writing animation to complete.
    await this._delayedCheck(1500, 'writing');
    await this._setPhaseFlag({ is_writing: false });
  }

  private async _doPause(): Promise<void> {
    await this._transitionTo('pausing');

    this.presence.setRhythm('pause');
    this.presence.setCuriosity(0.8);

    const thinkingPhrase = this.conversation.getThinkingPhrase();
    this.speech.enqueue({ text: thinkingPhrase, priority: 0 });
    this.conversation.addTurn('teacher', thinkingPhrase);

    // Natural thinking pause
    await this.speech.think(1200);
    this.analytics.recordPause(1200);
  }

  private async _doListen(): Promise<void> {
    await this._transitionTo('listening');

    this.conversation.setState('listening');
    this.presence.setEyeContact(true);
    this.presence.setRhythm('pause');

    // Wait for student input with a timeout
    const timeout = 8000;
    const startTime = Date.now();
    while (Date.now() - startTime < timeout && this._running) {
      if (this.interaction.size > 0) {
        const interaction = this.interaction.dequeue();
        if (interaction) {
          // Convert interaction to conversation turn
          const text = typeof interaction.data === 'string' ? interaction.data : '';
          this.conversation.addTurn('student', text);

          if (this.conversation.isDoubtMode()) {
            this.emotion.setFromDoubts();
            await this._handleDoubt();
            return;
          }
          break;
        }
      }
      await this._yieldToMicrotask();
    }

    this.conversation.setState('evaluating');
  }

  private async _doEvaluate(): Promise<void> {
    await this._transitionTo('evaluating');

    this.conversation.setState('evaluating');
    this.emotion.setEmotion('curiosity', 0.65);
    this.presence.setCuriosity(0.75);

    const lastTurn = this.conversation.context.turns[this.conversation.context.turns.length - 1];

    if (lastTurn && this.conversation.needsClarification(lastTurn)) {
      await this._handleClarification();
      return;
    }

    if (this.conversation.shouldAskFollowUp()) {
      const followUp = this.conversation.generateFollowUp();
      this.conversation.addTurn('teacher', followUp);
      this.speech.enqueue({ text: followUp, priority: 0, emotion: this.emotion.current });
      await this._waitForSpeech();
      await this._doListen();
      return;
    }

    // Simulate evaluation latency
    await this._delayedCheck(500, 'evaluating');
    this.analytics.recordTeacherResponse(500);
  }

  private async _doEncourage(): Promise<void> {
    await this._transitionTo('encouraging');

    const ack = this.conversation.getAcknowledgement();
    this.conversation.addTurn('teacher', ack);
    this.speech.enqueue({ text: ack, priority: 0, emotion: this.emotion.current });
    this.emotion.setEmotion('encouragement', 0.9);
    this.presence.setEncouragement(0.95);

    await this._waitForSpeech();
  }

  private async _doUpdateBoard(): Promise<void> {
    await this._transitionTo('updating_board');

    // Board updates are handled by the whiteboard engine.
    // The director simply signals the phase for synchronisation.
    this.presence.setRhythm('normal');
    await this._delayedCheck(600, 'updating_board');
  }

  private async _doContinue(): Promise<void> {
    await this._transitionTo('continuing');

    this.conversation.clearDoubtMode();
    this.presence.setCuriosity(0.5);
    this.emotion.setEmotion('calmness', 0.5);

    await this._delayedCheck(300, 'continuing');
  }

  // ── Interruption & Doubt Handling ──────────────────────────────────────

  private async _handleCriticalInteractions(): Promise<boolean> {
    if (this.interaction.hasCritical()) {
      const interaction = this.interaction.dequeueCritical()!;
      this.analytics.recordInterruption();
      this.emotion.setFromInterruption();
      this.presence.setWarmth(0.9);

      if (interaction.type === 'interruption' || interaction.type === 'doubt') {
        await this._handleDoubt();
        return true;
      }
    }
    return false;
  }

  private async _handleDoubt(): Promise<void> {
    this.conversation.setState('clarifying');
    this.emotion.setFromDoubts();

    const clarification = this.conversation.generateClarificationPrompt(this.conversation.context.topic);
    this.conversation.addTurn('teacher', clarification);
    this.speech.enqueueFront({ text: clarification, priority: 100, emotion: this.emotion.current });

    await this._waitForSpeech();
    await this._doListen();
  }

  private async _handleClarification(): Promise<void> {
    this.conversation.setState('clarifying');

    const prompt = this.conversation.generateClarificationPrompt(this.conversation.context.topic);
    this.conversation.addTurn('teacher', prompt);
    this.speech.enqueue({ text: prompt, priority: 0, emotion: this.emotion.current });

    await this._waitForSpeech();
    await this._doListen();
  }

  // ── External Commands ──────────────────────────────────────────────────

  receiveTeachingDecision(decision: { phase: string }): void {
    const { phase } = decision;
    if (phase) {
      this._transitionTo(phase as LiveLessonPhase);
    }
  }

  injectStudentInteraction(type: string, data: unknown): void {
    const validTypes = ['speech', 'touch', 'draw', 'text', 'gesture', 'notebook_move', 'interruption', 'doubt'];
    const t = validTypes.includes(type) ? type : 'speech';
    this.interaction.enqueue(t as any, data);
  }

  pauseLesson(): void {
    this.timing.pause();
    this.speech.clearQueue();
  }

  resumeLesson(): void {
    this.timing.resume();
  }

  setSpeed(speed: 'slow' | 'normal' | 'fast'): void {
    this.timing.setSpeed(speed);
    this.presence.setRhythm(speed === 'fast' ? 'fast' : speed === 'slow' ? 'slow' : 'normal');
  }

  // ── Debug Info ─────────────────────────────────────────────────────────

  getDebugSnapshot(): {
    phase: LiveLessonPhase;
    director: DirectorState;
    streaming_active: number;
    speech_state: string;
    conversation_state: string;
    timing_state: string;
    sync_drift: number;
    emotion: EmotionState;
    interaction_queue: number;
    analytics: LessonAnalytics;
    latency: LatencyReport;
  } {
    return {
      phase: this.phase,
      director: { ...this._state },
      streaming_active: this.streaming.activeCount(),
      speech_state: this.speech.state,
      conversation_state: this.conversation.state,
      timing_state: this.timing.state.is_paused ? 'paused' : this.timing.state.is_playing ? 'playing' : 'stopped',
      sync_drift: this.sync.state.drift_ms,
      emotion: this.emotion.current,
      interaction_queue: this.interaction.size,
      analytics: this.analytics.current,
      latency: this.latency.report,
    };
  }

  // ── Utilities ──────────────────────────────────────────────────────────

  private async _waitForSpeech(): Promise<void> {
    const startTime = Date.now();
    const timeout = 15000;
    while (this.speech.isSpeaking() && Date.now() - startTime < timeout && this._running) {
      await this._yieldToMicrotask();
    }
  }

  private async _delayedCheck(ms: number, expectedPhase: string): Promise<void> {
    const startTime = Date.now();
    while (Date.now() - startTime < ms && this._running) {
      if (this.interaction.hasCritical() && expectedPhase === this._state.phase) {
        return; // Interruption
      }
      await this._yieldToMicrotask();
    }
  }

  private async _idleWait(): Promise<void> {
    await this._delayedCheck(100, 'idle');
  }

  private _yieldToMicrotask(): Promise<void> {
    return new Promise((resolve) => setImmediate(resolve));
  }

  private _defaultState(): DirectorState {
    return {
      phase: 'idle',
      is_streaming: false,
      is_speaking: false,
      is_writing: false,
      is_pointing: false,
      is_paused: false,
      current_action_id: null,
      phase_started_at: Date.now(),
      student_interaction_queue: 0,
    };
  }

  private _notifyState(): void {
    const snapshot = this.state;
    for (const listener of this._stateListeners) {
      listener(snapshot);
    }
  }

  // ── Cleanup ────────────────────────────────────────────────────────────

  dispose(): void {
    this.stopLesson();
    this.streaming.dispose?.();
    this.speech.dispose();
    this.conversation.dispose();
    this.presence.dispose();
    this.timing.dispose();
    this.sync.dispose();
    this.emotion.dispose();
    this.interaction.dispose();
    this.prediction.dispose();
    this.resource.dispose();
    this.latency.dispose();
    this.analytics.dispose();
    this._phaseListeners.clear();
    this._stateListeners.clear();
  }
}
