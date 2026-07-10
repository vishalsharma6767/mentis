// ──────────────────────────────────────────────────────────────────────────────
// TeacherStateManager — manages the teacher's current activity, focus, speech,
// and visual presence on screen.  Exposes reactive shared values that the
// layered renderer consumes.
//
// The UI never reads raw backend output — it always reads from this manager,
// which translates TeachingDecisionDTO + TeacherOutputDTO into render state.
// ──────────────────────────────────────────────────────────────────────────────

import type {
  BoardActionDTO,
  BoardFocusDTO,
  Point,
  TeacherActivity,
  TeacherFocusDTO,
  TeacherState,
  TeachingDecisionDTO,
  TeachingPriorityDTO,
} from '../types';
import type { SharedValue } from 'react-native-reanimated';
import { useSharedValue } from 'react-native-reanimated';

// ── TeacherStateManager ──────────────────────────────────────────────────────

export class TeacherStateManager {
  // Reactive state — UI subscribes to these
  public readonly activity: SharedValue<TeacherActivity>;
  public readonly currentFocus: SharedValue<string>;
  public readonly currentStep: SharedValue<number>;
  public readonly speechText: SharedValue<string>;
  public readonly isAnimated: SharedValue<boolean>;
  public readonly confidence: SharedValue<number>;
  public readonly isWaitingForStudent: SharedValue<boolean>;
  public readonly boardContentHash: SharedValue<string>;
  public readonly pointerPosition: SharedValue<Point>;
  public readonly currentMisconception: SharedValue<string>;
  public readonly learningObjective: SharedValue<string>;

  // Private backing store for non-reactive queries
  private _currentDecision: TeachingDecisionDTO | null = null;
  private _lastBoardActions: BoardActionDTO[] = [];
  private _stateChangeCallbacks: Array<(state: TeacherState) => void> = [];

  constructor() {
    this.activity = useSharedValue<TeacherActivity>('idle');
    this.currentFocus = useSharedValue('');
    this.currentStep = useSharedValue(0);
    this.speechText = useSharedValue('');
    this.isAnimated = useSharedValue(false);
    this.confidence = useSharedValue(0);
    this.isWaitingForStudent = useSharedValue(false);
    this.boardContentHash = useSharedValue('');
    this.pointerPosition = useSharedValue<Point>({ x: 0.5, y: 0.5 });
    this.currentMisconception = useSharedValue('');
    this.learningObjective = useSharedValue('');
  }

  // ── Teaching decision ──────────────────────────────────────────────────

  applyTeachingDecision(decision: TeachingDecisionDTO): void {
    this._currentDecision = decision;

    // Focus
    this.currentFocus.value = decision.focus.current_focus;
    this.currentMisconception.value = decision.focus.misconception;
    this.learningObjective.value = decision.focus.learning_objective;

    // Confidence
    this.confidence.value = decision.confidence;

    // Steps — set step count from steps array
    if (decision.steps?.length > 0) {
      this.currentStep.value = decision.steps.length;
    }

    // Hints — store as speech if present
    if (decision.hints?.length > 0) {
      this.speechText.value = decision.hints[0];
    }

    // Visual focus
    if (decision.focus.visual_focus) {
      // Visual focus string can be parsed for pointer position
    }

    this._notify();
  }

  getCurrentDecision(): TeachingDecisionDTO | null {
    return this._currentDecision;
  }

  // ── Activity ───────────────────────────────────────────────────────────

  setActivity(activity: TeacherActivity): void {
    this.activity.value = activity;
    this._notify();
  }

  // ── Focus ──────────────────────────────────────────────────────────────

  setFocus(focus: string): void {
    this.currentFocus.value = focus;
    this._notify();
  }

  setLearningObjective(objective: string): void {
    this.learningObjective.value = objective;
  }

  setMisconception(misconception: string): void {
    this.currentMisconception.value = misconception;
  }

  // ── Speech ─────────────────────────────────────────────────────────────

  setSpeech(text: string): void {
    this.speechText.value = text;
    if (text) {
      this.activity.value = 'speaking';
    }
    this._notify();
  }

  appendSpeech(chunk: string): void {
    const current = this.speechText.value;
    this.speechText.value = current + chunk;
    this.activity.value = 'speaking';
  }

  clearSpeech(): void {
    this.speechText.value = '';
  }

  // ── Waiting ────────────────────────────────────────────────────────────

  setWaiting(waiting: boolean): void {
    this.isWaitingForStudent.value = waiting;
    if (waiting) {
      this.activity.value = 'waiting';
    }
    this._notify();
  }

  // ── Board actions ──────────────────────────────────────────────────────

  recordBoardAction(action: BoardActionDTO): void {
    this._lastBoardActions.push(action);
    if (this._lastBoardActions.length > 100) {
      this._lastBoardActions.shift();
    }

    // Update hash
    let hash = 0;
    for (const a of this._lastBoardActions) {
      hash = ((hash << 5) - hash + a.content.length) | 0;
    }
    this.boardContentHash.value = hash.toString(16);

    // Update activity based on action
    switch (action.action) {
      case 'write':
      case 'formula':
        this.activity.value = 'writing';
        break;
      case 'draw':
      case 'diagram':
        this.activity.value = 'drawing';
        break;
      case 'highlight':
        this.activity.value = 'pointing';
        break;
      case 'erase':
      case 'clear':
        // Activity stays as is
        break;
    }

    this._notify();
  }

  getLastBoardActions(): BoardActionDTO[] {
    return [...this._lastBoardActions];
  }

  clearBoardActions(): void {
    this._lastBoardActions = [];
    this.boardContentHash.value = '';
  }

  // ── State query ────────────────────────────────────────────────────────

  getState(): TeacherState {
    return {
      activity: this.activity.value,
      current_focus: this.currentFocus.value,
      current_step: this.currentStep.value,
      speech_text: this.speechText.value,
      is_animated: this.isAnimated.value,
      confidence: this.confidence.value,
      is_waiting_for_student: this.isWaitingForStudent.value,
      board_content_hash: this.boardContentHash.value,
      pointer_position: this.pointerPosition.value,
    };
  }

  // ── Subscriptions ──────────────────────────────────────────────────────

  onStateChange(cb: (state: TeacherState) => void): () => void {
    this._stateChangeCallbacks.push(cb);
    return () => {
      this._stateChangeCallbacks = this._stateChangeCallbacks.filter(
        (f) => f !== cb,
      );
    };
  }

  // ── Reset ──────────────────────────────────────────────────────────────

  reset(): void {
    this.activity.value = 'idle';
    this.currentFocus.value = '';
    this.currentStep.value = 0;
    this.speechText.value = '';
    this.isAnimated.value = false;
    this.confidence.value = 0;
    this.isWaitingForStudent.value = false;
    this.boardContentHash.value = '';
    this.currentMisconception.value = '';
    this.learningObjective.value = '';
    this._currentDecision = null;
    this._lastBoardActions = [];
  }

  // ── Internal ───────────────────────────────────────────────────────────

  private _notify(): void {
    const state = this.getState();
    this._stateChangeCallbacks.forEach((cb) => cb(state));
  }
}
