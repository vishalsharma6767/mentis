/* eslint-disable @typescript-eslint/no-explicit-any */

// ──────────────────────────────────────────────────────────────────────────────
// Mentis Interactive Classroom Engine — Shared Types
// ──────────────────────────────────────────────────────────────────────────────
// Every module imports from this single file.  No circular deps.  No duplication.

import type { SharedValue } from 'react-native-reanimated';

// ══════════════════════════════════════════════════════════════════════════════
// Geometry
// ══════════════════════════════════════════════════════════════════════════════

export interface Point {
  x: number;
  y: number;
}

export interface Size {
  width: number;
  height: number;
}

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Matrix4x4 {
  m00: number; m01: number; m02: number; m03: number;
  m10: number; m11: number; m12: number; m13: number;
  m20: number; m21: number; m22: number; m23: number;
  m30: number; m31: number; m32: number; m33: number;
}

export interface HomographyMatrix {
  a: number; b: number; c: number;
  d: number; e: number; f: number;
  g: number; h: number;
}

/** Transforms a point via homography. */
export function applyHomography(p: Point, H: HomographyMatrix): Point {
  const w = H.g * p.x + H.h * p.y + 1;
  return {
    x: (H.a * p.x + H.b * p.y + H.c) / w,
    y: (H.d * p.x + H.e * p.y + H.f) / w,
  };
}

export interface NotebookCorners {
  topLeft: Point;
  topRight: Point;
  bottomLeft: Point;
  bottomRight: Point;
}

// ══════════════════════════════════════════════════════════════════════════════
// Scene Graph (from backend Phase 3.5)
// ══════════════════════════════════════════════════════════════════════════════

export type NodeType =
  | 'question' | 'sub_question' | 'formula' | 'diagram' | 'graph'
  | 'geometry' | 'table' | 'equation' | 'variable' | 'constant'
  | 'student_answer' | 'teacher_hint' | 'mistake' | 'concept'
  | 'prerequisite' | 'learning_objective' | 'step' | 'known_value'
  | 'unknown_value' | 'rule' | 'theorem' | 'solution_path'
  | 'student_step' | 'teacher_note' | 'example' | 'analogy';

export type EdgeType =
  | 'contains' | 'depends_on' | 'explains' | 'references'
  | 'derived_from' | 'solves' | 'incorrect_step' | 'next_step'
  | 'requires_revision' | 'belongs_to_topic' | 'related_to_concept'
  | 'leads_to' | 'corrects' | 'precedes' | 'follows'
  | 'has_mistake' | 'has_answer' | 'has_diagram' | 'has_formula'
  | 'uses_concept' | 'builds_on' | 'substitutes' | 'equivalent_to'
  | 'has_property' | 'measures' | 'teacher_hint' | 'teacher_note';

export interface SceneNodeDTO {
  id: string;
  type: NodeType;
  label: string;
  content: string;
  confidence: number;
  data: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface SceneEdgeDTO {
  source_id: string;
  target_id: string;
  type: EdgeType;
  label: string;
  confidence: number;
}

export interface SceneGraphDTO {
  nodes: SceneNodeDTO[];
  edges: SceneEdgeDTO[];
  root_node_ids: string[];
  metadata: {
    source_scene_id: string;
    vision_confidence: number;
    node_count: number;
    edge_count: number;
    builder_version: string;
    created_at: string;
    processing_time_ms: number;
    models_used: string[];
  };
}

// ══════════════════════════════════════════════════════════════════════════════
// Teaching Decision (from backend reasoner)
// ══════════════════════════════════════════════════════════════════════════════

export interface TeacherFocusDTO {
  current_focus: string;
  misconception: string;
  learning_objective: string;
  visual_focus: string;
  revision_priority: string[];
  concept_to_teach: string;
  confidence: number;
}

export interface TeachingPriorityDTO {
  immediate: string[];
  next: string[];
  deferred: string[];
  revision: string[];
  ignore: string[];
}

export interface BoardFocusDTO {
  primary_formula: string;
  diagram_focus: string;
  step_highlight: string;
  labels_to_write: string[];
  color_hints: string[];
}

export interface StepAnalysisDTO {
  step_number: number;
  description: string;
  is_correct: boolean;
  confidence: number;
  teacher_guidance: string;
  hint: string;
  board_action: string;
  ar_visualization: string;
}

export interface TeachingDecisionDTO {
  focus: TeacherFocusDTO;
  priority: TeachingPriorityDTO;
  steps: StepAnalysisDTO[];
  board: BoardFocusDTO;
  hints: string[];
  confidence: number;
  processing_time_ms: number;
}

// ══════════════════════════════════════════════════════════════════════════════
// Teacher Agent Output (from backend Phase 2)
// ══════════════════════════════════════════════════════════════════════════════

export interface TeacherOutputDTO {
  speech_text: string;
  speech_language: 'hinglish' | 'hindi' | 'english';
  board_action: BoardActionDTO;
  pointer_action: PointerActionDTO;
  gesture: GestureType;
  animation: TimelineActionDTO | null;
  wait_for_student: boolean;
  metadata: Record<string, unknown>;
}

export interface BoardActionDTO {
  action: 'write' | 'draw' | 'erase' | 'highlight' | 'clear' | 'formula' | 'diagram';
  content: string;
  layer: number;
  position: Point;
  color: string;
  stroke_width: number;
  metadata?: Record<string, unknown>;
}

export interface PointerActionDTO {
  action: 'move' | 'tap' | 'circle' | 'arrow' | 'underline' | 'highlight' | 'idle';
  position: Point;
  target_id?: string;
  duration_ms?: number;
  color?: string;
}

// ══════════════════════════════════════════════════════════════════════════════
// Notebook Tracking
// ══════════════════════════════════════════════════════════════════════════════

export type TrackingQuality = 'high' | 'medium' | 'low' | 'lost';

export interface NotebookFrame {
  corners: NotebookCorners;
  homography: HomographyMatrix;
  quality: TrackingQuality;
  timestamp: number;
  image_size: Size;
  confidence: number;
}

export interface Anchor {
  id: string;
  position: Point;
  confidence: number;
  last_seen: number;
}

// ══════════════════════════════════════════════════════════════════════════════
// Board / Whiteboard
// ══════════════════════════════════════════════════════════════════════════════

export type BoardElementType =
  | 'stroke'
  | 'text'
  | 'formula'
  | 'diagram'
  | 'geometry'
  | 'arrow'
  | 'highlight'
  | 'image'
  | 'eraser';

export interface BoardElement {
  id: string;
  type: BoardElementType;
  layer: number;
  timestamp: number;
  is_animated: boolean;
  metadata: Record<string, unknown>;
}

export interface StrokeElement extends BoardElement {
  type: 'stroke';
  points: Point[];
  color: string;
  stroke_width: number;
  opacity: number;
  pressure_points: number[];
  is_complete: boolean;
}

export interface TextElement extends BoardElement {
  type: 'text';
  text: string;
  position: Point;
  font_size: number;
  color: string;
  font_family: string;
}

export interface FormulaElement extends BoardElement {
  type: 'formula';
  latex: string;
  position: Point;
  scale: number;
  elements: FormulaSubElement[];
}

export interface FormulaSubElement {
  id: string;
  latex: string;
  position: Point;
  animation_delay_ms: number;
}

export interface DiagramElement extends BoardElement {
  type: 'diagram';
  shape: 'triangle' | 'circle' | 'rectangle' | 'line' | 'arrow' | 'arc' | 'freeform';
  points: Point[];
  color: string;
  fill_color: string;
  stroke_width: number;
}

export interface HighlightElement extends BoardElement {
  type: 'highlight';
  region: Rect;
  color: string;
  opacity: number;
  animation: 'fade' | 'pulse' | 'draw';
}

// ══════════════════════════════════════════════════════════════════════════════
// Pen / Handwriting
// ══════════════════════════════════════════════════════════════════════════════

export interface PenState {
  position: SharedValue<Point>;
  pressure: SharedValue<number>;
  is_active: SharedValue<boolean>;
  color: SharedValue<string>;
  stroke_width: SharedValue<number>;
}

export interface InkPoint {
  x: number;
  y: number;
  pressure: number;
  timestamp: number;
}

export interface InkStroke {
  id: string;
  points: InkPoint[];
  color: string;
  stroke_width: number;
  opacity: number;
  is_replay: boolean;
  replay_speed: number;
}

// ══════════════════════════════════════════════════════════════════════════════
// Pointer
// ══════════════════════════════════════════════════════════════════════════════

export type PointerMode = 'laser' | 'finger' | 'pen' | 'arrow' | 'circle' | 'highlight';

export interface PointerState {
  mode: SharedValue<PointerMode>;
  position: SharedValue<Point>;
  is_visible: SharedValue<boolean>;
  color: SharedValue<string>;
  size: SharedValue<number>;
}

export interface PointerPath {
  points: Point[];
  timestamps: number[];
  mode: PointerMode;
}

// ══════════════════════════════════════════════════════════════════════════════
// Animation / Timeline
// ══════════════════════════════════════════════════════════════════════════════

export type AnimationType =
  | 'fade_in' | 'fade_out' | 'draw' | 'grow' | 'slide'
  | 'pulse' | 'highlight' | 'pointer_move' | 'circle_expand'
  | 'arrow_draw' | 'text_write' | 'formula_build' | 'none';

export type TimelineEventType =
  | 'teacher_speech'
  | 'board_action'
  | 'pointer_action'
  | 'gesture'
  | 'animation'
  | 'wait'
  | 'student_interaction'
  | 'correction'
  | 'next_step'
  | 'lesson_end';

export interface TimelineActionDTO {
  type: AnimationType;
  duration_ms: number;
  delay_ms: number;
  easing: 'linear' | 'ease_in' | 'ease_out' | 'ease_in_out' | 'spring';
  target_id?: string;
  properties: Record<string, unknown>;
}

export interface TimelineEvent {
  id: string;
  type: TimelineEventType;
  timestamp: number;
  duration_ms: number;
  data: Record<string, unknown>;
  animation: TimelineActionDTO | null;
  speech_text?: string;
  board_action?: BoardActionDTO;
  pointer_action?: PointerActionDTO;
}

export type TimelineState = 'idle' | 'playing' | 'paused' | 'seeking' | 'finished';

export interface LessonTimelineState {
  events: TimelineEvent[];
  current_index: number;
  current_time_ms: number;
  state: TimelineState;
  total_duration_ms: number;
  progress: number;
}

// ══════════════════════════════════════════════════════════════════════════════
// Gestures
// ══════════════════════════════════════════════════════════════════════════════

export type GestureType =
  | 'point' | 'wave' | 'tap' | 'circle' | 'underline'
  | 'focus' | 'highlight_region' | 'count' | 'none';

export interface GestureAction {
  type: GestureType;
  position: Point;
  target_id?: string;
  duration_ms: number;
  intensity: number;
  metadata: Record<string, unknown>;
}

// ══════════════════════════════════════════════════════════════════════════════
// Streaming (WebSocket)
// ══════════════════════════════════════════════════════════════════════════════

export type StreamMessageType =
  | 'scene_graph'
  | 'teaching_decision'
  | 'teacher_output'
  | 'board_update'
  | 'pointer_update'
  | 'speech_chunk'
  | 'animation_trigger'
  | 'gesture_trigger'
  | 'timeline_sync'
  | 'heartbeat';

export interface StreamMessage {
  type: StreamMessageType;
  timestamp: number;
  sequence: number;
  data: Record<string, unknown>;
  ack_required: boolean;
}

export interface StreamState {
  connected: boolean;
  latency_ms: number;
  last_heartbeat: number;
  queued_messages: number;
}

// ══════════════════════════════════════════════════════════════════════════════
// Teacher State
// ══════════════════════════════════════════════════════════════════════════════

export type TeacherActivity =
  | 'speaking'
  | 'writing'
  | 'drawing'
  | 'pointing'
  | 'gesturing'
  | 'waiting'
  | 'checking'
  | 'correcting'
  | 'idle';

export interface TeacherState {
  activity: TeacherActivity;
  current_focus: string;
  current_step: number;
  speech_text: string;
  is_animated: boolean;
  confidence: number;
  is_waiting_for_student: boolean;
  board_content_hash: string;
  pointer_position: Point;
}

// ══════════════════════════════════════════════════════════════════════════════
// Student Interaction
// ══════════════════════════════════════════════════════════════════════════════

export type StudentInputType = 'speech' | 'touch' | 'draw' | 'text';

export interface StudentInteraction {
  type: StudentInputType;
  timestamp: number;
  data: Record<string, unknown>;
  confidence: number;
}

export interface StudentState {
  is_interrupting: boolean;
  current_input: StudentInteraction | null;
  last_doubt: string | null;
  attention_score: number;
}

// ══════════════════════════════════════════════════════════════════════════════
// Render Layers
// ══════════════════════════════════════════════════════════════════════════════

export type LayerName =
  | 'background'
  | 'notebook'
  | 'teacher_ink'
  | 'highlights'
  | 'pointer'
  | 'animations'
  | 'widgets'
  | 'speech_captions'
  | 'debug';

export interface RenderLayer {
  name: LayerName;
  z_index: number;
  is_visible: boolean;
  needs_redraw: SharedValue<boolean>;
  opacity: SharedValue<number>;
}

// ══════════════════════════════════════════════════════════════════════════════
// Effects
// ══════════════════════════════════════════════════════════════════════════════

export type EffectType =
  | 'particle_burst'
  | 'transition_fade'
  | 'transition_slide'
  | 'highlight_glow'
  | 'correction_mark'
  | 'celebration';

export interface EffectConfig {
  type: EffectType;
  position: Point;
  duration_ms: number;
  intensity: number;
  color: string;
}

// ══════════════════════════════════════════════════════════════════════════════
// Performance metrics
// ══════════════════════════════════════════════════════════════════════════════

export interface PerformanceMetrics {
  fps: number;
  frame_time_ms: number;
  render_latency_ms: number;
  tracking_latency_ms: number;
  streaming_latency_ms: number;
  memory_mb: number;
  layer_count: number;
}

// ══════════════════════════════════════════════════════════════════════════════
// Engine-wide event bus types
// ══════════════════════════════════════════════════════════════════════════════

export type ClassroomEventType =
  | 'scene_graph_received'
  | 'teaching_decision_received'
  | 'teacher_output_received'
  | 'notebook_tracking_updated'
  | 'board_element_added'
  | 'stroke_started'
  | 'stroke_completed'
  | 'pointer_moved'
  | 'animation_triggered'
  | 'gesture_triggered'
  | 'timeline_event'
  | 'student_interaction'
  | 'stream_connected'
  | 'stream_disconnected'
  | 'error'
  | 'state_changed';

export interface ClassroomEvent {
  type: ClassroomEventType;
  timestamp: number;
  source: string;
  data: Record<string, unknown>;
}

export type EventListener = (event: ClassroomEvent) => void;

// ══════════════════════════════════════════════════════════════════════════════
// Metadata for debug overlay
// ══════════════════════════════════════════════════════════════════════════════

export interface DebugInfo {
  tracking: {
    quality: TrackingQuality;
    confidence: number;
    corner_count: number;
    homography_valid: boolean;
  };
  scene_graph: {
    node_count: number;
    edge_count: number;
    last_update: number;
  };
  board: {
    element_count: number;
    layer_count: number;
    current_stroke_count: number;
  };
  timeline: {
    state: TimelineState;
    current_index: number;
    progress: number;
    event_count: number;
  };
  pointer: {
    mode: PointerMode;
    position: Point;
    is_visible: boolean;
  };
  streaming: {
    connected: boolean;
    latency_ms: number;
    messages_sent: number;
    messages_received: number;
  };
  performance: PerformanceMetrics;
}
