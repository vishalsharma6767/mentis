// ──────────────────────────────────────────────────────────────────────────────
// DebugOverlay — development-mode overlay for the Classroom Engine.
//
// Visualizes:
//   - Tracking: notebook corners, homography validity, confidence
//   - Scene Graph: node count, edge count, root questions, mistakes
//   - Board: element count, stroke count, content hash
//   - Timeline: state, progress, current event index
//   - Pointer: mode, position, visibility
//   - Streaming: connection status, latency, message counts
//   - Performance: FPS, frame time, memory
//
// The overlay is rendered on the "debug" layer and is only visible in
// development builds.
// ──────────────────────────────────────────────────────────────────────────────

import type { DebugInfo } from '../types';

// ── Configuration ────────────────────────────────────────────────────────────

export interface DebugOverlayConfig {
  /** Whether the overlay is visible by default */
  visible: boolean;
  /** Opacity of the overlay background */
  backgroundOpacity: number;
  /** Font size for debug text */
  fontSize: number;
  /** Update interval for reading debug info (ms) */
  updateIntervalMs: number;
}

const DEFAULT_CONFIG: DebugOverlayConfig = {
  visible: __DEV__,
  backgroundOpacity: 0.75,
  fontSize: 10,
  updateIntervalMs: 250,
};

// ── DebugOverlay ─────────────────────────────────────────────────────────────

export class DebugOverlay {
  private _config: DebugOverlayConfig;
  private _isVisible: boolean;
  private _debugInfo: DebugInfo | null = null;
  private _sections: Array<{ title: string; lines: Array<{ label: string; value: string; color?: string }> }> = [];
  private _lastUpdateTime = 0;
  private _updateCallbacks: Array<(sections: DebugOverlay['_sections']) => void> = [];

  constructor(config: Partial<DebugOverlayConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
    this._isVisible = this._config.visible;
  }

  // ── Visibility ─────────────────────────────────────────────────────────

  show(): void {
    this._isVisible = true;
  }

  hide(): void {
    this._isVisible = false;
  }

  toggle(): void {
    this._isVisible = !this._isVisible;
  }

  isVisible(): boolean {
    return this._isVisible;
  }

  // ── Update ─────────────────────────────────────────────────────────────

  update(debugInfo: DebugInfo, force = false): void {
    const now = Date.now();
    if (!force && now - this._lastUpdateTime < this._config.updateIntervalMs) {
      return;
    }

    this._lastUpdateTime = now;
    this._debugInfo = debugInfo;
    this._buildSections();
    this._notify();
  }

  getDebugInfo(): DebugInfo | null {
    return this._debugInfo;
  }

  getSections(): DebugOverlay['_sections'] {
    return this._sections;
  }

  // ── Subscriptions ──────────────────────────────────────────────────────

  onUpdate(cb: (sections: DebugOverlay['_sections']) => void): () => void {
    this._updateCallbacks.push(cb);
    // Immediately push current state
    if (this._sections.length > 0) {
      cb(this._sections);
    }
    return () => {
      this._updateCallbacks = this._updateCallbacks.filter((f) => f !== cb);
    };
  }

  // ── Section building ───────────────────────────────────────────────────

  private _buildSections(): void {
    if (!this._debugInfo) return;

    this._sections = [
      this._buildTrackingSection(),
      this._buildSceneGraphSection(),
      this._buildBoardSection(),
      this._buildTimelineSection(),
      this._buildPointerSection(),
      this._buildStreamingSection(),
      this._buildPerformanceSection(),
    ];
  }

  private _buildTrackingSection(): DebugOverlay['_sections'][0] {
    const t = this._debugInfo!.tracking;
    const qualityColor =
      t.quality === 'high' ? '#22cc66' :
      t.quality === 'medium' ? '#ffaa00' :
      t.quality === 'low' ? '#ff6600' : '#ff4444';

    return {
      title: '📷 Notebook Tracking',
      lines: [
        { label: 'Quality', value: t.quality, color: qualityColor },
        { label: 'Confidence', value: `${(t.confidence * 100).toFixed(0)}%` },
        { label: 'Corners', value: `${t.corner_count}` },
        { label: 'Homography', value: t.homography_valid ? '✅ Valid' : '❌ Invalid' },
      ],
    };
  }

  private _buildSceneGraphSection(): DebugOverlay['_sections'][0] {
    const sg = this._debugInfo!.scene_graph;
    const age = sg.last_update > 0
      ? `${((Date.now() - sg.last_update) / 1000).toFixed(1)}s ago`
      : 'never';

    return {
      title: '🧠 Scene Graph',
      lines: [
        { label: 'Nodes', value: `${sg.node_count}` },
        { label: 'Edges', value: `${sg.edge_count}` },
        { label: 'Last Update', value: age },
      ],
    };
  }

  private _buildBoardSection(): DebugOverlay['_sections'][0] {
    const b = this._debugInfo!.board;
    return {
      title: '📋 Board',
      lines: [
        { label: 'Elements', value: `${b.element_count}` },
        { label: 'Layers', value: `${b.layer_count}` },
        { label: 'Active Strokes', value: `${b.current_stroke_count}` },
      ],
    };
  }

  private _buildTimelineSection(): DebugOverlay['_sections'][0] {
    const t = this._debugInfo!.timeline;
    const stateColor =
      t.state === 'playing' ? '#22cc66' :
      t.state === 'paused' ? '#ffaa00' :
      t.state === 'finished' ? '#4488ff' : '#888888';

    return {
      title: '⏱️ Timeline',
      lines: [
        { label: 'State', value: t.state, color: stateColor },
        { label: 'Event', value: `${t.current_index + 1} / ${t.event_count}` },
        { label: 'Progress', value: `${(t.progress * 100).toFixed(0)}%` },
      ],
    };
  }

  private _buildPointerSection(): DebugOverlay['_sections'][0] {
    const p = this._debugInfo!.pointer;
    return {
      title: '🖱️ Pointer',
      lines: [
        { label: 'Mode', value: p.mode },
        { label: 'Position', value: `(${p.position.x.toFixed(3)}, ${p.position.y.toFixed(3)})` },
        { label: 'Visible', value: p.is_visible ? '✅ Yes' : '❌ No' },
      ],
    };
  }

  private _buildStreamingSection(): DebugOverlay['_sections'][0] {
    const s = this._debugInfo!.streaming;
    const connColor = s.connected ? '#22cc66' : '#ff4444';
    return {
      title: '🌐 Streaming',
      lines: [
        { label: 'Connected', value: s.connected ? '✅ Yes' : '❌ No', color: connColor },
        { label: 'Latency', value: `${s.latency_ms}ms` },
        { label: 'Sent / Recv', value: `${s.messages_sent} / ${s.messages_received}` },
      ],
    };
  }

  private _buildPerformanceSection(): DebugOverlay['_sections'][0] {
    const p = this._debugInfo!.performance;
    const fpsColor =
      p.fps >= 55 ? '#22cc66' :
      p.fps >= 30 ? '#ffaa00' : '#ff4444';

    return {
      title: '⚡ Performance',
      lines: [
        { label: 'FPS', value: `${p.fps}`, color: fpsColor },
        { label: 'Frame Time', value: `${p.frame_time_ms}ms` },
        { label: 'Render Latency', value: `${p.render_latency_ms}ms` },
        { label: 'Layers Rendered', value: `${p.layer_count}` },
      ],
    };
  }

  // ── Internal notify ───────────────────────────────────────────────────

  private _notify(): void {
    for (const cb of this._updateCallbacks) {
      cb(this._sections);
    }
  }

  // ── Serialization ──────────────────────────────────────────────────────

  getOverlayText(): string {
    return this._sections
      .map((section) => {
        const header = `── ${section.title} ──`;
        const lines = section.lines
          .map((l) => `  ${l.label}: ${l.value}`)
          .join('\n');
        return `${header}\n${lines}`;
      })
      .join('\n\n');
  }

  // ── Stats summary ──────────────────────────────────────────────────────

  getSummaryLine(): string {
    if (!this._debugInfo) return '';
    const t = this._debugInfo.tracking;
    const p = this._debugInfo.performance;
    const tl = this._debugInfo.timeline;
    return (
      `[${t.quality}] FPS:${p.fps} ` +
      `Progress:${(tl.progress * 100).toFixed(0)}% ` +
      `Events:${tl.current_index + 1}/${tl.event_count}`
    );
  }
}
