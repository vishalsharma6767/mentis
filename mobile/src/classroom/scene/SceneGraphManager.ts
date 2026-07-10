// ──────────────────────────────────────────────────────────────────────────────
// SceneGraphManager — receives the Scene Graph from the Mentis backend,
// provides query access to all nodes for the rendering pipeline, and
// notifies subscribers when the scene graph updates.
//
// The Scene Graph is the single source of truth. The classroom engine
// never renders anything that isn't derived from this graph.
// ──────────────────────────────────────────────────────────────────────────────

import type { SceneGraphDTO, SceneNodeDTO, SceneEdgeDTO, NodeType } from '../types';

// ── SceneGraphManager ────────────────────────────────────────────────────────

export class SceneGraphManager {
  private _sceneGraph: SceneGraphDTO | null = null;
  private _nodesById = new Map<string, SceneNodeDTO>();
  private _edgesBySource = new Map<string, SceneEdgeDTO[]>();
  private _edgesByTarget = new Map<string, SceneEdgeDTO[]>();
  private _nodesByType = new Map<NodeType, SceneNodeDTO[]>();

  private _updateCallbacks: Array<(graph: SceneGraphDTO) => void> = [];
  private _lastUpdateTime = 0;

  // ── Loading ────────────────────────────────────────────────────────────

  loadSceneGraph(dto: SceneGraphDTO): void {
    this._sceneGraph = dto;
    this._indexGraph(dto);
    this._lastUpdateTime = Date.now();
    this._notify(dto);
  }

  clear(): void {
    this._sceneGraph = null;
    this._nodesById.clear();
    this._edgesBySource.clear();
    this._edgesByTarget.clear();
    this._nodesByType.clear();
    this._lastUpdateTime = 0;
  }

  // ── Node queries ───────────────────────────────────────────────────────

  getNode(id: string): SceneNodeDTO | undefined {
    return this._nodesById.get(id);
  }

  getNodes(): SceneNodeDTO[] {
    return this._sceneGraph?.nodes ?? [];
  }

  getNodesByType(type: NodeType): SceneNodeDTO[] {
    return this._nodesByType.get(type) ?? [];
  }

  getRootNodes(): string[] {
    return this._sceneGraph?.root_node_ids ?? [];
  }

  getRootNodeObjects(): SceneNodeDTO[] {
    const rootIds = this.getRootNodes();
    return rootIds
      .map((id) => this._nodesById.get(id))
      .filter((n): n is SceneNodeDTO => n !== undefined);
  }

  getQuestionNodes(): SceneNodeDTO[] {
    return this.getNodesByType('question');
  }

  getFormulaNodes(): SceneNodeDTO[] {
    return this.getNodesByType('formula');
  }

  getDiagramNodes(): SceneNodeDTO[] {
    return this.getNodesByType('diagram');
  }

  getGraphNodes(): SceneNodeDTO[] {
    return this.getNodesByType('graph');
  }

  getMistakeNodes(): SceneNodeDTO[] {
    return this.getNodesByType('mistake');
  }

  getConceptNodes(): SceneNodeDTO[] {
    return this.getNodesByType('concept');
  }

  getStudentAnswerNodes(): SceneNodeDTO[] {
    return this.getNodesByType('student_answer');
  }

  getStepNodes(): SceneNodeDTO[] {
    return this.getNodesByType('step');
  }

  getLearningObjectiveNodes(): SceneNodeDTO[] {
    return this.getNodesByType('learning_objective');
  }

  // ── Edge queries ───────────────────────────────────────────────────────

  getEdges(): SceneEdgeDTO[] {
    return this._sceneGraph?.edges ?? [];
  }

  getOutgoingEdges(nodeId: string): SceneEdgeDTO[] {
    return this._edgesBySource.get(nodeId) ?? [];
  }

  getIncomingEdges(nodeId: string): SceneEdgeDTO[] {
    return this._edgesByTarget.get(nodeId) ?? [];
  }

  getChildren(nodeId: string): SceneNodeDTO[] {
    const edges = this.getOutgoingEdges(nodeId);
    const childIds = edges
      .filter((e) => ['contains', 'has_answer', 'has_diagram', 'has_formula', 'next_step'].includes(e.type))
      .map((e) => e.target_id);
    return childIds
      .map((id) => this._nodesById.get(id))
      .filter((n): n is SceneNodeDTO => n !== undefined);
  }

  getParents(nodeId: string): SceneNodeDTO[] {
    const edges = this.getIncomingEdges(nodeId);
    const parentIds = edges
      .filter((e) => ['contains', 'has_answer', 'has_diagram', 'has_formula', 'next_step'].includes(e.type))
      .map((e) => e.source_id);
    return parentIds
      .map((id) => this._nodesById.get(id))
      .filter((n): n is SceneNodeDTO => n !== undefined);
  }

  // ── Derived data ───────────────────────────────────────────────────────

  getTextContent(nodeId: string): string {
    return this._nodesById.get(nodeId)?.content ?? '';
  }

  getQuestionCount(): number {
    return this.getQuestionNodes().length;
  }

  getMistakeCount(): number {
    return this.getMistakeNodes().length;
  }

  getFormulaCount(): number {
    return this.getFormulaNodes().length;
  }

  getDiagramCount(): number {
    return this.getDiagramNodes().length;
  }

  hasQuestion(): boolean {
    return this.getQuestionCount() > 0;
  }

  hasMistakes(): boolean {
    return this.getMistakeCount() > 0;
  }

  hasDiagrams(): boolean {
    return this.getDiagramCount() > 0;
  }

  hasFormulas(): boolean {
    return this.getFormulaCount() > 0;
  }

  getSceneConfidence(): number {
    return this._sceneGraph?.metadata.vision_confidence ?? 0;
  }

  getNodeCount(): number {
    return this._sceneGraph?.metadata.node_count ?? 0;
  }

  getEdgeCount(): number {
    return this._sceneGraph?.metadata.edge_count ?? 0;
  }

  getLastUpdateTime(): number {
    return this._lastUpdateTime;
  }

  getRaw(): SceneGraphDTO | null {
    return this._sceneGraph;
  }

  // ── Subscriptions ──────────────────────────────────────────────────────

  onUpdate(cb: (graph: SceneGraphDTO) => void): () => void {
    this._updateCallbacks.push(cb);
    // Immediately call with current graph if available
    if (this._sceneGraph) {
      cb(this._sceneGraph);
    }
    return () => {
      this._updateCallbacks = this._updateCallbacks.filter((f) => f !== cb);
    };
  }

  // ── Internals ──────────────────────────────────────────────────────────

  private _indexGraph(dto: SceneGraphDTO): void {
    this._nodesById.clear();
    this._edgesBySource.clear();
    this._edgesByTarget.clear();
    this._nodesByType.clear();

    for (const node of dto.nodes) {
      this._nodesById.set(node.id, node);
      const type = node.type;
      if (!this._nodesByType.has(type)) {
        this._nodesByType.set(type, []);
      }
      this._nodesByType.get(type)!.push(node);
    }

    for (const edge of dto.edges) {
      if (!this._edgesBySource.has(edge.source_id)) {
        this._edgesBySource.set(edge.source_id, []);
      }
      this._edgesBySource.get(edge.source_id)!.push(edge);

      if (!this._edgesByTarget.has(edge.target_id)) {
        this._edgesByTarget.set(edge.target_id, []);
      }
      this._edgesByTarget.get(edge.target_id)!.push(edge);
    }
  }

  private _notify(dto: SceneGraphDTO): void {
    this._updateCallbacks.forEach((cb) => cb(dto));
  }
}
