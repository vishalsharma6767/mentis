// ──────────────────────────────────────────────────────────────────────────────
// LessonTimeline — manages the lesson as a playable sequence of events.
//
// Every lesson becomes a timeline:
//   Greeting → Teacher speaks → Circle animation → Arrow animation →
//   Teacher writes → Highlight → Pause → Student writes → Teacher checks →
//   Correction → Next step
//
// Supports play, pause, resume, seek, replay, and step-by-step navigation.
// ──────────────────────────────────────────────────────────────────────────────

import type {
  LessonTimelineState,
  TimelineEvent,
  TimelineEventType,
  TimelineState,
} from '../types';

// ── Configuration ────────────────────────────────────────────────────────────

export interface TimelineConfig {
  /** Default wait time between events (ms) when not specified */
  defaultEventGapMs: number;
  /** Speed multiplier for replay */
  replaySpeed: number;
  /** Whether to auto-play after loading events */
  autoPlay: boolean;
}

const DEFAULT_CONFIG: TimelineConfig = {
  defaultEventGapMs: 300,
  replaySpeed: 1.5,
  autoPlay: false,
};

// ── LessonTimeline ───────────────────────────────────────────────────────────

export class LessonTimeline {
  private _config: TimelineConfig;
  private _events: TimelineEvent[] = [];
  private _currentIndex = -1;
  private _currentTimeMs = 0;
  private _state: TimelineState = 'idle';
  private _totalDurationMs = 0;
  private _playStartTime = 0;
  private _pausedAtMs = 0;
  private _playTimer: ReturnType<typeof setTimeout> | null = null;
  private _isReplay = false;

  private _eventCallbacks: Array<(event: TimelineEvent) => void> = [];
  private _stateCallbacks: Array<(state: TimelineState) => void> = [];

  constructor(config: Partial<TimelineConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── Event management ───────────────────────────────────────────────────

  loadEvents(events: TimelineEvent[]): void {
    this._events = events;
    this._totalDurationMs = events.reduce(
      (sum, e) => sum + (e.duration_ms || this._config.defaultEventGapMs),
      0,
    );
    this._currentIndex = -1;
    this._currentTimeMs = 0;
    this._state = 'idle';
    this._notifyState();

    if (this._config.autoPlay && events.length > 0) {
      this.play();
    }
  }

  addEvent(event: TimelineEvent): void {
    this._events.push(event);
    this._totalDurationMs += event.duration_ms || this._config.defaultEventGapMs;
  }

  insertEvent(event: TimelineEvent, index: number): void {
    this._events.splice(index, 0, event);
    this._totalDurationMs += event.duration_ms || this._config.defaultEventGapMs;
  }

  removeEvent(eventId: string): boolean {
    const idx = this._events.findIndex((e) => e.id === eventId);
    if (idx === -1) return false;
    const removed = this._events.splice(idx, 1)[0];
    this._totalDurationMs -= removed.duration_ms || this._config.defaultEventGapMs;
    return true;
  }

  getEvents(): TimelineEvent[] {
    return [...this._events];
  }

  getEventsByType(type: TimelineEventType): TimelineEvent[] {
    return this._events.filter((e) => e.type === type);
  }

  // ── Playback control ───────────────────────────────────────────────────

  play(): void {
    if (this._events.length === 0) return;
    if (this._state === 'playing') return;

    if (this._state === 'paused') {
      this.resume();
      return;
    }

    this._state = 'playing';
    this._currentIndex = -1;
    this._currentTimeMs = 0;
    this._playStartTime = Date.now();
    this._pausedAtMs = 0;
    this._notifyState();
    this._scheduleNext();
  }

  pause(): void {
    if (this._state !== 'playing') return;

    this._state = 'paused';
    this._pausedAtMs = Date.now() - this._playStartTime;
    this._cancelTimer();
    this._notifyState();
  }

  resume(): void {
    if (this._state !== 'paused') return;

    this._state = 'playing';
    this._playStartTime = Date.now() - this._pausedAtMs;
    this._notifyState();
    this._scheduleNext();
  }

  seek(timeMs: number): void {
    this._cancelTimer();
    this._currentTimeMs = Math.max(0, Math.min(timeMs, this._totalDurationMs));

    // Find the event at this time
    let accumulatedTime = 0;
    this._currentIndex = -1;
    for (let i = 0; i < this._events.length; i++) {
      const eventDuration = this._events[i].duration_ms || this._config.defaultEventGapMs;
      if (this._currentTimeMs >= accumulatedTime && this._currentTimeMs < accumulatedTime + eventDuration) {
        this._currentIndex = i;
        break;
      }
      accumulatedTime += eventDuration;
    }

    this._playStartTime = Date.now() - this._currentTimeMs;
    this._state = 'seeking';
    this._notifyState();

    if (this._currentIndex >= 0) {
      this._eventCallbacks.forEach((cb) => cb(this._events[this._currentIndex]));
    }

    // If was playing, continue
    if (this._state === 'seeking') {
      this._state = 'playing';
      this._notifyState();
      this._scheduleNext();
    }
  }

  async next(): Promise<TimelineEvent | null> {
    this._cancelTimer();

    const nextIndex = this._currentIndex + 1;
    if (nextIndex >= this._events.length) {
      this._state = 'finished';
      this._notifyState();
      return null;
    }

    this._currentIndex = nextIndex;
    const event = this._events[nextIndex];
    this._currentTimeMs += event.duration_ms || this._config.defaultEventGapMs;

    this._eventCallbacks.forEach((cb) => cb(event));

    if (this._state === 'playing') {
      this._scheduleNext();
    }

    return event;
  }

  previous(): TimelineEvent | null {
    if (this._currentIndex <= 0) return null;

    this._cancelTimer();
    this._currentIndex--;
    const event = this._events[this._currentIndex];
    this._currentTimeMs -= event.duration_ms || this._config.defaultEventGapMs;

    this._eventCallbacks.forEach((cb) => cb(event));

    if (this._state === 'playing') {
      this._scheduleNext();
    }

    return event;
  }

  async goToStep(stepIndex: number): Promise<TimelineEvent | null> {
    if (stepIndex < 0 || stepIndex >= this._events.length) return null;

    this._cancelTimer();
    this._currentIndex = stepIndex - 1; // Will advance to stepIndex on next()
    return this.next();
  }

  // ── Replay ─────────────────────────────────────────────────────────────

  async replay(): Promise<void> {
    const originalSpeed = this._config.replaySpeed;
    const originalEvents = [...this._events];

    this._isReplay = true;
    this._state = 'idle';
    this._currentIndex = -1;
    this._currentTimeMs = 0;
    this._notifyState();

    // Speed up events for replay
    this._config.replaySpeed = originalSpeed;

    this.play();

    // Wait until finished
    await new Promise<void>((resolve) => {
      const checkFinished = (): void => {
        if (this._state === 'finished') {
          this._isReplay = false;
          resolve();
        } else {
          setTimeout(checkFinished, 100);
        }
      };
      checkFinished();
    });
  }

  // ── State queries ──────────────────────────────────────────────────────

  getState(): LessonTimelineState {
    return {
      events: this._events,
      current_index: this._currentIndex,
      current_time_ms: this._currentTimeMs,
      state: this._state,
      total_duration_ms: this._totalDurationMs,
      progress: this._totalDurationMs > 0
        ? this._currentTimeMs / this._totalDurationMs
        : 0,
    };
  }

  getCurrentEvent(): TimelineEvent | null {
    if (this._currentIndex < 0 || this._currentIndex >= this._events.length) {
      return null;
    }
    return this._events[this._currentIndex];
  }

  isFinished(): boolean {
    return this._state === 'finished';
  }

  isReplaying(): boolean {
    return this._isReplay;
  }

  eventCount(): number {
    return this._events.length;
  }

  remainingCount(): number {
    return this._events.length - this._currentIndex - 1;
  }

  // ── Event callbacks ────────────────────────────────────────────────────

  onEvent(cb: (event: TimelineEvent) => void): () => void {
    this._eventCallbacks.push(cb);
    return () => {
      this._eventCallbacks = this._eventCallbacks.filter((f) => f !== cb);
    };
  }

  onStateChange(cb: (state: TimelineState) => void): () => void {
    this._stateCallbacks.push(cb);
    return () => {
      this._stateCallbacks = this._stateCallbacks.filter((f) => f !== cb);
    };
  }

  // ── Internals ──────────────────────────────────────────────────────────

  private _scheduleNext(): void {
    this._cancelTimer();

    const nextIndex = this._currentIndex + 1;
    if (nextIndex >= this._events.length) {
      this._state = 'finished';
      this._notifyState();
      return;
    }

    const event = this._events[nextIndex];
    const delay = event.duration_ms || this._config.defaultEventGapMs;
    const adjustedDelay = this._isReplay ? delay / this._config.replaySpeed : delay;

    this._playTimer = setTimeout(() => {
      this._currentIndex = nextIndex;
      this._currentTimeMs += event.duration_ms || this._config.defaultEventGapMs;
      this._eventCallbacks.forEach((cb) => cb(event));
      this._notifyState();
      this._scheduleNext();
    }, adjustedDelay);
  }

  private _cancelTimer(): void {
    if (this._playTimer) {
      clearTimeout(this._playTimer);
      this._playTimer = null;
    }
  }

  private _notifyState(): void {
    this._stateCallbacks.forEach((cb) => cb(this._state));
  }
}
