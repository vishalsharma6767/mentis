// ──────────────────────────────────────────────────────────────────────────────
// StreamingEngine — WebSocket-based real-time streaming from the Mentis backend.
//
// Streams: speech chunks, drawing strokes, pointer positions, animation
// triggers, scene graph updates, teaching decisions, timeline sync, memory
// updates.
//
// Handles reconnection, message ordering, heartbeat, and backpressure.
// ──────────────────────────────────────────────────────────────────────────────

import type { StreamMessage, StreamMessageType, StreamState } from '../types';

// ── Configuration ────────────────────────────────────────────────────────────

export interface StreamingConfig {
  /** WebSocket URL (wss://...) */
  url: string;
  /** Reconnect delay on failure (ms) */
  reconnectDelayMs: number;
  /** Maximum reconnection attempts (0 = infinite) */
  maxReconnectAttempts: number;
  /** Heartbeat interval (ms) */
  heartbeatIntervalMs: number;
  /** Connection timeout (ms) */
  connectionTimeoutMs: number;
  /** Max queued outbound messages */
  maxQueueSize: number;
  /** Session ID for authentication */
  sessionId?: string;
}

const DEFAULT_CONFIG: StreamingConfig = {
  url: '',
  reconnectDelayMs: 2000,
  maxReconnectAttempts: 10,
  heartbeatIntervalMs: 5000,
  connectionTimeoutMs: 10000,
  maxQueueSize: 100,
};

// ── StreamingEngine ──────────────────────────────────────────────────────────

export class StreamingEngine {
  private _config: StreamingConfig;
  private _ws: WebSocket | null = null;
  private _reconnectAttempts = 0;
  private _isConnected = false;
  private _sequenceNumber = 0;
  private _heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private _connectionTimer: ReturnType<typeof setTimeout> | null = null;
  private _shouldReconnect = false;

  private _messageCallbacks: Array<(msg: StreamMessage) => void> = [];
  private _connectionCallbacks: Array<(connected: boolean) => void> = [];
  private _outbox: StreamMessage[] = [];

  private _lastHeartbeatTime = 0;
  private _messagesSent = 0;
  private _messagesReceived = 0;

  constructor(config: Partial<StreamingConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── Connection lifecycle ───────────────────────────────────────────────

  async connect(url?: string): Promise<void> {
    if (url) this._config.url = url;
    if (!this._config.url) {
      throw new Error('StreamingEngine: no WebSocket URL configured');
    }

    this._shouldReconnect = true;
    return this._connect();
  }

  disconnect(): void {
    this._shouldReconnect = false;
    this._cleanup();
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
    this._isConnected = false;
    this._notifyConnection(false);
  }

  isConnected(): boolean {
    return this._isConnected;
  }

  getState(): StreamState {
    return {
      connected: this._isConnected,
      latency_ms: this._estimateLatency(),
      last_heartbeat: this._lastHeartbeatTime,
      queued_messages: this._outbox.length,
    };
  }

  // ── Messaging ──────────────────────────────────────────────────────────

  send(message: Omit<StreamMessage, 'timestamp' | 'sequence'>): void {
    const msg: StreamMessage = {
      ...message,
      timestamp: Date.now(),
      sequence: this._sequenceNumber++,
    };

    if (this._isConnected && this._ws?.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify(msg));
      this._messagesSent++;
    } else {
      if (this._outbox.length < this._config.maxQueueSize) {
        this._outbox.push(msg);
      } else {
        console.warn('[StreamingEngine] outbox full, dropping message');
      }
    }
  }

  onMessage(cb: (msg: StreamMessage) => void): () => void {
    this._messageCallbacks.push(cb);
    return () => {
      this._messageCallbacks = this._messageCallbacks.filter((f) => f !== cb);
    };
  }

  onConnectionChange(cb: (connected: boolean) => void): () => void {
    this._connectionCallbacks.push(cb);
    return () => {
      this._connectionCallbacks = this._connectionCallbacks.filter((f) => f !== cb);
    };
  }

  // ── Stats ──────────────────────────────────────────────────────────────

  getMessagesSent(): number {
    return this._messagesSent;
  }

  getMessagesReceived(): number {
    return this._messagesReceived;
  }

  // ── Internals ──────────────────────────────────────────────────────────

  private _connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this._ws = new WebSocket(this._config.url);

        this._ws.onopen = () => {
          this._isConnected = true;
          this._reconnectAttempts = 0;
          this._startHeartbeat();
          this._flushOutbox();
          this._notifyConnection(true);

          if (this._connectionTimer) {
            clearTimeout(this._connectionTimer);
            this._connectionTimer = null;
          }

          // Authenticate
          if (this._config.sessionId) {
            this.send({
              type: 'heartbeat',
              ack_required: false,
              data: {
                type: 'auth',
                session_id: this._config.sessionId,
              },
            });
          }

          resolve();
        };

        this._ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data) as StreamMessage;
            this._messagesReceived++;

            if (msg.type === 'heartbeat') {
              this._lastHeartbeatTime = Date.now();
              return;
            }

            this._messageCallbacks.forEach((cb) => cb(msg));
          } catch {
            console.warn('[StreamingEngine] failed to parse message');
          }
        };

        this._ws.onerror = () => {
          this._isConnected = false;
          this._notifyConnection(false);
        };

        this._ws.onclose = () => {
          this._isConnected = false;
          this._stopHeartbeat();
          this._notifyConnection(false);

          if (this._shouldReconnect) {
            this._scheduleReconnect();
          }
        };

        // Connection timeout
        this._connectionTimer = setTimeout(() => {
          if (!this._isConnected) {
            this._cleanup();
            reject(new Error('StreamingEngine: connection timeout'));
          }
        }, this._config.connectionTimeoutMs);
      } catch (error) {
        reject(error);
      }
    });
  }

  private _scheduleReconnect(): void {
    if (this._config.maxReconnectAttempts > 0 &&
        this._reconnectAttempts >= this._config.maxReconnectAttempts) {
      console.warn('[StreamingEngine] max reconnect attempts reached');
      return;
    }

    this._reconnectAttempts++;
    console.log(
      `[StreamingEngine] reconnecting in ${this._config.reconnectDelayMs}ms ` +
      `(attempt ${this._reconnectAttempts})`,
    );

    setTimeout(() => {
      this._connect().catch((err) => {
        console.warn('[StreamingEngine] reconnect failed:', err);
      });
    }, this._config.reconnectDelayMs);
  }

  private _flushOutbox(): void {
    while (this._outbox.length > 0 && this._ws?.readyState === WebSocket.OPEN) {
      const msg = this._outbox.shift()!;
      this._ws.send(JSON.stringify(msg));
      this._messagesSent++;
    }
  }

  private _startHeartbeat(): void {
    this._stopHeartbeat();
    this._heartbeatInterval = setInterval(() => {
      if (this._isConnected && this._ws?.readyState === WebSocket.OPEN) {
        this.send({
          type: 'heartbeat',
          ack_required: false,
          data: { timestamp: Date.now() },
        });
      }
    }, this._config.heartbeatIntervalMs);
  }

  private _stopHeartbeat(): void {
    if (this._heartbeatInterval) {
      clearInterval(this._heartbeatInterval);
      this._heartbeatInterval = null;
    }
  }

  private _cleanup(): void {
    this._stopHeartbeat();
    if (this._connectionTimer) {
      clearTimeout(this._connectionTimer);
      this._connectionTimer = null;
    }
  }

  private _notifyConnection(connected: boolean): void {
    this._connectionCallbacks.forEach((cb) => cb(connected));
  }

  private _estimateLatency(): number {
    if (!this._lastHeartbeatTime) return 0;
    return Date.now() - this._lastHeartbeatTime;
  }
}
