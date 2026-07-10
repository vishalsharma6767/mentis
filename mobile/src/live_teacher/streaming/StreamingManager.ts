// ──────────────────────────────────────────────────────────────────────────────
// StreamingManager — multi-stream orchestrator for the live teacher.
//
// Manages concurrent streams of different types (LLM, speech, drawing, pointer,
// AR, captions, memory, homework, quiz). Supports cancellation and resume per
// stream session.
//
// The teacher never waits for a full response — chunks are forwarded as they
// arrive to the appropriate downstream consumers.
// ──────────────────────────────────────────────────────────────────────────────

import type {
  StreamType,
  StreamStatus,
  StreamChunk,
  StreamSession,
  StreamCallback,
  LiveTeacherEvent,
} from '../types';

export interface StreamingManagerConfig {
  max_concurrent_streams: number;
  chunk_timeout_ms: number;
  onEvent?: (event: LiveTeacherEvent) => void;
}

const DEFAULT_CONFIG: StreamingManagerConfig = {
  max_concurrent_streams: 12,
  chunk_timeout_ms: 30000,
};

interface InternalSession extends StreamSession {
  callbacks: Set<StreamCallback>;
  _resolve?: () => void;
  _reject?: (err: Error) => void;
  _timer?: ReturnType<typeof setTimeout>;
}

export class StreamingManager {
  private _config: StreamingManagerConfig;
  private _sessions: Map<string, InternalSession> = new Map();
  private _globalCallbacks: Set<StreamCallback> = new Set();

  constructor(config: Partial<StreamingManagerConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── Session Management ─────────────────────────────────────────────────

  createSession(
    type: StreamType,
    metadata: Record<string, unknown> = {},
  ): { session_id: string; commit: () => void; cancel: () => void } {
    const id = `stream_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const session: InternalSession = {
      id,
      type,
      status: 'active',
      started_at: Date.now(),
      chunks_received: 0,
      metadata,
      callbacks: new Set(this._globalCallbacks),
    };

    this._sessions.set(id, session);
    this._startTimeout(session);

    return {
      session_id: id,
      commit: () => this._completeSession(id),
      cancel: () => this.cancelSession(id),
    };
  }

  pushChunk<T>(sessionId: string, data: T): void {
    const session = this._sessions.get(sessionId);
    if (!session || session.status === 'cancelled') return;

    const chunk: StreamChunk<T> = {
      type: session.type,
      data,
      timestamp: Date.now(),
      sequence: session.chunks_received,
      stream_id: sessionId,
    };

    session.chunks_received++;
    this._resetTimeout(session);

    for (const cb of session.callbacks) {
      try {
        cb(chunk);
      } catch { /* consumer error */ }
    }

    this._config.onEvent?.({
      type: 'stream:chunk',
      timestamp: chunk.timestamp,
      data: { session_id: sessionId, type: session.type, sequence: chunk.sequence },
    });
  }

  subscribe<T = unknown>(
    sessionId: string,
    callback: StreamCallback<T>,
  ): () => void {
    const session = this._sessions.get(sessionId);
    if (session) {
      session.callbacks.add(callback as StreamCallback);
    }
    return () => {
      this._sessions.get(sessionId)?.callbacks.delete(callback as StreamCallback);
    };
  }

  subscribeAll<T = unknown>(callback: StreamCallback<T>): () => void {
    this._globalCallbacks.add(callback as StreamCallback);
    return () => {
      this._globalCallbacks.delete(callback as StreamCallback);
    };
  }

  cancelSession(sessionId: string): void {
    const session = this._sessions.get(sessionId);
    if (!session || session.status === 'cancelled') return;

    session.status = 'cancelled';
    this._clearTimer(session);
    session._reject?.(new Error('Stream cancelled'));
    this._teardown(sessionId);

    this._config.onEvent?.({
      type: 'stream:cancel',
      timestamp: Date.now(),
      data: { session_id: sessionId, type: session.type },
    });
  }

  cancelByType(type: StreamType): void {
    for (const [id, session] of this._sessions) {
      if (session.type === type) {
        this.cancelSession(id);
      }
    }
  }

  cancelAll(): void {
    for (const [id] of this._sessions) {
      this.cancelSession(id);
    }
  }

  resumeSession(sessionId: string): void {
    const session = this._sessions.get(sessionId);
    if (session?.status === 'paused') {
      session.status = 'active';
      this._resetTimeout(session);
    }
  }

  pauseSession(sessionId: string): void {
    const session = this._sessions.get(sessionId);
    if (session?.status === 'active') {
      session.status = 'paused';
      this._clearTimer(session);
    }
  }

  getSession(sessionId: string): Readonly<StreamSession> | undefined {
    const s = this._sessions.get(sessionId);
    if (!s) return undefined;
    return {
      id: s.id,
      type: s.type,
      status: s.status,
      started_at: s.started_at,
      chunks_received: s.chunks_received,
      metadata: { ...s.metadata },
    };
  }

  getSessionsByType(type: StreamType): Readonly<StreamSession>[] {
    const result: StreamSession[] = [];
    for (const s of this._sessions.values()) {
      if (s.type === type) {
        result.push({
          id: s.id,
          type: s.type,
          status: s.status,
          started_at: s.started_at,
          chunks_received: s.chunks_received,
          metadata: { ...s.metadata },
        });
      }
    }
    return result;
  }

  activeCount(): number {
    let count = 0;
    for (const s of this._sessions.values()) {
      if (s.status === 'active') count++;
    }
    return count;
  }

  // ── Private ────────────────────────────────────────────────────────────

  private _completeSession(sessionId: string): void {
    const session = this._sessions.get(sessionId);
    if (!session || session.status !== 'active') return;

    session.status = 'completed';
    this._clearTimer(session);
    session._resolve?.();
    this._teardown(sessionId);

    this._config.onEvent?.({
      type: 'stream:complete',
      timestamp: Date.now(),
      data: { session_id: sessionId, type: session.type, chunks: session.chunks_received },
    });
  }

  private _startTimeout(session: InternalSession): void {
    session._timer = setTimeout(() => {
      this.cancelSession(session.id);
    }, this._config.chunk_timeout_ms);
  }

  private _resetTimeout(session: InternalSession): void {
    this._clearTimer(session);
    this._startTimeout(session);
  }

  private _clearTimer(session: InternalSession): void {
    if (session._timer) {
      clearTimeout(session._timer);
      session._timer = undefined;
    }
  }

  private _teardown(sessionId: string): void {
    this._sessions.delete(sessionId);
  }

  dispose(): void {
    this.cancelAll();
    this._globalCallbacks.clear();
  }
}
