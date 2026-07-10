// ──────────────────────────────────────────────────────────────────────────────
// LiveInteractionEngine — priority-based student interaction queue.
//
// Students may speak, write, draw, move their notebook, tap, interrupt, or
// express doubt. This engine assigns a priority to each interaction, queues
// it, and delegates processing to the appropriate subsystem. The director
// polls the queue to decide what to handle next.
// ──────────────────────────────────────────────────────────────────────────────

import type {
  InteractionType,
  InteractionPriority,
  StudentInteraction,
  LiveTeacherEvent,
} from '../types';

export interface LiveInteractionEngineConfig {
  max_queue_size: number;
  onEvent?: (event: LiveTeacherEvent) => void;
}

const DEFAULT_CONFIG: LiveInteractionEngineConfig = {
  max_queue_size: 50,
};

const PRIORITY_MAP: Record<InteractionType, InteractionPriority> = {
  interruption: 'critical',
  doubt: 'critical',
  speech: 'high',
  gesture: 'high',
  touch: 'normal',
  draw: 'normal',
  text: 'normal',
  notebook_move: 'normal',
};

export class LiveInteractionEngine {
  private _config: LiveInteractionEngineConfig;
  private _queue: StudentInteraction[] = [];
  private _processing = false;
  private _listeners: Set<(interaction: StudentInteraction) => void> = new Set();

  constructor(config: Partial<LiveInteractionEngineConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── Enqueue ────────────────────────────────────────────────────────────

  enqueue(type: InteractionType, data: unknown): string {
    const id = `int_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const interaction: StudentInteraction = {
      id,
      type,
      priority: PRIORITY_MAP[type],
      timestamp: Date.now(),
      data,
      processed: false,
    };

    this._queue.push(interaction);
    this._queue.sort((a, b) => this._priorityWeight(b.priority) - this._priorityWeight(a.priority));

    if (this._queue.length > this._config.max_queue_size) {
      this._queue.pop();
    }

    this._config.onEvent?.({
      type: 'interaction:received',
      timestamp: interaction.timestamp,
      data: { id, type, priority: interaction.priority },
    });

    return id;
  }

  // ── Dequeue ────────────────────────────────────────────────────────────

  dequeue(): StudentInteraction | null {
    if (this._queue.length === 0) return null;
    const interaction = this._queue.shift()!;
    this._config.onEvent?.({
      type: 'interaction:processed',
      timestamp: Date.now(),
      data: { id: interaction.id, type: interaction.type },
    });
    return interaction;
  }

  peek(): StudentInteraction | null {
    return this._queue[0] ?? null;
  }

  // ── Filtered Dequeue ───────────────────────────────────────────────────

  dequeueByType(type: InteractionType): StudentInteraction | null {
    const idx = this._queue.findIndex((i) => i.type === type);
    if (idx === -1) return null;
    const interaction = this._queue.splice(idx, 1)[0];
    return interaction;
  }

  dequeueCritical(): StudentInteraction | null {
    const idx = this._queue.findIndex((i) => i.priority === 'critical');
    if (idx === -1) return null;
    return this._queue.splice(idx, 1)[0];
  }

  // ── Queue Inspection ───────────────────────────────────────────────────

  get queue(): readonly StudentInteraction[] {
    return [...this._queue];
  }

  get size(): number {
    return this._queue.length;
  }

  hasCritical(): boolean {
    return this._queue.some((i) => i.priority === 'critical');
  }

  hasType(type: InteractionType): boolean {
    return this._queue.some((i) => i.type === type);
  }

  clear(): void {
    this._queue = [];
  }

  remove(id: string): void {
    this._queue = this._queue.filter((i) => i.id !== id);
  }

  // ── Processing ─────────────────────────────────────────────────────────

  markProcessing(): void {
    this._processing = true;
  }

  markDone(): void {
    this._processing = false;
  }

  get isProcessing(): boolean {
    return this._processing;
  }

  // ── Priority Weight ────────────────────────────────────────────────────

  private _priorityWeight(priority: InteractionPriority): number {
    switch (priority) {
      case 'critical': return 100;
      case 'high': return 50;
      case 'normal': return 10;
      case 'low': return 1;
    }
  }

  dispose(): void {
    this.clear();
    this._listeners.clear();
  }
}
