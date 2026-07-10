// ──────────────────────────────────────────────────────────────────────────────
// ResourceManager — manages preloading, caching, and lifecycle of all resources
// used by the live teacher system.
//
// Handles audio, animations, images, fonts, diagrams, lesson data, and pointer
// assets. Supports eager loading, lazy loading, LRU eviction, and offline mode.
// ──────────────────────────────────────────────────────────────────────────────

import type { ResourceType, ResourceEntry, LiveTeacherEvent } from '../types';

export interface ResourceManagerConfig {
  max_cache_size_bytes: number;
  enable_offline: boolean;
  preload_on_start: string[];
  onEvent?: (event: LiveTeacherEvent) => void;
}

const DEFAULT_CONFIG: ResourceManagerConfig = {
  max_cache_size_bytes: 50 * 1024 * 1024, // 50 MB
  enable_offline: false,
  preload_on_start: [],
};

export class ResourceManager {
  private _config: ResourceManagerConfig;
  private _cache: Map<string, ResourceEntry> = new Map();
  private _loadedData: Map<string, unknown> = new Map();
  private _pendingLoads: Map<string, Promise<unknown>> = new Map();
  private _totalSizeBytes = 0;

  constructor(config: Partial<ResourceManagerConfig> = {}) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── Registration ───────────────────────────────────────────────────────

  register(id: string, type: ResourceType, uri: string, sizeBytes: number): void {
    const entry: ResourceEntry = {
      id,
      type,
      uri,
      size_bytes: sizeBytes,
      cached: false,
      loaded: false,
      last_accessed: Date.now(),
    };
    this._cache.set(id, entry);
  }

  unregister(id: string): void {
    this._cache.delete(id);
    this._loadedData.delete(id);
  }

  // ── Loading ────────────────────────────────────────────────────────────

  async load(id: string): Promise<unknown> {
    const entry = this._cache.get(id);
    if (!entry) throw new Error(`Resource not registered: ${id}`);

    if (entry.loaded) {
      entry.last_accessed = Date.now();
      return this._loadedData.get(id);
    }

    const pending = this._pendingLoads.get(id);
    if (pending) return pending as Promise<unknown>;

    const loadPromise = this._doLoad(entry);
    this._pendingLoads.set(id, loadPromise);
    try {
      const data = await loadPromise;
      return data;
    } finally {
      this._pendingLoads.delete(id);
    }
  }

  async preload(ids: string[]): Promise<void> {
    await Promise.all(ids.map((id) => this.load(id)));
  }

  get(id: string): unknown {
    const entry = this._cache.get(id);
    if (!entry || !entry.loaded) return undefined;
    entry.last_accessed = Date.now();
    return this._loadedData.get(id);
  }

  // ── Cache Management ───────────────────────────────────────────────────

  isCached(id: string): boolean {
    return this._cache.get(id)?.loaded ?? false;
  }

  evict(id: string): void {
    const entry = this._cache.get(id);
    if (!entry) return;
    this._totalSizeBytes -= entry.size_bytes;
    this._loadedData.delete(id);
    entry.cached = false;
    entry.loaded = false;
    this._config.onEvent?.({
      type: 'resource:evicted',
      timestamp: Date.now(),
      data: { id, type: entry.type },
    });
  }

  evictAll(): void {
    for (const [id] of this._cache) {
      this.evict(id);
    }
  }

  evictLeastRecentlyUsed(count: number): void {
    const sorted = Array.from(this._cache.values())
      .filter((e) => e.loaded)
      .sort((a, b) => a.last_accessed - b.last_accessed);
    for (let i = 0; i < Math.min(count, sorted.length); i++) {
      this.evict(sorted[i].id);
    }
  }

  get cacheSize(): number {
    return this._totalSizeBytes;
  }

  get cacheCount(): number {
    let count = 0;
    for (const entry of this._cache.values()) {
      if (entry.loaded) count++;
    }
    return count;
  }

  get registeredCount(): number {
    return this._cache.size;
  }

  // ── Offline ────────────────────────────────────────────────────────────

  isOfflineReady(): boolean {
    if (!this._config.enable_offline) return false;
    for (const entry of this._cache.values()) {
      if (!entry.loaded) return false;
    }
    return true;
  }

  // ── Private ────────────────────────────────────────────────────────────

  private async _doLoad(entry: ResourceEntry): Promise<unknown> {
    // Check cache space
    if (this._totalSizeBytes + entry.size_bytes > this._config.max_cache_size_bytes) {
      this.evictLeastRecentlyUsed(1);
    }

    // Simulated load — in production would fetch from filesystem/network
    const data = await this._fetchResource(entry);
    this._loadedData.set(entry.id, data);
    entry.loaded = true;
    entry.cached = true;
    entry.last_accessed = Date.now();
    this._totalSizeBytes += entry.size_bytes;

    this._config.onEvent?.({
      type: 'resource:loaded',
      timestamp: Date.now(),
      data: { id: entry.id, type: entry.type, size: entry.size_bytes },
    });

    return data;
  }

  private async _fetchResource(entry: ResourceEntry): Promise<unknown> {
    // Placeholder for actual resource loading
    return { uri: entry.uri, loaded: true };
  }

  dispose(): void {
    this.evictAll();
    this._cache.clear();
    this._loadedData.clear();
    this._pendingLoads.clear();
  }
}
