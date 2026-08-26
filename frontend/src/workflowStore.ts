import { addEdge as addReactFlowEdge, applyEdgeChanges, applyNodeChanges, type Edge, type EdgeChange, type NodeChange } from "@xyflow/react";
import { create } from "zustand";
import { clips, createPendingGeneratorClip, createWorkflowNode, inferDishCategory, normalizeTimelineClip, randomizeClipSelection, recommendClipSelection, removeNodeAndEdges, reorderById, resolveGeneratorNodeStatus, type ClipLibraryItem, type ComposeJob, type ComposeWorkspace, type DraftPayload, type GenerationJob, type ImageProcessingJob, type NodeKind, type Panel, type TimelineClip, type WorkflowData, type WorkflowNode } from "./model";
import { workflowSeed } from "./seed";
import { fetchCanvasClips, fetchDraft, persistDraft, startCanvasGeneration, startCanvasImageProcessing, waitForCanvasGeneration, waitForCanvasImageProcessing } from "./api";

type WorkflowState = {
  nodes: WorkflowNode[];
  edges: Edge[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  activePanel: Panel;
  timeline: TimelineClip[];
  candidateClips: TimelineClip[];
  composeBatchCount: number;
  composeClipCount: number;
  composeWorkspaces: ComposeWorkspace[];
  availableClips: ClipLibraryItem[];
  clipsLoaded: boolean;
  clipsLastLoadedAt: string | null;
  clipsLoadError: string | null;
  bgmName: string;
  bgmUrl: string;
  composeJob: ComposeJob | null;
  nextNodeNumber: number;
  draftId: string;
  hydrated: boolean;
  saving: boolean;
  lastSavedAt: string | null;
  revision: number;
  setNodes: (changes: NodeChange<WorkflowNode>[]) => void;
  setEdges: (changes: EdgeChange[]) => void;
  addEdge: (edge: Edge) => void;
  setSelection: (nodeId: string | null, edgeId?: string | null) => void;
  setActivePanel: (panel: Panel) => void;
  updateNodeData: (nodeId: string, patch: Partial<WorkflowData>) => void;
  registerGeneratorClip: (nodeId: string) => void;
  attachGeneratedClip: (nodeId: string, clip: TimelineClip) => void;
  generateNode: (nodeId: string) => Promise<GenerationJob>;
  processImageNode: (nodeId: string) => Promise<ImageProcessingJob>;
  addNode: (kind: NodeKind) => void;
  deleteNode: (nodeId: string) => void;
  duplicateNode: (nodeId: string) => void;
  deleteSelected: () => void;
  duplicateSelected: () => void;
  reorderTimeline: (sourceId: string, targetId: string) => void;
  removeTimelineClip: (clipId: string) => void;
  updateTimelineClip: (clipId: string, patch: Partial<TimelineClip>) => void;
  updateWorkspaceClip: (workspaceId: string, clipId: string, patch: Partial<TimelineClip>) => void;
  toggleClip: (clipId: string) => void;
  loadClipLibrary: () => Promise<void>;
  setBgmName: (name: string) => void;
  setBgm: (name: string, url: string) => void;
  clearBgm: () => void;
  setComposeJob: (job: ComposeJob | null) => void;
  setComposeBatchCount: (count: number) => void;
  setComposeClipCount: (count: number) => void;
  randomizeComposeWorkspaces: () => void;
  recommendComposeWorkspaces: () => void;
  reorderWorkspace: (workspaceId: string, sourceId: string, targetId: string) => void;
  removeWorkspaceClip: (workspaceId: string, clipId: string) => void;
  addWorkspaceClip: (workspaceId: string, clipId: string) => void;
  setWorkspaceJob: (workspaceId: string, job: ComposeJob | null) => void;
  loadDraft: () => Promise<void>;
  saveDraft: () => Promise<void>;
};

const protectedNodeIds = new Set(["assets", "image_process", "prompt", "clips", "output", "sound"]);

function migrateImageProcessNode(nodes: WorkflowNode[], edges: Edge[]): { nodes: WorkflowNode[]; edges: Edge[] } {
  if (nodes.some(node => node.data.kind === "image_process")) return { nodes, edges };
  const assets = nodes.find(node => node.id === "assets" || node.data.kind === "input");
  const prompt = nodes.find(node => node.id === "prompt" || node.data.kind === "prompt");
  if (!assets || !prompt) return { nodes, edges };
  const processNode = createWorkflowNode("image_process", "image_process", { x: (assets.position.x + prompt.position.x) / 2, y: Math.min(assets.position.y, prompt.position.y) });
  const withoutLegacy = edges.filter(edge => !(edge.source === assets.id && edge.target === prompt.id));
  return {
    nodes: [...nodes, processNode],
    edges: [
      ...withoutLegacy,
      { id: `${assets.id}-image-process`, source: assets.id, target: processNode.id, type: "smoothstep" },
      { id: `image-process-${prompt.id}`, source: processNode.id, target: prompt.id, type: "smoothstep" },
    ],
  };
}

function sameClipList(left: TimelineClip[], right: TimelineClip[]): boolean {
  if (left.length !== right.length) return false;
  return left.every((clip, index) => {
    const other = right[index];
    return Boolean(other)
      && clip.id === other.id
      && clip.dish === other.dish
      && clip.label === other.label
      && clip.tone === other.tone
      && clip.timelineDuration === other.timelineDuration
      && clip.sourceDurationSeconds === other.sourceDurationSeconds
      && clip.sourceStartSeconds === other.sourceStartSeconds
      && clip.sourceEndSeconds === other.sourceEndSeconds
      && clip.trimConfirmed === other.trimConfirmed
      && clip.status === other.status
      && clip.sourcePath === other.sourcePath
      && clip.sourceUrl === other.sourceUrl
      && clip.dishCategory === other.dishCategory
      && clip.filename === other.filename
      && clip.generatorNodeId === other.generatorNodeId
      && clip.generationJobId === other.generationJobId
      && clip.qualityScore === other.qualityScore
      && clip.qualityLabel === other.qualityLabel
      && JSON.stringify(clip.qualityWarnings ?? []) === JSON.stringify(other.qualityWarnings ?? []);
  });
}

function withResolvedDishCategory<T extends TimelineClip>(clip: T): T {
  return clip.dishCategory ? clip : { ...clip, dishCategory: inferDishCategory(clip.dish) };
}

function mergeAvailableClips(persisted: TimelineClip[], available: ClipLibraryItem[]): TimelineClip[] {
  const matched = new Set<string>();
  const merged = persisted.map(item => {
    const match = available.find(candidate =>
      (item.sourcePath && candidate.sourcePath === item.sourcePath)
      || (item.filename && candidate.filename === item.filename),
    );
    if (!match) return item;
    matched.add(match.id);
    return {
      ...match,
      id: item.id,
      generatorNodeId: item.generatorNodeId ?? match.generatorNodeId,
      generationJobId: item.generationJobId ?? match.generationJobId,
      dishCategory: item.dishCategory ?? match.dishCategory,
      // The draft is the source of truth for clip timing. This also keeps
      // trims made before the explicit confirmation flag was introduced.
      ...(item.sourceStartSeconds !== undefined || item.sourceEndSeconds !== undefined ? {
        sourceStartSeconds: item.sourceStartSeconds,
        sourceEndSeconds: item.sourceEndSeconds,
        timelineDuration: item.timelineDuration,
        trimConfirmed: item.trimConfirmed,
      } : {}),
    };
  });
  return [...merged, ...available.filter(item => !matched.has(item.id) && !persisted.some(existing => existing.sourcePath === item.sourcePath || existing.filename === item.filename))];
}

function syncGeneratorNodeStatuses(nodes: WorkflowNode[], candidateClips: TimelineClip[]): WorkflowNode[] {
  return nodes.map(node => {
    if (node.data.kind !== "generator") return node;
    const clip = candidateClips.find(item => item.generatorNodeId === node.id);
    const status = resolveGeneratorNodeStatus(node.data.status, clip);
    return status === node.data.status ? node : { ...node, data: { ...node.data, status } };
  });
}

function syncPrimaryWorkspace(workspaces: ComposeWorkspace[], timeline: TimelineClip[]): ComposeWorkspace[] {
  return workspaces.map((workspace, index) => index === 0 ? { ...workspace, clips: timeline, job: null } : workspace);
}

function removeNodeArtifacts(state: Pick<WorkflowState, "candidateClips" | "composeWorkspaces" | "timeline">, nodeIds: Set<string>) {
  const candidateClips = state.candidateClips.filter(clip => !clip.generatorNodeId || !nodeIds.has(clip.generatorNodeId));
  const composeWorkspaces = state.composeWorkspaces.map(workspace => ({
    ...workspace,
    clips: workspace.clips.filter(clip => !clip.generatorNodeId || !nodeIds.has(clip.generatorNodeId)),
  }));
  const timeline = composeWorkspaces[0]?.clips ?? state.timeline.filter(clip => !clip.generatorNodeId || !nodeIds.has(clip.generatorNodeId));
  return { candidateClips, composeWorkspaces, timeline };
}

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  nodes: workflowSeed.nodes,
  edges: workflowSeed.edges,
  selectedNodeId: "assets",
  selectedEdgeId: null,
  activePanel: "prompt",
  timeline: workflowSeed.timeline,
  candidateClips: workflowSeed.candidateClips,
  composeBatchCount: workflowSeed.composeBatchCount,
  composeClipCount: workflowSeed.composeClipCount,
  composeWorkspaces: workflowSeed.composeWorkspaces,
  availableClips: [],
  clipsLoaded: false,
  clipsLastLoadedAt: null,
  clipsLoadError: null,
  bgmName: workflowSeed.bgmName,
  bgmUrl: "",
  composeJob: null,
  nextNodeNumber: 1,
  draftId: "default",
  hydrated: false,
  saving: false,
  lastSavedAt: null,
  revision: 0,
  setNodes: changes => set(state => {
    const safeChanges = changes.filter(change => !(change.type === "remove" && protectedNodeIds.has(change.id)));
    const nodes = applyNodeChanges(safeChanges, state.nodes) as WorkflowNode[];
    const removed = new Set(safeChanges.filter(change => change.type === "remove").map(change => change.id));
    const artifacts = removed.size ? removeNodeArtifacts(state, removed) : {};
    return {
      nodes,
      edges: removed.size ? state.edges.filter(edge => !removed.has(edge.source) && !removed.has(edge.target)) : state.edges,
      ...artifacts,
      selectedNodeId: state.selectedNodeId && removed.has(state.selectedNodeId) ? null : state.selectedNodeId,
      revision: state.revision + 1,
    };
  }),
  setEdges: changes => set(state => {
    const edges = applyEdgeChanges(changes, state.edges);
    const removed = new Set(changes.filter(change => change.type === "remove").map(change => change.id));
    return { edges, selectedEdgeId: state.selectedEdgeId && removed.has(state.selectedEdgeId) ? null : state.selectedEdgeId, revision: state.revision + 1 };
  }),
  addEdge: edge => set(state => ({ edges: addReactFlowEdge(edge, state.edges), selectedNodeId: null, selectedEdgeId: null, revision: state.revision + 1 })),
  setSelection: (nodeId, edgeId = null) => set(state => {
    const nextEdgeId = nodeId ? null : edgeId;
    if (state.selectedNodeId === nodeId && state.selectedEdgeId === nextEdgeId) return {};
    return { selectedNodeId: nodeId, selectedEdgeId: nextEdgeId };
  }),
  setActivePanel: activePanel => set(state => ({ activePanel, revision: state.revision + 1 })),
  updateNodeData: (nodeId, patch) => set(state => {
    const node = state.nodes.find(item => item.id === nodeId);
    const data = node ? { ...node.data, ...patch } : null;
    const primaryInput = state.nodes.find(item => item.data.kind === "input");
    const shouldSyncClipMetadata = node?.data.kind === "input"
      && primaryInput?.id === nodeId
      && ("dishName" in patch || "dishCategory" in patch);
    if (!shouldSyncClipMetadata || !data) {
      return { nodes: state.nodes.map(item => item.id === nodeId ? { ...item, data: { ...item.data, ...patch } } : item), revision: state.revision + 1 };
    }
    const dish = data.dishName || "待配置菜品";
    const dishCategory = data.dishCategory ?? (data.dishName ? inferDishCategory(dish) : "正餐");
    const syncClip = (clip: TimelineClip) => clip.generatorNodeId ? { ...clip, dish, dishCategory } : clip;
    const candidateClips = state.candidateClips.map(syncClip);
    const timeline = state.timeline.map(syncClip);
    const composeWorkspaces = state.composeWorkspaces.map(workspace => ({ ...workspace, clips: workspace.clips.map(syncClip) }));
    return {
      nodes: state.nodes.map(item => item.id === nodeId ? { ...item, data: { ...item.data, ...patch } } : item),
      candidateClips,
      timeline,
      composeWorkspaces,
      revision: state.revision + 1,
    };
  }),
  registerGeneratorClip: nodeId => set(state => {
    const node = state.nodes.find(item => item.id === nodeId && item.data.kind === "generator");
    if (!node) return {};
    const existing = state.candidateClips.find(item => item.generatorNodeId === nodeId);
    const input = state.nodes.find(item => item.data.kind === "input");
    const dish = input?.data.dishName || existing?.dish || "待配置菜品";
    const dishCategory = input?.data.dishCategory ?? existing?.dishCategory ?? (input?.data.dishName ? inferDishCategory(dish) : "正餐");
    const clip = existing
      ? { ...existing, dish, dishCategory, label: "生成任务", status: "pending" as const }
      : createPendingGeneratorClip(nodeId, state.nextNodeNumber, dish, dishCategory);
    const candidateClips = existing
      ? state.candidateClips.map(item => item.id === existing.id ? clip : item)
      : [...state.candidateClips, clip];
    return {
      nodes: state.nodes.map(item => item.id === nodeId ? { ...item, data: { ...item.data, status: "待关联真实文件" } } : item),
      candidateClips,
      revision: state.revision + 1,
    };
  }),
  attachGeneratedClip: (nodeId, clip) => set(state => {
    const existing = state.candidateClips.find(item => item.generatorNodeId === nodeId);
    const nextClip = normalizeTimelineClip({
      ...clip,
      id: existing?.id ?? clip.id,
      generatorNodeId: nodeId,
      status: "generated" as const,
    });
    const candidateClips = existing
      ? state.candidateClips.map(item => item.id === existing.id ? nextClip : item)
      : [...state.candidateClips, nextClip];
    const replace = (items: TimelineClip[]) => existing ? items.map(item => item.id === existing.id ? nextClip : item) : items;
    const composeWorkspaces = state.composeWorkspaces.map(workspace => ({ ...workspace, clips: replace(workspace.clips) }));
    return {
      candidateClips,
      timeline: replace(state.timeline),
      composeWorkspaces,
      availableClips: [...state.availableClips.filter(item => item.sourcePath !== nextClip.sourcePath), nextClip as ClipLibraryItem],
      nodes: state.nodes.map(item => item.id === nodeId ? { ...item, data: { ...item.data, status: "已生成" } } : item),
      revision: state.revision + 1,
    };
  }),
  generateNode: async nodeId => {
    const state = get();
    state.registerGeneratorClip(nodeId);
    state.updateNodeData(nodeId, { status: "生成中" });
    await get().saveDraft();
    try {
      const started = await startCanvasGeneration(get().draftId, nodeId);
      const completed = await waitForCanvasGeneration(get().draftId, started);
      if (completed.status === "error") throw new Error(completed.error || "Kling 生成失败");
      if (completed.status !== "done" || !completed.clip) throw new Error("生成任务超时，请检查后端日志");
      get().attachGeneratedClip(nodeId, completed.clip);
      await get().saveDraft();
      return completed;
    } catch (error) {
      get().updateNodeData(nodeId, { status: "生成失败" });
      throw error;
    }
  },
  processImageNode: async nodeId => {
    const state = get();
    state.updateNodeData(nodeId, { status: "处理中" });
    await get().saveDraft();
    try {
      const started = await startCanvasImageProcessing(get().draftId, nodeId);
      const completed = await waitForCanvasImageProcessing(get().draftId, started);
      if (completed.status === "error") throw new Error(completed.error || "图片处理失败");
      if (completed.status !== "done" || !completed.result_url || !completed.result_name) throw new Error("图片处理任务超时，请检查后端日志");
      get().updateNodeData(nodeId, {
        status: "已处理",
        imageProcessingJobId: completed.job_id,
        processedImagePreview: completed.result_url,
        processedImageName: completed.result_name,
        processedImageAnalysis: completed.analysis ?? undefined,
      });
      await get().saveDraft();
      return completed;
    } catch (error) {
      get().updateNodeData(nodeId, { status: "处理失败" });
      throw error;
    }
  },
  addNode: kind => set(state => {
    const id = `node_${kind}_${state.nextNodeNumber}`;
    const index = state.nextNodeNumber - 1;
    return {
      nodes: [...state.nodes, createWorkflowNode(kind, id, { x: 24 + (index % 3) * 260, y: 520 + Math.floor(index / 3) * 220 })],
      nextNodeNumber: state.nextNodeNumber + 1,
      selectedNodeId: id,
      selectedEdgeId: null,
      revision: state.revision + 1,
    };
  }),
  deleteNode: nodeId => set(state => {
    if (protectedNodeIds.has(nodeId)) return {};
    const next = removeNodeAndEdges(state.nodes, state.edges, nodeId);
    const artifacts = removeNodeArtifacts(state, new Set([nodeId]));
    return {
      ...next,
      ...artifacts,
      selectedNodeId: state.selectedNodeId === nodeId ? null : state.selectedNodeId,
      revision: state.revision + 1,
    };
  }),
  duplicateNode: nodeId => set(state => {
    const source = state.nodes.find(node => node.id === nodeId);
    if (!source) return {};
    const id = `node_${source.data.kind}_${state.nextNodeNumber}`;
    const copy = {
      ...source,
      id,
      position: { x: source.position.x + 36, y: source.position.y + 36 },
      data: { ...source.data, title: `${source.data.title} 副本`, ...(source.data.kind === "generator" ? { status: "待生成" } : {}) },
      selected: true,
    };
    return {
      nodes: [...state.nodes, copy],
      nextNodeNumber: state.nextNodeNumber + 1,
      selectedNodeId: id,
      selectedEdgeId: null,
      revision: state.revision + 1,
    };
  }),
  deleteSelected: () => set(state => {
    if (state.selectedEdgeId) return { edges: state.edges.filter(edge => edge.id !== state.selectedEdgeId), selectedEdgeId: null, revision: state.revision + 1 };
    if (!state.selectedNodeId || protectedNodeIds.has(state.selectedNodeId)) return {};
    const next = removeNodeAndEdges(state.nodes, state.edges, state.selectedNodeId);
    return { ...next, selectedNodeId: null, revision: state.revision + 1 };
  }),
  duplicateSelected: () => set(state => {
    const source = state.nodes.find(node => node.id === state.selectedNodeId);
    if (!source) return {};
    const id = `node_${source.data.kind}_${state.nextNodeNumber}`;
    const copy = { ...source, id, position: { x: source.position.x + 36, y: source.position.y + 36 }, data: { ...source.data, title: `${source.data.title} 副本`, ...(source.data.kind === "generator" ? { status: "待生成" } : {}) }, selected: true };
    return { nodes: [...state.nodes, copy], nextNodeNumber: state.nextNodeNumber + 1, selectedNodeId: id, selectedEdgeId: null, revision: state.revision + 1 };
  }),
  reorderTimeline: (sourceId, targetId) => set(state => {
    const timeline = reorderById(state.timeline, sourceId, targetId);
    return { timeline, composeWorkspaces: syncPrimaryWorkspace(state.composeWorkspaces, timeline), revision: state.revision + 1 };
  }),
  removeTimelineClip: clipId => set(state => {
    const timeline = state.timeline.filter(clip => clip.id !== clipId);
    return { timeline, composeWorkspaces: syncPrimaryWorkspace(state.composeWorkspaces, timeline), revision: state.revision + 1 };
  }),
  updateTimelineClip: (clipId, patch) => set(state => {
    const timeline = state.timeline.map(clip => clip.id === clipId ? normalizeTimelineClip({ ...clip, ...patch }) : clip);
    return { timeline, composeWorkspaces: syncPrimaryWorkspace(state.composeWorkspaces, timeline), revision: state.revision + 1 };
  }),
  updateWorkspaceClip: (_workspaceId, clipId, patch) => set(state => {
    // A trim belongs to the source clip, so every composition reuses it.
    const update = <T extends TimelineClip>(clip: T): T => clip.id === clipId
      ? normalizeTimelineClip({ ...clip, ...patch })
      : clip;
    const composeWorkspaces = state.composeWorkspaces.map(workspace => {
      const includesClip = workspace.clips.some(clip => clip.id === clipId);
      return includesClip ? { ...workspace, clips: workspace.clips.map(update), job: null } : workspace;
    });
    return {
      candidateClips: state.candidateClips.map(update),
      availableClips: state.availableClips.map(clip => update(clip)),
      composeWorkspaces,
      timeline: composeWorkspaces[0]?.clips ?? state.timeline.map(update),
      revision: state.revision + 1,
    };
  }),
  toggleClip: clipId => set(state => {
    const clip = state.candidateClips.find(item => item.id === clipId) ?? state.availableClips.find(item => item.id === clipId) ?? clips.find(item => item.id === clipId);
    if (!clip) return {};
    const exists = state.timeline.some(item => item.id === clipId);
    const timeline = exists ? state.timeline.filter(item => item.id !== clipId) : [...state.timeline, clip];
    return { timeline, composeWorkspaces: syncPrimaryWorkspace(state.composeWorkspaces, timeline), revision: state.revision + 1 };
  }),
  loadClipLibrary: async () => {
    try {
      const availableClips = (await fetchCanvasClips()).map(clip => withResolvedDishCategory(normalizeTimelineClip(clip)));
      set(state => {
        const normalizedTimeline = state.timeline.map(clip => withResolvedDishCategory(normalizeTimelineClip(clip)));
        const normalizedCandidates = state.candidateClips.map(clip => withResolvedDishCategory(normalizeTimelineClip(clip)));
        const seedIds = new Set(clips.map(item => item.id));
        const isUnlinkedSeedTimeline = normalizedTimeline.length > 0 && normalizedTimeline.every(item => seedIds.has(item.id) && !item.sourcePath);
        const timeline = isUnlinkedSeedTimeline && availableClips.length
          ? normalizedTimeline.map((item, index) => availableClips[index] ? { ...availableClips[index] } : item)
          : normalizedTimeline;
        const isUnlinkedSeedCandidates = normalizedCandidates.length > 0 && normalizedCandidates.every(item => seedIds.has(item.id) && !item.sourcePath);
        const candidateClips = isUnlinkedSeedCandidates && availableClips.length
          ? availableClips.map(item => ({ ...item }))
          : mergeAvailableClips(normalizedCandidates, availableClips);
        const nodes = syncGeneratorNodeStatuses(state.nodes, candidateClips);
        const timelineChanged = !sameClipList(timeline, state.timeline);
        const candidateClipsChanged = !sameClipList(candidateClips, state.candidateClips);
        const nodesChanged = nodes.some((node, index) => node !== state.nodes[index]);
        const workspaces = timelineChanged ? syncPrimaryWorkspace(state.composeWorkspaces, timeline) : state.composeWorkspaces;
        return {
          nodes,
          availableClips,
          clipsLoaded: true,
          clipsLastLoadedAt: new Date().toISOString(),
          clipsLoadError: null,
          timeline,
          candidateClips,
          composeWorkspaces: workspaces,
          revision: timelineChanged || candidateClipsChanged || nodesChanged ? state.revision + 1 : state.revision,
        };
      });
    } catch (error) {
      set({ clipsLoadError: error instanceof Error ? error.message : "片段库扫描失败" });
      throw error;
    }
  },
  setBgmName: bgmName => set(state => ({ bgmName, revision: state.revision + 1 })),
  setBgm: (bgmName, bgmUrl) => set(state => ({ bgmName, bgmUrl, revision: state.revision + 1 })),
  clearBgm: () => set(state => ({ bgmName: "", bgmUrl: "", revision: state.revision + 1 })),
  setComposeJob: composeJob => set(state => ({ composeJob, revision: state.revision + 1 })),
  setComposeBatchCount: count => set(state => {
    const nextCount = Math.max(1, Math.min(20, Math.round(count)));
    const workspaces = Array.from({ length: nextCount }, (_, index) => state.composeWorkspaces[index] ?? { id: `compose_${index + 1}`, title: `成片 ${index + 1}`, clips: [], job: null });
    return { composeBatchCount: nextCount, composeWorkspaces: workspaces, revision: state.revision + 1 };
  }),
  setComposeClipCount: count => set(state => ({ composeClipCount: Math.max(1, Math.min(20, Math.round(count))), revision: state.revision + 1 })),
  randomizeComposeWorkspaces: () => set(state => {
    const pool = state.candidateClips.filter(clip => clip.sourcePath);
    const workspaces = state.composeWorkspaces.map(workspace => {
      return { ...workspace, clips: randomizeClipSelection(pool, state.composeClipCount), job: null };
    });
    return { composeWorkspaces: workspaces, timeline: workspaces[0]?.clips ?? [], revision: state.revision + 1 };
  }),
  recommendComposeWorkspaces: () => set(state => {
    const pool = state.candidateClips.filter(clip => clip.sourcePath);
    const workspaces = state.composeWorkspaces.map(workspace => ({
      ...workspace,
      clips: recommendClipSelection(pool, state.composeClipCount),
      job: null,
    }));
    return { composeWorkspaces: workspaces, timeline: workspaces[0]?.clips ?? [], revision: state.revision + 1 };
  }),
  reorderWorkspace: (workspaceId, sourceId, targetId) => set(state => {
    const composeWorkspaces = state.composeWorkspaces.map(workspace => workspace.id === workspaceId ? { ...workspace, clips: reorderById(workspace.clips, sourceId, targetId), job: null } : workspace);
    return { composeWorkspaces, timeline: composeWorkspaces[0]?.clips ?? state.timeline, revision: state.revision + 1 };
  }),
  removeWorkspaceClip: (workspaceId, clipId) => set(state => {
    const composeWorkspaces = state.composeWorkspaces.map(workspace => workspace.id === workspaceId ? { ...workspace, clips: workspace.clips.filter(clip => clip.id !== clipId), job: null } : workspace);
    return { composeWorkspaces, timeline: composeWorkspaces[0]?.clips ?? state.timeline, revision: state.revision + 1 };
  }),
  addWorkspaceClip: (workspaceId, clipId) => set(state => {
    const clip = state.candidateClips.find(item => item.id === clipId);
    if (!clip) return {};
    const composeWorkspaces = state.composeWorkspaces.map(workspace => workspace.id === workspaceId && !workspace.clips.some(item => item.id === clipId) ? { ...workspace, clips: [...workspace.clips, clip], job: null } : workspace);
    return { composeWorkspaces, timeline: composeWorkspaces[0]?.clips ?? state.timeline, revision: state.revision + 1 };
  }),
  setWorkspaceJob: (workspaceId, job) => set(state => ({ composeWorkspaces: state.composeWorkspaces.map(workspace => workspace.id === workspaceId ? { ...workspace, job } : workspace), revision: state.revision + 1 })),
  loadDraft: async () => {
    const state = get();
    if (state.hydrated) return;
    const draft = await fetchDraft(state.draftId);
    if (!draft) {
      set({ hydrated: true });
      return;
    }
    const migrated = migrateImageProcessNode(draft.nodes as WorkflowNode[], draft.edges);
    const normalizedCandidates = (draft.candidateClips ?? draft.timeline).map(normalizeTimelineClip);
    const normalizedNodes = migrated.nodes.map(node => node.data.kind === "input" && !node.data.dishCategory
        ? { ...node, data: { ...node.data, dishCategory: node.data.dishName ? inferDishCategory(node.data.dishName) : "正餐" } }
        : node);
    const nodes = syncGeneratorNodeStatuses(normalizedNodes, normalizedCandidates);
    const nodesChanged = nodes.some((node, index) => node !== migrated.nodes[index]);
    set({
      nodes,
      edges: migrated.edges,
      timeline: draft.timeline.map(normalizeTimelineClip),
      candidateClips: normalizedCandidates,
      composeBatchCount: draft.composeBatchCount ?? 1,
      composeClipCount: draft.composeClipCount ?? draft.timeline.length,
      composeWorkspaces: (draft.composeWorkspaces ?? [{ id: "compose_1", title: "成片 1", clips: draft.timeline, job: draft.composeJob ?? null }]).map(workspace => ({ ...workspace, clips: workspace.clips.map(normalizeTimelineClip) })),
      bgmName: draft.bgmName,
      bgmUrl: draft.bgmUrl ?? "",
      composeJob: draft.composeJob ?? null,
      activePanel: draft.activePanel as Panel,
      nextNodeNumber: draft.nextNodeNumber,
      hydrated: true,
      revision: nodesChanged ? 1 : 0,
      lastSavedAt: (draft as DraftPayload & { updated_at?: string }).updated_at ?? null,
    });
  },
  saveDraft: async () => {
    const state = get();
    set({ saving: true });
    try {
      const payload: DraftPayload = {
        activePanel: state.activePanel,
        nextNodeNumber: state.nextNodeNumber,
        nodes: state.nodes.map(({ selected: _selected, measured: _measured, ...node }) => node),
        edges: state.edges.map(({ selected: _selected, ...edge }) => edge),
        timeline: state.timeline,
        candidateClips: state.candidateClips,
        composeBatchCount: state.composeBatchCount,
        composeClipCount: state.composeClipCount,
        composeWorkspaces: state.composeWorkspaces,
        bgmName: state.bgmName,
        bgmUrl: state.bgmUrl,
        composeJob: state.composeJob,
      };
      const saved = await persistDraft(state.draftId, payload);
      set({ saving: false, lastSavedAt: (saved as DraftPayload & { updated_at?: string }).updated_at ?? new Date().toISOString() });
    } catch (error) {
      set({ saving: false });
      throw error;
    }
  },
}));

export type { WorkflowState };
