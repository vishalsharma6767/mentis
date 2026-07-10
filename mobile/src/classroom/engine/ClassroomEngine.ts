// ──────────────────────────────────────────────────────────────────────────────
// Mentis Classroom Engine — Main Orchestrator
// ──────────────────────────────────────────────────────────────────────────────
// Wires every subsystem together.  Single entry point for the UI layer.
//
// Usage (in a React component):
//   const engine = useClassroomEngine();
//   engine.start(sessionId);
//   engine.on('state_changed', ...);

import type { SharedValue } from 'react-native-reanimated';
import { useSharedValue } from 'react-native-reanimated';

import type {
  BoardElement,
  ClassroomEvent,
  ClassroomEventType,
  DebugInfo,
  EventListener,
  GestureAction,
  LessonTimelineState,
  NotebookFrame,
  PerformanceMetrics,
  PointerMode,
  PointerState,
  SceneGraphDTO,
  StreamMessage,
  StudentInteraction,
  TeacherActivity,
  TeacherState,
  TeachingDecisionDTO,
  TimelineEvent,
  TimelineState,
} from '../types';

// Forward-declare subsystem interfaces so we can inject them.
// Each subsystem exports its own type that satisfies these contracts.

export interface NotebookTrackerInterface {
  start(): Promise<void>;
  stop(): void;
  getCurrentFrame(): NotebookFrame | null;
  onFrame(cb: (frame: NotebookFrame) => void): () => void;
}

export interface WhiteboardEngineInterface {
  addElement(element: BoardElement): void;
  removeElement(id: string): void;
  clear(): void;
  getElements(): BoardElement[];
  undo(): void;
  redo(): void;
  getLayerElements(layer: number): BoardElement[];
}

export interface PenEngineInterface {
  startStroke(x: number, y: number, pressure: number): void;
  continueStroke(x: number, y: number, pressure: number): void;
  endStroke(): string | null;
  clear(): void;
  replayStroke(id: string, speed?: number): Promise<void>;
  getActiveStrokeId(): string | null;
}

export interface PointerEngineInterface {
  setMode(mode: PointerMode): void;
  moveTo(x: number, y: number): void;
  tap(x: number, y: number): void;
  hide(): void;
  show(): void;
  getState(): PointerState;
}

export interface AnimationEngineInterface {
  play(type: string, targetId: string, props: Record<string, unknown>): Promise<void>;
  playSequence(animations: Array<{ type: string; targetId: string; props: Record<string, unknown> }>): Promise<void>;
  cancel(targetId: string): void;
  cancelAll(): void;
}

export interface GestureEngineInterface {
  playGesture(gesture: GestureAction): Promise<void>;
  cancelGesture(): void;
}

export interface StreamingEngineInterface {
  connect(url: string): Promise<void>;
  disconnect(): void;
  send(message: StreamMessage): void;
  onMessage(cb: (msg: StreamMessage) => void): () => void;
  isConnected(): boolean;
}

export interface LessonTimelineInterface {
  loadEvents(events: TimelineEvent[]): void;
  play(): void;
  pause(): void;
  resume(): void;
  seek(timeMs: number): void;
  next(): Promise<TimelineEvent | null>;
  previous(): TimelineEvent | null;
  getState(): LessonTimelineState;
  onEvent(cb: (event: TimelineEvent) => void): () => void;
}

export interface SceneGraphManagerInterface {
  loadSceneGraph(dto: SceneGraphDTO): void;
  getQuestionNodes(): SceneGraphDTO['nodes'];
  getMistakeNodes(): SceneGraphDTO['nodes'];
  getConceptNodes(): SceneGraphDTO['nodes'];
  getRootNodes(): string[];
}

export interface TeacherStateManagerInterface {
  setActivity(activity: TeacherActivity): void;
  setFocus(focus: string): void;
  setSpeech(text: string): void;
  setWaiting(waiting: boolean): void;
  getState(): TeacherState;
  onStateChange(cb: (state: TeacherState) => void): () => void;
}

export interface InteractionEngineInterface {
  handleStudentInteraction(interaction: StudentInteraction): void;
  isInterrupting(): boolean;
  clearInteraction(): void;
  onInteraction(cb: (interaction: StudentInteraction) => void): () => void;
}

export interface LayeredRendererInterface {
  setLayerVisibility(name: string, visible: boolean): void;
  setLayerOpacity(name: string, opacity: number): void;
  requestRedraw(layerName?: string): void;
  getPerformanceMetrics(): PerformanceMetrics;
  getDebugInfo(): DebugInfo;
}

// ──────────────────────────────────────────────────────────────────────────────

export interface ClassroomEngineConfig {
  wsUrl?: string;
  sessionId?: string;
  onError?: (error: Error) => void;
}

export class ClassroomEngine {
  // Subsystems
  public notebookTracker!: NotebookTrackerInterface;
  public whiteboard!: WhiteboardEngineInterface;
  public pen!: PenEngineInterface;
  public pointer!: PointerEngineInterface;
  public animation!: AnimationEngineInterface;
  public gesture!: GestureEngineInterface;
  public streaming!: StreamingEngineInterface;
  public timeline!: LessonTimelineInterface;
  public sceneGraph!: SceneGraphManagerInterface;
  public teacherState!: TeacherStateManagerInterface;
  public interaction!: InteractionEngineInterface;
  public renderer!: LayeredRendererInterface;

  // Reactive state exposed to UI
  public readonly isRunning: SharedValue<boolean>;
  public readonly currentActivity: SharedValue<TeacherActivity>;
  public readonly currentFocus: SharedValue<string>;
  public readonly isWaiting: SharedValue<boolean>;
  public readonly timelineState: SharedValue<TimelineState>;
  public readonly streamingConnected: SharedValue<boolean>;
  public readonly trackingQuality: SharedValue<string>;
  public readonly fps: SharedValue<number>;

  private readonly _eventListeners = new Map<string, Set<EventListener>>();
  private readonly _subsystemCleanups: Array<() => void> = [];
  private _sessionId: string;
  private _config: ClassroomEngineConfig;
  private _metricsInterval: ReturnType<typeof setInterval> | null = null;

  constructor(config: ClassroomEngineConfig = {}) {
    this._config = config;
    this._sessionId = config.sessionId ?? '';

    this.isRunning = useSharedValue(false);
    this.currentActivity = useSharedValue<TeacherActivity>('idle');
    this.currentFocus = useSharedValue('');
    this.isWaiting = useSharedValue(false);
    this.timelineState = useSharedValue<TimelineState>('idle');
    this.streamingConnected = useSharedValue(false);
    this.trackingQuality = useSharedValue('lost');
    this.fps = useSharedValue(0);
  }

  // ── Lifecycle ───────────────────────────────────────────────────────────

  async start(sessionId?: string): Promise<void> {
    if (this.isRunning.value) return;

    this._sessionId = sessionId ?? this._sessionId;
    this._emit('state_changed', { action: 'start', sessionId: this._sessionId });

    try {
      // 1. Start notebook tracking
      await this.notebookTracker.start();
      this._subsystemCleanups.push(
        this.notebookTracker.onFrame((frame) => {
          this.trackingQuality.value = frame.quality;
          this._emit('notebook_tracking_updated', { frame });
        }),
      );

      // 2. Connect streaming
      if (this._config.wsUrl) {
        await this.streaming.connect(this._config.wsUrl);
        this.streamingConnected.value = true;
        this._subsystemCleanups.push(
          this.streaming.onMessage((msg) => this._handleStreamMessage(msg)),
        );
      }

      // 3. Wire timeline events
      this._subsystemCleanups.push(
        this.timeline.onEvent((event) => this._onTimelineEvent(event)),
      );

      // 4. Wire teacher state changes
      this._subsystemCleanups.push(
        this.teacherState.onStateChange((state) => {
          this.currentActivity.value = state.activity;
          this.currentFocus.value = state.current_focus;
          this.isWaiting.value = state.is_waiting_for_student;
        }),
      );

      // 5. Wire student interactions
      this._subsystemCleanups.push(
        this.interaction.onInteraction((interaction) => {
          this._emit('student_interaction', { interaction });
          if (interaction.type === 'speech' || interaction.type === 'touch') {
            this.timeline.pause();
          }
        }),
      );

      // 6. Start metrics collection
      this._startMetricsCollection();

      this.isRunning.value = true;
      this._emit('state_changed', { action: 'started', sessionId: this._sessionId });
    } catch (error) {
      this._handleError(error as Error);
      throw error;
    }
  }

  stop(): void {
    if (!this.isRunning.value) return;

    this._cleanupSubsystems();
    this.notebookTracker.stop();
    this.streaming.disconnect();
    this.animation.cancelAll();
    this.isRunning.value = false;

    this._emit('state_changed', { action: 'stopped' });
  }

  // ── Lesson control ──────────────────────────────────────────────────────

  playLesson(): void {
    this.timeline.play();
    this.timelineState.value = 'playing';
  }

  pauseLesson(): void {
    this.timeline.pause();
    this.timelineState.value = 'paused';
  }

  resumeLesson(): void {
    this.timeline.resume();
    this.timelineState.value = 'playing';
  }

  seekLesson(timeMs: number): void {
    this.timeline.seek(timeMs);
    this.timelineState.value = 'seeking';
  }

  nextStep(): void {
    this.timeline.next();
  }

  // ── Event bus ───────────────────────────────────────────────────────────

  on(eventType: ClassroomEventType, listener: EventListener): () => void {
    if (!this._eventListeners.has(eventType)) {
      this._eventListeners.set(eventType, new Set());
    }
    this._eventListeners.get(eventType)!.add(listener);
    return () => this._eventListeners.get(eventType)?.delete(listener);
  }

  off(eventType: ClassroomEventType, listener: EventListener): void {
    this._eventListeners.get(eventType)?.delete(listener);
  }

  // ── Internal ────────────────────────────────────────────────────────────

  private _emit(type: ClassroomEventType, data: Record<string, unknown>): void {
    const event: ClassroomEvent = {
      type,
      timestamp: Date.now(),
      source: 'ClassroomEngine',
      data,
    };
    this._eventListeners.get(type)?.forEach((listener) => {
      try {
        listener(event);
      } catch (err) {
        console.warn(`[ClassroomEngine] listener error for ${type}:`, err);
      }
    });
    // Wildcard listeners
    this._eventListeners.get('*' as ClassroomEventType)?.forEach((listener) => {
      try {
        listener(event);
      } catch (err) {
        console.warn(`[ClassroomEngine] wildcard listener error:`, err);
      }
    });
  }

  private _handleStreamMessage(msg: StreamMessage): void {
    switch (msg.type) {
      case 'scene_graph':
        this.sceneGraph.loadSceneGraph(msg.data as unknown as SceneGraphDTO);
        this._emit('scene_graph_received', msg.data);
        break;

      case 'teaching_decision': {
        const decision = msg.data as unknown as TeachingDecisionDTO;
        this.teacherState.setFocus(decision.focus.current_focus);
        this._emit('teaching_decision_received', msg.data);
        break;
      }

      case 'board_update': {
        const element = msg.data as unknown as BoardElement;
        this.whiteboard.addElement(element);
        this.renderer.requestRedraw('teacher_ink');
        this._emit('board_element_added', msg.data);
        break;
      }

      case 'pointer_update': {
        const { x, y } = msg.data as { x: number; y: number };
        this.pointer.moveTo(x, y);
        break;
      }

      case 'speech_chunk': {
        const text = (msg.data as { text: string }).text;
        this.teacherState.setSpeech(text);
        break;
      }

      case 'animation_trigger': {
        const animData = msg.data as {
          type: string;
          targetId: string;
          properties: Record<string, unknown>;
        };
        this.animation.play(animData.type, animData.targetId, animData.properties);
        break;
      }

      case 'timeline_sync': {
        const events = msg.data as { events: TimelineEvent[] };
        this.timeline.loadEvents(events.events);
        this._emit('timeline_event', { events: events.events });
        break;
      }
    }
  }

  private async _onTimelineEvent(event: TimelineEvent): Promise<void> {
    this._emit('timeline_event', { event });

    // Execute timeline event actions
    if (event.board_action) {
      const action = event.board_action;
      if (action.action === 'write') {
        this.pen.startStroke(action.position.x, action.position.y, 1);
        // Simulate stroke continuation
        for (let i = 0; i < 5; i++) {
          this.pen.continueStroke(
            action.position.x + i * 5,
            action.position.y,
            0.8,
          );
        }
        this.pen.endStroke();
      }
      this.renderer.requestRedraw('teacher_ink');
    }

    if (event.pointer_action) {
      this.pointer.moveTo(
        event.pointer_action.position.x,
        event.pointer_action.position.y,
      );
    }

    if (event.animation) {
      await this.animation.play(
        event.animation.type,
        event.animation.target_id ?? '',
        event.animation.properties,
      );
    }

    this._emit('state_changed', {
      action: 'timeline_progress',
      current_index: this.timeline.getState().current_index,
      progress: this.timeline.getState().progress,
    });
  }

  private _handleError(error: Error): void {
    console.error('[ClassroomEngine]', error);
    this._config.onError?.(error);
    this._emit('error', { message: error.message, stack: error.stack });
  }

  private _startMetricsCollection(): void {
    this._metricsInterval = setInterval(() => {
      const metrics = this.renderer.getPerformanceMetrics();
      this.fps.value = metrics.fps;
    }, 1000);
  }

  private _cleanupSubsystems(): void {
    this._subsystemCleanups.forEach((cleanup) => cleanup());
    this._subsystemCleanups.length = 0;
    if (this._metricsInterval) {
      clearInterval(this._metricsInterval);
      this._metricsInterval = null;
    }
  }
}

// ── React hook ──────────────────────────────────────────────────────────────

import { useMemo } from 'react';

let _globalEngine: ClassroomEngine | null = null;

export function useClassroomEngine(config?: ClassroomEngineConfig): ClassroomEngine {
  return useMemo(() => {
    if (!_globalEngine) {
      _globalEngine = new ClassroomEngine(config);
    }
    return _globalEngine;
  }, []);
}

export function getClassroomEngine(): ClassroomEngine {
  if (!_globalEngine) {
    throw new Error('ClassroomEngine not initialized. Call useClassroomEngine() first.');
  }
  return _globalEngine;
}
