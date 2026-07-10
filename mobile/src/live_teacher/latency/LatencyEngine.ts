// ──────────────────────────────────────────────────────────────────────────────
// LatencyEngine — real-time latency monitoring and optimisation.
//
// Continuously measures UI, speech, pointer, drawing, and streaming latencies.
// Reports when targets are exceeded and provides hooks for subsystems to
// self-optimise. Target: UI <16ms, speech start <250ms, pointer <16ms,
// drawing <16ms, streaming first chunk immediate.
// ──────────────────────────────────────────────────────────────────────────────

import type { LatencyReport, LiveTeacherEvent } from '../types';

export interface LatencyEngineConfig {
  sample_interval_ms: number;
  report_thresholds: Partial<LatencyReport>;
  onEvent?: (event: LiveTeacherEvent) => void;
}

const DEFAULT_CONFIG: LatencyEngineConfig = {
  sample_interval_ms: 1000,
  report_thresholds: {
    ui_ms: 16,
    speech_start_ms: 250,
    pointer_update_ms: 16,
    drawing_ms: 16,
    streaming_first_chunk_ms: 100,
  },
};

export class LatencyEngine {
  private _config: LatencyEngineConfig;
  private _report: LatencyReport;
  private _samples: LatencyReport[] = [];
  private _maxSamples = 60;
  private _listeners: Set<(report: LatencyReport) => void> = new Set();
  private _interval: ReturnType<typeof setInterval> | null = null;

  constructor(config: Partial<LatencyEngineConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
    this._report = this._zeroReport();
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────

  start(): void {
    if (this._interval) return;
    this._interval = setInterval(() => {
      this._reportSample();
    }, this._config.sample_interval_ms);
  }

  stop(): void {
    if (this._interval) {
      clearInterval(this._interval);
      this._interval = null;
    }
  }

  // ── Measurements ───────────────────────────────────────────────────────

  recordUiLatency(ms: number): void {
    this._report.ui_ms = ms;
    this._checkThreshold('ui_ms', ms, 16);
  }

  recordSpeechStartLatency(ms: number): void {
    this._report.speech_start_ms = ms;
    this._checkThreshold('speech_start_ms', ms, 250);
  }

  recordPointerUpdateLatency(ms: number): void {
    this._report.pointer_update_ms = ms;
    this._checkThreshold('pointer_update_ms', ms, 16);
  }

  recordDrawingLatency(ms: number): void {
    this._report.drawing_ms = ms;
    this._checkThreshold('drawing_ms', ms, 16);
  }

  recordStreamingFirstChunk(ms: number): void {
    this._report.streaming_first_chunk_ms = ms;
    this._checkThreshold('streaming_first_chunk_ms', ms, 100);
  }

  startMeasurement(): number {
    return performance.now();
  }

  endMeasurement(startTime: number): number {
    return performance.now() - startTime;
  }

  // ── Reporting ──────────────────────────────────────────────────────────

  get report(): LatencyReport {
    return { ...this._report };
  }

  get averageReport(): LatencyReport {
    if (this._samples.length === 0) return this._zeroReport();
    const avg = this._zeroReport();
    for (const sample of this._samples) {
      avg.ui_ms += sample.ui_ms;
      avg.speech_start_ms += sample.speech_start_ms;
      avg.pointer_update_ms += sample.pointer_update_ms;
      avg.drawing_ms += sample.drawing_ms;
      avg.streaming_first_chunk_ms += sample.streaming_first_chunk_ms;
    }
    const n = this._samples.length;
    avg.ui_ms /= n;
    avg.speech_start_ms /= n;
    avg.pointer_update_ms /= n;
    avg.drawing_ms /= n;
    avg.streaming_first_chunk_ms /= n;
    return avg;
  }

  get worstReport(): LatencyReport {
    const worst = this._zeroReport();
    for (const sample of this._samples) {
      if (sample.ui_ms > worst.ui_ms) worst.ui_ms = sample.ui_ms;
      if (sample.speech_start_ms > worst.speech_start_ms) worst.speech_start_ms = sample.speech_start_ms;
      if (sample.pointer_update_ms > worst.pointer_update_ms) worst.pointer_update_ms = sample.pointer_update_ms;
      if (sample.drawing_ms > worst.drawing_ms) worst.drawing_ms = sample.drawing_ms;
      if (sample.streaming_first_chunk_ms > worst.streaming_first_chunk_ms) worst.streaming_first_chunk_ms = sample.streaming_first_chunk_ms;
    }
    return worst;
  }

  onReport(listener: (report: LatencyReport) => void): () => void {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  // ── Threshold Checking ────────────────────────────────────────────────

  isExceedingThreshold(): boolean {
    const t = this._config.report_thresholds;
    return (
      (t.ui_ms !== undefined && this._report.ui_ms > t.ui_ms) ||
      (t.speech_start_ms !== undefined && this._report.speech_start_ms > t.speech_start_ms) ||
      (t.pointer_update_ms !== undefined && this._report.pointer_update_ms > t.pointer_update_ms) ||
      (t.drawing_ms !== undefined && this._report.drawing_ms > t.drawing_ms) ||
      (t.streaming_first_chunk_ms !== undefined && this._report.streaming_first_chunk_ms > t.streaming_first_chunk_ms)
    );
  }

  // ── Private ────────────────────────────────────────────────────────────

  private _zeroReport(): LatencyReport {
    return {
      ui_ms: 0,
      speech_start_ms: 0,
      pointer_update_ms: 0,
      drawing_ms: 0,
      streaming_first_chunk_ms: 0,
      timestamp: Date.now(),
    };
  }

  private _reportSample(): void {
    this._report.timestamp = Date.now();
    this._samples.push({ ...this._report });
    if (this._samples.length > this._maxSamples) {
      this._samples.shift();
    }
    for (const listener of this._listeners) {
      listener(this._report);
    }
    if (this.isExceedingThreshold()) {
      this._config.onEvent?.({
        type: 'latency:report',
        timestamp: Date.now(),
        data: { report: this._report, thresholds: this._config.report_thresholds },
      });
    }
  }

  private _checkThreshold(key: keyof LatencyReport, value: number, target: number): void {
    if (value > target * 1.5) {
      this._config.onEvent?.({
        type: 'latency:report',
        timestamp: Date.now(),
        data: { metric: key, value, target, severity: 'warning' },
      });
    }
  }

  dispose(): void {
    this.stop();
    this._listeners.clear();
    this._samples = [];
  }
}
