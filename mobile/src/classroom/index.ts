// ──────────────────────────────────────────────────────────────────────────────
// Mentis Interactive Classroom Engine — barrel export
// ──────────────────────────────────────────────────────────────────────────────

export { ClassroomEngine, useClassroomEngine, getClassroomEngine } from './engine/ClassroomEngine';
export type {
  ClassroomEngineConfig,
  NotebookTrackerInterface,
  WhiteboardEngineInterface,
  PenEngineInterface,
  PointerEngineInterface,
  AnimationEngineInterface,
  GestureEngineInterface,
  StreamingEngineInterface,
  LessonTimelineInterface,
  SceneGraphManagerInterface,
  TeacherStateManagerInterface,
  InteractionEngineInterface,
  LayeredRendererInterface,
} from './engine/ClassroomEngine';

export { NotebookTracker } from './camera/NotebookTracker';
export type { NotebookTrackerConfig, CornerDetectionResult, FeatureMatchResult } from './camera/NotebookTracker';

export { WhiteboardEngine } from './board/WhiteboardEngine';

export { PenEngine } from './pen/PenEngine';
export type { PenEngineConfig } from './pen/PenEngine';

export { PointerEngine } from './pointer/PointerEngine';
export type { PointerEngineConfig } from './pointer/PointerEngine';

export { AnimationEngine } from './animation/AnimationEngine';
export type { AnimationConfig } from './animation/AnimationEngine';

export { GestureEngine } from './gesture/GestureEngine';
export type { GestureConfig } from './gesture/GestureEngine';

export { StreamingEngine } from './streaming/StreamingEngine';
export type { StreamingConfig } from './streaming/StreamingEngine';

export { LessonTimeline } from './timeline/LessonTimeline';
export type { TimelineConfig } from './timeline/LessonTimeline';

export { SceneGraphManager } from './scene/SceneGraphManager';

export { TeacherStateManager } from './teacher/TeacherStateManager';

export { InteractionEngine } from './interaction/InteractionEngine';
export type { InteractionConfig } from './interaction/InteractionEngine';

export { LayeredRenderer } from './renderer/LayeredRenderer';

export { ParticleEngine } from './effects/ParticleEngine';
export type { ParticleConfig } from './effects/ParticleEngine';

export { DebugOverlay } from './debug/DebugOverlay';
export type { DebugOverlayConfig } from './debug/DebugOverlay';

// Re-export all types
export type * from './types';
