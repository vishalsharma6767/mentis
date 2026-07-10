// ──────────────────────────────────────────────────────────────────────────────
// AnalyticsEngine — tracks lesson quality metrics in real time.
//
// Measures student engagement, teacher response time, pause durations,
// interruption frequency, lesson completion, pointer accuracy, streaming
// quality, and speech latency. Provides both live snapshots and aggregated
// reports for post-lesson analysis.
// ──────────────────────────────────────────────────────────────────────────────

import type { AnalyticsEvent, LessonAnalytics, LiveTeacherEvent } from '../types';

export interface AnalyticsEngineConfig {
  session_id: string;
  report_interval_ms: number;
  onEvent?: (event: LiveTeacherEvent) => void;
}

const DEFAULT_CONFIG: AnalyticsEngineConfig = {
  session_id: '',
  report_interval_ms: 5000,
};

export class AnalyticsEngine {
  private _config: AnalyticsEngineConfig;
  private _events: AnalyticsEvent[] = [];
  private _lessonAnalytics: LessonAnalytics;
  private _startTime = 0;
  private _totalPauseMs = 0;
  private _totalResponseMs = 0;
  private _responseCount = 0;
  private _interruptionCount = 0;
  private _totalPointerMovement = 0;
  private _accuratePointerMovements = 0;
  private _streamingChunksReceived = 0;
  private _streamingChunksExpected = 0;
  private _speechLatencySum = 0;
  private _speechLatencyCount = 0;
  private _listeners: Set<(analytics: LessonAnalytics) => void> = new Set();
  private _interval: ReturnType<typeof setInterval> | null = null;

  constructor(config: Partial<AnalyticsEngineConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
    this._lessonAnalytics = this._zeroAnalytics();
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────

  start(): void {
    this._startTime = Date.now();
    if (this._interval) return;
    this._interval = setInterval(() => {
      this._updateAnalytics();
    }, this._config.report_interval_ms);
  }

  stop(): void {
    if (this._interval) {
      clearInterval(this._interval);
      this._interval = null;
    }
  }

  // ── Event Tracking ─────────────────────────────────────────────────────

  trackEvent(type: string, data: Record<string, unknown>): void {
    const event: AnalyticsEvent = {
      event_id: `evt_${Date.now()}_${this._events.length}`,
      type,
      timestamp: Date.now(),
      data,
      session_id: this._config.session_id,
    };
    this._events.push(event);
    if (this._events.length > 1000) {
      this._events.splice(0, this._events.length - 1000);
    }
    this._config.onEvent?.({
      type: 'analytics:event',
      timestamp: event.timestamp,
      data: event,
    });
  }

  // ── Metric Recorders ───────────────────────────────────────────────────

  recordTeacherResponse(ms: number): void {
    this._totalResponseMs += ms;
    this._responseCount++;
  }

  recordPause(ms: number): void {
    this._totalPauseMs += ms;
  }

  recordInterruption(): void {
    this._interruptionCount++;
  }

  recordPointerMovement(accurate: boolean): void {
    this._totalPointerMovement++;
    if (accurate) this._accuratePointerMovements++;
  }

  recordStreamingQuality(received: number, expected: number): void {
    this._streamingChunksReceived += received;
    this._streamingChunksExpected += expected;
  }

  recordSpeechLatency(ms: number): void {
    this._speechLatencySum += ms;
    this._speechLatencyCount++;
  }

  // ── Analytics Access ───────────────────────────────────────────────────

  get current(): LessonAnalytics {
    return { ...this._lessonAnalytics };
  }

  get allEvents(): readonly AnalyticsEvent[] {
    return [...this._events];
  }

  get sessionDurationMs(): number {
    return this._startTime > 0 ? Date.now() - this._startTime : 0;
  }

  onUpdate(listener: (analytics: LessonAnalytics) => void): () => void {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  generateReport(): { summary: LessonAnalytics; duration_ms: number; event_count: number } {
    return {
      summary: { ...this._lessonAnalytics },
      duration_ms: this.sessionDurationMs,
      event_count: this._events.length,
    };
  }

  // ── Private ────────────────────────────────────────────────────────────

  private _updateAnalytics(): void {
    this._lessonAnalytics = {
      student_engagement: this._calculateEngagement(),
      teacher_response_time_ms: this._responseCount > 0 ? this._totalResponseMs / this._responseCount : 0,
      pause_duration_ms: this._totalPauseMs,
      interruption_count: this._interruptionCount,
      lesson_completion: this._calculateCompletion(),
      pointer_accuracy: this._totalPointerMovement > 0 ? this._accuratePointerMovements / this._totalPointerMovement : 0,
      streaming_quality: this._streamingChunksExpected > 0 ? this._streamingChunksReceived / this._streamingChunksExpected : 0,
      speech_latency_ms: this._speechLatencyCount > 0 ? this._speechLatencySum / this._speechLatencyCount : 0,
    };
    for (const listener of this._listeners) {
      listener(this._lessonAnalytics);
    }
  }

  private _calculateEngagement(): number {
    const duration = this.sessionDurationMs;
    if (duration < 1000) return 0;
    const pauseRatio = Math.min(1, this._totalPauseMs / duration);
    const interruptionBonus = Math.min(0.2, this._interruptionCount * 0.02);
    const baseEngagement = 0.7;
    const pausePenalty = pauseRatio * 0.3;
    return Math.max(0, Math.min(1, baseEngagement - pausePenalty + interruptionBonus));
  }

  private _calculateCompletion(): number {
    // Placeholder: would be driven by actual lesson progress
    return Math.min(1, this._events.length / 100);
  }

  private _zeroAnalytics(): LessonAnalytics {
    return {
      student_engagement: 0,
      teacher_response_time_ms: 0,
      pause_duration_ms: 0,
      interruption_count: 0,
      lesson_completion: 0,
      pointer_accuracy: 0,
      streaming_quality: 0,
      speech_latency_ms: 0,
    };
  }

  dispose(): void {
    this.stop();
    this._listeners.clear();
    this._events = [];
  }
}
