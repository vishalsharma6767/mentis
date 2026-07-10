// ──────────────────────────────────────────────────────────────────────────────
// AnimationEngine — timeline-based animation system for the classroom.
//
// Every board action, pointer movement, and visual effect is animated.
// Animations can be sequenced, grouped, and synchronised with speech.
//
// Supports: fade_in, fade_out, draw, grow, slide, pulse, highlight,
//           pointer_move, circle_expand, arrow_draw, text_write, formula_build
// ──────────────────────────────────────────────────────────────────────────────

import type { AnimationType, Point } from '../types';
import type { SharedValue } from 'react-native-reanimated';
import {
  useSharedValue,
  withTiming,
  withSpring,
  withSequence,
  withDelay,
  Easing,
  cancelAnimation,
} from 'react-native-reanimated';

// ── Configuration ────────────────────────────────────────────────────────────

export interface AnimationConfig {
  defaultDurationMs: number;
  springStiffness: number;
  springDamping: number;
  maxConcurrentAnimations: number;
}

const DEFAULT_CONFIG: AnimationConfig = {
  defaultDurationMs: 400,
  springStiffness: 150,
  springDamping: 15,
  maxConcurrentAnimations: 20,
};

// ── Animation state ──────────────────────────────────────────────────────────

interface AnimationInstance {
  id: string;
  type: AnimationType;
  targetId: string;
  progress: SharedValue<number>;
  opacity: SharedValue<number>;
  scale: SharedValue<number>;
  position: SharedValue<Point>;
  isPlaying: SharedValue<boolean>;
  resolve: (() => void) | null;
}

// ── AnimationEngine ──────────────────────────────────────────────────────────

export class AnimationEngine {
  private _config: AnimationConfig;
  private _activeAnimations: Map<string, AnimationInstance> = new Map();
  private _nextAnimationId = 1;
  private _isSpeechSynchronized = false;

  constructor(config: Partial<AnimationConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── Public API ──────────────────────────────────────────────────────────

  async play(
    type: AnimationType,
    targetId: string,
    properties: Record<string, unknown> = {},
  ): Promise<void> {
    if (type === 'none') return;

    // Cancel any existing animation on this target
    this.cancel(targetId);

    if (this._activeAnimations.size >= this._config.maxConcurrentAnimations) {
      this._cleanupOldest();
    }

    const id = `anim_${this._nextAnimationId++}_${targetId}`;
    const progress = useSharedValue(0);
    const opacity = useSharedValue(1);
    const scale = useSharedValue(1);
    const position = useSharedValue<Point>({
      x: (properties.startX as number) ?? 0,
      y: (properties.startY as number) ?? 0,
    });

    const instance: AnimationInstance = {
      id,
      type,
      targetId,
      progress,
      opacity,
      scale,
      position,
      isPlaying: useSharedValue(true),
      resolve: null,
    };

    this._activeAnimations.set(targetId, instance);

    return new Promise<void>((resolve) => {
      instance.resolve = resolve;
      this._executeAnimation(instance, properties);
    });
  }

  async playSequence(
    animations: Array<{
      type: AnimationType;
      targetId: string;
      properties?: Record<string, unknown>;
    }>,
  ): Promise<void> {
    for (const anim of animations) {
      await this.play(anim.type, anim.targetId, anim.properties);
    }
  }

  cancel(targetId: string): void {
    const instance = this._activeAnimations.get(targetId);
    if (!instance) return;

    cancelAnimation(instance.progress);
    cancelAnimation(instance.opacity);
    cancelAnimation(instance.scale);
    cancelAnimation(instance.position);
    instance.isPlaying.value = false;
    instance.resolve?.();
    this._activeAnimations.delete(targetId);
  }

  cancelAll(): void {
    Array.from(this._activeAnimations.keys()).forEach((targetId) => {
      this.cancel(targetId);
    });
  }

  getProgress(targetId: string): SharedValue<number> | null {
    return this._activeAnimations.get(targetId)?.progress ?? null;
  }

  getOpacity(targetId: string): SharedValue<number> | null {
    return this._activeAnimations.get(targetId)?.opacity ?? null;
  }

  getScale(targetId: string): SharedValue<number> | null {
    return this._activeAnimations.get(targetId)?.scale ?? null;
  }

  getPosition(targetId: string): SharedValue<Point> | null {
    return this._activeAnimations.get(targetId)?.position ?? null;
  }

  isAnimating(targetId: string): boolean {
    return this._activeAnimations.has(targetId);
  }

  activeCount(): number {
    return this._activeAnimations.size;
  }

  // ── Speech sync ─────────────────────────────────────────────────────────

  setSpeechSynchronized(enabled: boolean): void {
    this._isSpeechSynchronized = enabled;
  }

  async playWithSpeech(
    type: AnimationType,
    targetId: string,
    speechDurationMs: number,
    properties: Record<string, unknown> = {},
  ): Promise<void> {
    // Stretch animation timing to match speech duration
    if (speechDurationMs > 0) {
      properties = { ...properties, duration_ms: speechDurationMs };
    }
    return this.play(type, targetId, properties);
  }

  // ── Animation execution ─────────────────────────────────────────────────

  private async _executeAnimation(
    instance: AnimationInstance,
    properties: Record<string, unknown>,
  ): Promise<void> {
    const duration = (properties.duration_ms as number) ?? this._config.defaultDurationMs;
    const delay = (properties.delay_ms as number) ?? 0;
    const easing = this._resolveEasing(properties.easing as string);

    switch (instance.type) {
      case 'fade_in':
        instance.opacity.value = 0;
        if (delay > 0) {
          instance.opacity.value = withDelay(
            delay,
            withTiming(1, { duration, easing }),
          );
        } else {
          instance.opacity.value = withTiming(1, { duration, easing });
        }
        instance.progress.value = withTiming(1, { duration: duration + delay });
        break;

      case 'fade_out':
        if (delay > 0) {
          instance.opacity.value = withDelay(
            delay,
            withTiming(0, { duration, easing }),
          );
        } else {
          instance.opacity.value = withTiming(0, { duration, easing });
        }
        instance.progress.value = withTiming(1, { duration: duration + delay });
        break;

      case 'draw':
        // Progress drives stroke length (0→1 draws the line)
        instance.progress.value = withTiming(1, { duration, easing });
        break;

      case 'grow':
        instance.scale.value = 0;
        if (delay > 0) {
          instance.scale.value = withDelay(
            delay,
            withSpring(1, {
              stiffness: this._config.springStiffness * 0.5,
              damping: this._config.springDamping,
            }),
          );
        } else {
          instance.scale.value = withSpring(1, {
            stiffness: this._config.springStiffness * 0.5,
            damping: this._config.springDamping,
          });
        }
        instance.progress.value = withTiming(1, { duration: duration + delay });
        break;

      case 'slide': {
        const startX = (properties.startX as number) ?? 0;
        const startY = (properties.startY as number) ?? 0;
        const endX = (properties.endX as number) ?? startX;
        const endY = (properties.endY as number) ?? startY;
        instance.position.value = { x: startX, y: startY };

        const animatePosition = (): void => {
          'worklet';
          instance.position.value = withTiming(
            { x: endX, y: endY },
            { duration, easing },
          );
        };
        if (delay > 0) {
          setTimeout(animatePosition, delay);
        } else {
          animatePosition();
        }
        instance.progress.value = withTiming(1, { duration: duration + delay });
        break;
      }

      case 'pulse':
        instance.scale.value = withSequence(
          withTiming(1.15, { duration: duration / 2 }),
          withTiming(1, { duration: duration / 2 }),
        );
        instance.progress.value = withTiming(1, { duration });
        break;

      case 'highlight':
        instance.opacity.value = 0.3;
        instance.progress.value = withTiming(1, { duration });
        if (delay > 0) {
          instance.opacity.value = withDelay(
            delay,
            withTiming(0.6, { duration: duration / 2 }),
          );
        } else {
          instance.opacity.value = withTiming(0.6, { duration: duration / 2 });
        }
        break;

      case 'pointer_move':
        instance.progress.value = withTiming(1, { duration, easing });
        break;

      case 'circle_expand':
        instance.scale.value = 0;
        instance.opacity.value = 1;
        instance.scale.value = withSequence(
          withTiming(1.5, { duration }),
          withTiming(1, { duration: duration / 2 }),
        );
        instance.opacity.value = withDelay(
          duration + duration / 2,
          withTiming(0, { duration: 200 }),
        );
        instance.progress.value = withTiming(1, { duration: duration + 200 });
        break;

      case 'arrow_draw':
        instance.progress.value = withTiming(1, { duration, easing });
        break;

      case 'text_write':
        instance.progress.value = withTiming(1, { duration, easing });
        break;

      case 'formula_build':
        instance.progress.value = withTiming(1, { duration, easing });
        break;
    }

    // Auto-cleanup after animation completes
    const totalDuration = duration + delay + 100;
    setTimeout(() => {
      instance.isPlaying.value = false;
      instance.resolve?.();
      this._activeAnimations.delete(instance.targetId);
    }, totalDuration);
  }

  // ── Helpers ─────────────────────────────────────────────────────────────

  private _resolveEasing(easingName?: string): any {
    switch (easingName) {
      case 'ease_in':
        return Easing.bezier(0.42, 0.0, 1.0, 1.0);
      case 'ease_out':
        return Easing.bezier(0.0, 0.0, 0.58, 1.0);
      case 'ease_in_out':
        return Easing.bezier(0.42, 0.0, 0.58, 1.0);
      default:
        return Easing.bezier(0.25, 0.1, 0.25, 1.0);
    }
  }

  private _cleanupOldest(): void {
    const entries = Array.from(this._activeAnimations.entries());
    if (entries.length === 0) return;
    const [targetId] = entries[0];
    this.cancel(targetId);
  }
}
