// ──────────────────────────────────────────────────────────────────────────────
// ParticleEngine — lightweight particle system for classroom effects.
//
// Supports: particle bursts (celebration / correct answer), transition fades
// and slides, highlight glow, correction marks, and subtle ambient particles
// that make the classroom feel alive.
// ──────────────────────────────────────────────────────────────────────────────

import type { EffectConfig, EffectType, Point } from '../types';

// ── Configuration ────────────────────────────────────────────────────────────

export interface ParticleConfig {
  maxParticles: number;
  defaultParticleCount: number;
  gravity: number;
  fadeSpeed: number;
}

const DEFAULT_CONFIG: ParticleConfig = {
  maxParticles: 500,
  defaultParticleCount: 30,
  gravity: 0.05,
  fadeSpeed: 0.02,
};

// ── Particle ─────────────────────────────────────────────────────────────────

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  maxLife: number;
  size: number;
  color: string;
  opacity: number;
  shape: 'circle' | 'star' | 'spark';
}

// ── Active effect ────────────────────────────────────────────────────────────

interface ActiveEffect {
  type: EffectType;
  particles: Particle[];
  isComplete: boolean;
  age: number;
  durationMs: number;
  resolve: (() => void) | null;
}

// ── ParticleEngine ───────────────────────────────────────────────────────────

export class ParticleEngine {
  private _config: ParticleConfig;
  private _activeEffects: ActiveEffect[] = [];
  private _particles: Particle[] = [];

  constructor(config: Partial<ParticleConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── Public API ─────────────────────────────────────────────────────────

  /** Spawn an effect and return a promise that resolves when it completes. */
  async playEffect(config: EffectConfig): Promise<void> {
    return new Promise<void>((resolve) => {
      const active: ActiveEffect = {
        type: config.type,
        particles: this._createEffect(config),
        isComplete: false,
        age: 0,
        durationMs: config.duration_ms,
        resolve,
      };
      this._activeEffects.push(active);
      this._particles.push(...active.particles);

      // Limit particle count
      if (this._particles.length > this._config.maxParticles) {
        this._particles.splice(0, this._particles.length - this._config.maxParticles);
      }

      // Auto-complete after duration
      setTimeout(() => {
        active.isComplete = true;
        active.resolve?.();
      }, config.duration_ms);
    });
  }

  /** Update particle positions — call on each animation frame. */
  update(deltaMs: number): void {
    const delta = deltaMs / 16; // Normalize to ~60fps

    for (let i = this._particles.length - 1; i >= 0; i--) {
      const p = this._particles[i];
      p.x += p.vx * delta;
      p.y += p.vy * delta;
      p.vy += this._config.gravity * delta;
      p.life -= this._config.fadeSpeed * delta;
      p.opacity = Math.max(0, p.life / p.maxLife);

      if (p.life <= 0) {
        this._particles.splice(i, 1);
      }
    }

    // Clean up completed effects
    this._activeEffects = this._activeEffects.filter((e) => {
      e.age += deltaMs;
      return !e.isComplete;
    });
  }

  /** Get all active particles for rendering. */
  getParticles(): Particle[] {
    return this._particles;
  }

  /** Get active effects (for rendering overlays). */
  getActiveEffects(): ActiveEffect[] {
    return this._activeEffects.filter((e) => !e.isComplete);
  }

  /** Cancel all effects immediately. */
  cancelAll(): void {
    this._particles = [];
    this._activeEffects.forEach((e) => {
      e.isComplete = true;
      e.resolve?.();
    });
    this._activeEffects = [];
  }

  particleCount(): number {
    return this._particles.length;
  }

  hasActiveEffects(): boolean {
    return this._activeEffects.some((e) => !e.isComplete);
  }

  // ── Effect implementations ─────────────────────────────────────────────

  private _createEffect(config: EffectConfig): Particle[] {
    switch (config.type) {
      case 'particle_burst':
        return this._createBurst(config.position, config.color, config.intensity);
      case 'transition_fade':
        return this._createFadeParticles(config.position, config.color);
      case 'transition_slide':
        return this._createSlideParticles(config.position, config.color);
      case 'highlight_glow':
        return this._createGlowParticles(config.position, config.color);
      case 'correction_mark':
        return this._createCorrectionParticles(config.position);
      case 'celebration':
        return this._createCelebration(config.position, config.intensity);
      default:
        return [];
    }
  }

  private _createBurst(origin: Point, color: string, intensity: number): Particle[] {
    const count = Math.round(this._config.defaultParticleCount * intensity);
    const particles: Particle[] = [];

    for (let i = 0; i < count; i++) {
      const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.5;
      const speed = 2 + Math.random() * 4;
      particles.push({
        x: origin.x,
        y: origin.y,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        life: 1,
        maxLife: 1,
        size: 2 + Math.random() * 4,
        color: this._randomColorVariant(color),
        opacity: 1,
        shape: Math.random() > 0.5 ? 'circle' : 'spark',
      });
    }

    return particles;
  }

  private _createFadeParticles(_origin: Point, _color: string): Particle[] {
    // Fade transitions are handled by the animation engine, not particles
    return [];
  }

  private _createSlideParticles(_origin: Point, _color: string): Particle[] {
    // Slide transitions are handled by the animation engine
    return [];
  }

  private _createGlowParticles(center: Point, color: string): Particle[] {
    const particles: Particle[] = [];
    for (let i = 0; i < 15; i++) {
      const angle = Math.random() * Math.PI * 2;
      const radius = 5 + Math.random() * 20;
      particles.push({
        x: center.x + Math.cos(angle) * radius,
        y: center.y + Math.sin(angle) * radius,
        vx: (Math.random() - 0.5) * 0.5,
        vy: -Math.random() * 0.5,
        life: 1,
        maxLife: 1,
        size: 3 + Math.random() * 5,
        color,
        opacity: 0.6,
        shape: 'circle',
      });
    }
    return particles;
  }

  private _createCorrectionParticles(origin: Point): Particle[] {
    const particles: Particle[] = [];
    const colors = ['#ff4444', '#ff6600', '#ffaa00'];
    for (let i = 0; i < 10; i++) {
      const angle = (Math.PI * 2 * i) / 10;
      particles.push({
        x: origin.x,
        y: origin.y,
        vx: Math.cos(angle) * 1.5,
        vy: Math.sin(angle) * 1.5,
        life: 1,
        maxLife: 1,
        size: 2,
        color: colors[i % colors.length],
        opacity: 1,
        shape: 'spark',
      });
    }
    return particles;
  }

  private _createCelebration(origin: Point, intensity: number): Particle[] {
    const count = Math.round(20 * intensity);
    const particles: Particle[] = [];
    const colors = ['#ffd700', '#ff6b6b', '#48dbfb', '#ff9ff3', '#54a0ff', '#5f27cd'];

    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 3 + Math.random() * 5;
      particles.push({
        x: origin.x + (Math.random() - 0.5) * 40,
        y: origin.y + (Math.random() - 0.5) * 40,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 3,
        life: 1,
        maxLife: 1,
        size: 3 + Math.random() * 5,
        color: colors[Math.floor(Math.random() * colors.length)],
        opacity: 1,
        shape: Math.random() > 0.3 ? 'star' : 'circle',
      });
    }
    return particles;
  }

  // ── Helpers ────────────────────────────────────────────────────────────

  private _randomColorVariant(baseColor: string): string {
    // Simple RGB variant for burst effects
    const r = parseInt(baseColor.slice(1, 3), 16) || 200;
    const g = parseInt(baseColor.slice(3, 5), 16) || 100;
    const b = parseInt(baseColor.slice(5, 7), 16) || 50;
    const variance = 40;
    const clamp = (v: number): number => Math.max(0, Math.min(255, v + (Math.random() - 0.5) * variance));
    return `rgb(${clamp(r)},${clamp(g)},${clamp(b)})`;
  }
}
