// ──────────────────────────────────────────────────────────────────────────────
// Mentis Live Teacher System — barrel export
// ──────────────────────────────────────────────────────────────────────────────

export { LiveTeacherDirector } from './director/LiveTeacherDirector';
export type { LiveTeacherDirectorConfig, DirectorSubsystems } from './director/LiveTeacherDirector';

export { StreamingManager } from './streaming/StreamingManager';
export type { StreamingManagerConfig } from './streaming/StreamingManager';

export { SpeechManager } from './speech/SpeechManager';
export type { SpeechManagerConfig } from './speech/SpeechManager';

export { ConversationEngine } from './conversation/ConversationEngine';
export type { ConversationEngineConfig } from './conversation/ConversationEngine';

export { PresenceEngine } from './presence/PresenceEngine';
export type { PresenceEngineConfig } from './presence/PresenceEngine';

export { TimingEngine } from './timing/TimingEngine';
export type { TimingEngineConfig, TimingClockListener, TimingActionListener } from './timing/TimingEngine';

export { SyncEngine } from './synchronization/SyncEngine';
export type { SyncEngineConfig } from './synchronization/SyncEngine';

export { EmotionEngine } from './emotion/EmotionEngine';
export type { EmotionEngineConfig } from './emotion/EmotionEngine';

export { LiveInteractionEngine } from './interaction/LiveInteractionEngine';
export type { LiveInteractionEngineConfig } from './interaction/LiveInteractionEngine';

export { PredictionEngine } from './prediction/PredictionEngine';
export type { PredictionEngineConfig } from './prediction/PredictionEngine';

export { ResourceManager } from './resource_manager/ResourceManager';
export type { ResourceManagerConfig } from './resource_manager/ResourceManager';

export { LatencyEngine } from './latency/LatencyEngine';
export type { LatencyEngineConfig } from './latency/LatencyEngine';

export { AnalyticsEngine } from './analytics/AnalyticsEngine';
export type { AnalyticsEngineConfig } from './analytics/AnalyticsEngine';

// Re-export all types
export type * from './types';
