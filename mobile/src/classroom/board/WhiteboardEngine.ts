// ──────────────────────────────────────────────────────────────────────────────
// WhiteboardEngine — the digital teaching board.
//
// Supports:
//   - Handwriting, typing, math equations, diagrams, geometry, flowcharts
//   - Layers with z-ordering
//   - Undo / Redo stack
//   - Element-level animation tags
//   - Efficient incremental updates
// ──────────────────────────────────────────────────────────────────────────────

import type {
  BoardElement,
  BoardElementType,
  DiagramElement,
  FormulaElement,
  HighlightElement,
  Point,
  StrokeElement,
  TextElement,
} from '../types';

// ── Operations for undo/redo ─────────────────────────────────────────────────

interface BoardOperation {
  type: 'add' | 'remove' | 'modify' | 'clear';
  elementId?: string;
  previousState?: BoardElement[];
  element?: BoardElement;
  timestamp: number;
}

// ── WhiteboardEngine ─────────────────────────────────────────────────────────

export class WhiteboardEngine {
  private _elements: BoardElement[] = [];
  private _undoStack: BoardOperation[] = [];
  private _redoStack: BoardOperation[] = [];
  private readonly _maxUndoDepth = 100;
  private _nextId = 1;

  // ── Element management ──────────────────────────────────────────────────

  addElement(element: Omit<BoardElement, 'id' | 'timestamp'>): string {
    const id = this._generateId();
    const full: BoardElement = {
      ...element,
      id,
      timestamp: Date.now(),
    } as unknown as BoardElement;
    this._elements.push(full);
    this._pushUndo({ type: 'add', elementId: id, element: full, timestamp: Date.now() });
    this._redoStack = [];
    return id;
  }

  addStroke(stroke: Omit<StrokeElement, 'id' | 'timestamp' | 'type'>): string {
    return this.addElement({ ...stroke, type: 'stroke' } as unknown as Omit<BoardElement, 'id' | 'timestamp'>);
  }

  addText(text: Omit<TextElement, 'id' | 'timestamp' | 'type'>): string {
    return this.addElement({ ...text, type: 'text' } as unknown as Omit<BoardElement, 'id' | 'timestamp'>);
  }

  addFormula(formula: Omit<FormulaElement, 'id' | 'timestamp' | 'type'>): string {
    return this.addElement({ ...formula, type: 'formula' } as unknown as Omit<BoardElement, 'id' | 'timestamp'>);
  }

  addDiagram(diagram: Omit<DiagramElement, 'id' | 'timestamp' | 'type'>): string {
    return this.addElement({ ...diagram, type: 'diagram' } as unknown as Omit<BoardElement, 'id' | 'timestamp'>);
  }

  addHighlight(highlight: Omit<HighlightElement, 'id' | 'timestamp' | 'type'>): string {
    return this.addElement({ ...highlight, type: 'highlight' } as unknown as Omit<BoardElement, 'id' | 'timestamp'>);
  }

  removeElement(id: string): boolean {
    const idx = this._elements.findIndex((e) => e.id === id);
    if (idx === -1) return false;
    const removed = this._elements.splice(idx, 1)[0];
    this._pushUndo({
      type: 'remove',
      elementId: id,
      element: removed,
      previousState: [...this._elements],
      timestamp: Date.now(),
    });
    this._redoStack = [];
    return true;
  }

  modifyElement(id: string, changes: Partial<BoardElement>): boolean {
    const element = this._elements.find((e) => e.id === id);
    if (!element) return false;
    const previous = { ...element };
    Object.assign(element, changes, { id, timestamp: Date.now() });
    this._pushUndo({
      type: 'modify',
      elementId: id,
      element: { ...element },
      previousState: [previous],
      timestamp: Date.now(),
    });
    this._redoStack = [];
    return true;
  }

  clear(): void {
    if (this._elements.length === 0) return;
    this._pushUndo({
      type: 'clear',
      previousState: [...this._elements],
      timestamp: Date.now(),
    });
    this._elements = [];
    this._redoStack = [];
  }

  getElements(): BoardElement[] {
    return [...this._elements];
  }

  getElement(id: string): BoardElement | undefined {
    return this._elements.find((e) => e.id === id);
  }

  getElementsByType(type: BoardElementType): BoardElement[] {
    return this._elements.filter((e) => e.type === type);
  }

  getLayerElements(layer: number): BoardElement[] {
    return this._elements
      .filter((e) => e.layer === layer)
      .sort((a, b) => a.timestamp - b.timestamp);
  }

  getElementsInRect(rect: { x: number; y: number; width: number; height: number }): BoardElement[] {
    return this._elements.filter((e) => {
      if (e.type === 'stroke') {
        const stroke = e as StrokeElement;
        return stroke.points.some(
          (p) =>
            p.x >= rect.x &&
            p.x <= rect.x + rect.width &&
            p.y >= rect.y &&
            p.y <= rect.y + rect.height,
        );
      }
      return true;
    });
  }

  getAnimatedElements(): BoardElement[] {
    return this._elements.filter((e) => e.is_animated);
  }

  elementCount(): number {
    return this._elements.length;
  }

  // ── Undo / Redo ─────────────────────────────────────────────────────────

  undo(): boolean {
    const op = this._undoStack.pop();
    if (!op) return false;

    switch (op.type) {
      case 'add':
        if (op.elementId) {
          this._elements = this._elements.filter((e) => e.id !== op.elementId);
        }
        break;
      case 'remove':
        if (op.element) {
          this._elements.push(op.element);
        }
        break;
      case 'modify':
        if (op.previousState && op.elementId) {
          const idx = this._elements.findIndex((e) => e.id === op.elementId);
          if (idx !== -1) {
            this._elements[idx] = op.previousState[0];
          }
        }
        break;
      case 'clear':
        if (op.previousState) {
          this._elements = [...op.previousState];
        }
        break;
    }

    this._redoStack.push(op);
    return true;
  }

  redo(): boolean {
    const op = this._redoStack.pop();
    if (!op) return false;

    switch (op.type) {
      case 'add':
        if (op.element) {
          this._elements.push(op.element);
        }
        break;
      case 'remove':
        if (op.elementId) {
          this._elements = this._elements.filter((e) => e.id !== op.elementId);
        }
        break;
      case 'modify':
        if (op.element && op.elementId) {
          const idx = this._elements.findIndex((e) => e.id === op.elementId);
          if (idx !== -1) {
            this._elements[idx] = op.element;
          }
        }
        break;
      case 'clear':
        this._elements = [];
        break;
    }

    this._undoStack.push(op);
    return true;
  }

  canUndo(): boolean {
    return this._undoStack.length > 0;
  }

  canRedo(): boolean {
    return this._redoStack.length > 0;
  }

  // ── Serialization ───────────────────────────────────────────────────────

  serialize(): string {
    return JSON.stringify({
      elements: this._elements,
      version: 1,
    });
  }

  deserialize(json: string): void {
    try {
      const data = JSON.parse(json);
      if (data.version === 1 && Array.isArray(data.elements)) {
        this._elements = data.elements;
        this._undoStack = [];
        this._redoStack = [];
      }
    } catch {
      console.warn('[WhiteboardEngine] failed to deserialize board state');
    }
  }

  // ── Cache helpers ───────────────────────────────────────────────────────

  contentHash(): string {
    let hash = 0;
    for (const el of this._elements) {
      hash = ((hash << 5) - hash + el.id.length) | 0;
    }
    return hash.toString(16);
  }

  // ── Private ─────────────────────────────────────────────────────────────

  private _generateId(): string {
    return `board_${Date.now()}_${this._nextId++}`;
  }

  private _pushUndo(op: BoardOperation): void {
    this._undoStack.push(op);
    if (this._undoStack.length > this._maxUndoDepth) {
      this._undoStack.shift();
    }
  }
}
