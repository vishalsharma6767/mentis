// ──────────────────────────────────────────────────────────────────────────────
// Live Teacher System — shared type definitions
// ──────────────────────────────────────────────────────────────────────────────

// ── Stream Types ─────────────────────────────────────────────────────────────

export type StreamType =
  | 'llm'
  | 'speech'
  | 'drawing'
  | 'pointer'
  | 'ar'
  | 'captions'
  | 'memory'
  | 'homework'
  | 'quiz';

export type StreamStatus = 'active' | 'cancelled' | 'completed' | 'paused';

export interface StreamChunk<T = unknown> {
  type: StreamType;
  data: T;
  timestamp: number;
  sequence: number;
  stream_id: string;
}

export interface StreamSession {
  id: string;
  type: StreamType;
  status: StreamStatus;
  started_at: number;
  chunks_received: number;
  metadata: Record<string, unknown>;
}

export type StreamCallback<T = unknown> = (chunk: StreamChunk<T>) => void;

// ── Speech Types ─────────────────────────────────────────────────────────────

export type SpeechState = 'idle' | 'speaking' | 'paused' | 'thinking' | 'waiting';

export interface SpeechRequest {
  text: string;
  emotion?: EmotionState;
  priority: number;
  queue_position?: number;
}

export interface SpeechSegment {
  text: string;
  start_ms: number;
  duration_ms: number;
  emotion: EmotionState;
}

// ── Conversation Types ───────────────────────────────────────────────────────

export type ConversationRole = 'teacher' | 'student';
export type ConversationState = 'greeting' | 'explaining' | 'questioning' | 'listening' | 'evaluating' | 'encouraging' | 'clarifying' | 'idle';

export interface ConversationTurn {
  role: ConversationRole;
  text: string;
  timestamp: number;
  emotion?: EmotionState;
  turn_id: string;
}

export interface ConversationContext {
  turns: ConversationTurn[];
  current_state: ConversationState;
  topic: string;
  doubt_mode: boolean;
  interruption_count: number;
}

// ── Emotion Types ────────────────────────────────────────────────────────────

export type EmotionType =
  | 'encouragement'
  | 'curiosity'
  | 'excitement'
  | 'patience'
  | 'concern'
  | 'celebration'
  | 'calmness';

export type SpeechStyle = 'warm' | 'energetic' | 'gentle' | 'serious' | 'playful';

export interface EmotionState {
  emotion: EmotionType;
  intensity: number; // 0–1
  duration_ms: number;
  speech_style: SpeechStyle;
  gesture_metadata: string;
}

// ── Presence Types ───────────────────────────────────────────────────────────

export type TeachingRhythm = 'fast' | 'normal' | 'slow' | 'pause';

export interface PresenceState {
  greeting?: string;
  eye_contact: boolean;
  teaching_rhythm: TeachingRhythm;
  natural_pause_ms: number;
  thinking_pause_ms: number;
  confidence: number;       // 0–1
  warmth: number;           // 0–1
  attention: number;        // 0–1
  curiosity: number;        // 0–1
  encouragement: number;    // 0–1
}

// ── Timing Types ─────────────────────────────────────────────────────────────

export type LessonSpeed = 'slow' | 'normal' | 'fast';
export type TimelineCommand = 'play' | 'pause' | 'resume' | 'skip' | 'replay' | 'seek';

export interface TimingState {
  speed: LessonSpeed;
  current_time_ms: number;
  is_paused: boolean;
  is_playing: boolean;
}

export interface TimedAction {
  action_id: string;
  type: string;
  start_ms: number;
  duration_ms: number;
  completed: boolean;
}

// ── Synchronisation Types ────────────────────────────────────────────────────

export interface SyncState {
  speech_offset_ms: number;
  pointer_offset_ms: number;
  board_offset_ms: number;
  animation_offset_ms: number;
  timeline_offset_ms: number;
  drift_ms: number;
  last_sync_at: number;
}

// ── Interaction Types ────────────────────────────────────────────────────────

export type InteractionType =
  | 'speech'
  | 'touch'
  | 'draw'
  | 'text'
  | 'gesture'
  | 'notebook_move'
  | 'interruption'
  | 'doubt';

export type InteractionPriority = 'low' | 'normal' | 'high' | 'critical';

export interface StudentInteraction {
  id: string;
  type: InteractionType;
  priority: InteractionPriority;
  timestamp: number;
  data: unknown;
  processed: boolean;
}

// ── Prediction Types ─────────────────────────────────────────────────────────

export interface PredictionResult {
  next_action: string;
  confidence: number; // 0–1
  preload_resources: string[];
  estimated_timing_ms: number;
}

// ── Resource Types ───────────────────────────────────────────────────────────

export type ResourceType = 'audio' | 'animation' | 'image' | 'font' | 'diagram' | 'lesson' | 'pointer';

export interface ResourceEntry {
  id: string;
  type: ResourceType;
  uri: string;
  size_bytes: number;
  cached: boolean;
  loaded: boolean;
  last_accessed: number;
}

// ── Latency Types ────────────────────────────────────────────────────────────

export interface LatencyReport {
  ui_ms: number;
  speech_start_ms: number;
  pointer_update_ms: number;
  drawing_ms: number;
  streaming_first_chunk_ms: number;
  timestamp: number;
}

// ── Analytics Types ──────────────────────────────────────────────────────────

export interface AnalyticsEvent {
  event_id: string;
  type: string;
  timestamp: number;
  data: Record<string, unknown>;
  session_id: string;
}

export interface LessonAnalytics {
  student_engagement: number;      // 0–1
  teacher_response_time_ms: number;
  pause_duration_ms: number;
  interruption_count: number;
  lesson_completion: number;        // 0–1
  pointer_accuracy: number;         // 0–1
  streaming_quality: number;        // 0–1
  speech_latency_ms: number;
}

// ── Director Types ───────────────────────────────────────────────────────────

export type LiveLessonPhase =
  | 'greeting'
  | 'observing'
  | 'explaining'
  | 'pointing'
  | 'writing'
  | 'pausing'
  | 'listening'
  | 'evaluating'
  | 'encouraging'
  | 'updating_board'
  | 'continuing'
  | 'idle';

export interface DirectorState {
  phase: LiveLessonPhase;
  is_streaming: boolean;
  is_speaking: boolean;
  is_writing: boolean;
  is_pointing: boolean;
  is_paused: boolean;
  current_action_id: string | null;
  phase_started_at: number;
  student_interaction_queue: number;
}

// ── Event Bus Types ──────────────────────────────────────────────────────────

export type LiveTeacherEventType =
  | 'speech:start'
  | 'speech:end'
  | 'speech:pause'
  | 'stream:chunk'
  | 'stream:complete'
  | 'stream:cancel'
  | 'conversation:turn'
  | 'conversation:state_change'
  | 'emotion:change'
  | 'presence:update'
  | 'timing:state_change'
  | 'sync:drift'
  | 'interaction:received'
  | 'interaction:processed'
  | 'prediction:ready'
  | 'resource:loaded'
  | 'resource:evicted'
  | 'latency:report'
  | 'analytics:event'
  | 'director:phase_change'
  | 'director:error';

export interface LiveTeacherEvent<T = unknown> {
  type: LiveTeacherEventType;
  timestamp: number;
  data: T;
}
