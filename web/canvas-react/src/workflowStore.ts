import { addEdge as addReactFlowEdge, applyEdgeChanges, applyNodeChanges, type Edge, type EdgeChange, type NodeChange } from "@xyflow/react";
import { create } from "zustand";
import { clips, createWorkflowNode, removeNodeAndEdges, reorderById, type ClipLibraryItem, type ComposeJob, type ComposeWorkspace, type DraftPayload, type NodeKind, type Panel, type TimelineClip, type WorkflowData, type WorkflowNode } from "./model";
import { workflowSeed } from "./seed";
import { fetchCanvasClips, fetchDraft, persistDraft } from "./api";

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
  addNode: (kind: NodeKind) => void;
  deleteNode: (nodeId: string) => void;
  duplicateNode: (nodeId: string) => void;
  deleteSelected: () => void;
  duplicateSelected: () => void;
  reorderTimeline: (sourceId: string, targetId: string) => void;
  removeTimelineClip: (clipId: string) => void;
  updateTimelineClip: (clipId: string, patch: Partial<TimelineClip>) => void;
  toggleClip: (clipId: string) => void;
  loadClipLibrary: () => Promise<void>;
  setBgmName: (name: string) => void;
  setBgm: (name: string, url: string) => void;
  clearBgm: () => void;
  setComposeJob: (job: ComposeJob | null) => void;
  setComposeBatchCount: (count: number) => void;
  setComposeClipCount: (count: number) => void;
  randomizeComposeWorkspaces: () => void;
  reorderWorkspace: (workspaceId: string, sourceId: string, targetId: string) => void;
  removeWorkspaceClip: (workspaceId: string, clipId: string) => void;
  addWorkspaceClip: (workspaceId: string, clipId: string) => void;
  setWorkspaceJob: (workspaceId: string, job: ComposeJob | null) => void;
  loadDraft: () => Promise<void>;
  saveDraft: () => Promise<void>;
};

const protectedNodeIds = new Set(["assets", "prompt", "clips", "output", "sound"]);

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
      && clip.status === other.status
      && clip.sourcePath === other.sourcePath
      && clip.sourceUrl === other.sourceUrl
      && clip.batchId === other.batchId
      && clip.filename === other.filename
      && clip.generatorNodeId === other.generatorNodeId;
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
  updateNodeData: (nodeId, patch) => set(state => ({ nodes: state.nodes.map(node => node.id === nodeId ? { ...node, data: { ...node.data, ...patch } } : node), revision: state.revision + 1 })),
  addNode: kind => set(state => {
    const id = `node_${kind}_${state.nextNodeNumber}`;
    const index = state.nextNodeNumber - 1;
    const generatedClip = kind === "generator"
      ? { id: `${id}_clip`, dish: `待配置片段 ${state.nextNodeNumber}`, label: "待生成", tone: "#355e62", timelineDuration: 2.5, status: "pending" as const, generatorNodeId: id }
      : null;
    return {
      nodes: [...state.nodes, createWorkflowNode(kind, id, { x: 24 + (index % 3) * 260, y: 520 + Math.floor(index / 3) * 220 })],
      candidateClips: generatedClip ? [...state.candidateClips, generatedClip] : state.candidateClips,
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
      data: { ...source.data, title: `${source.data.title} 副本` },
      selected: true,
    };
    const generatedClip = source.data.kind === "generator"
      ? { id: `${id}_clip`, dish: `待配置片段 ${state.nextNodeNumber}`, label: "待生成", tone: "#355e62", timelineDuration: 2.5, status: "pending" as const, generatorNodeId: id }
      : null;
    return {
      nodes: [...state.nodes, copy],
      candidateClips: generatedClip ? [...state.candidateClips, generatedClip] : state.candidateClips,
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
    const copy = { ...source, id, position: { x: source.position.x + 36, y: source.position.y + 36 }, data: { ...source.data, title: `${source.data.title} 副本` }, selected: true };
    const generatedClip = source.data.kind === "generator"
      ? { id: `${id}_clip`, dish: `待配置片段 ${state.nextNodeNumber}`, label: "待生成", tone: "#355e62", timelineDuration: 2.5, status: "pending" as const, generatorNodeId: id }
      : null;
    return { nodes: [...state.nodes, copy], candidateClips: generatedClip ? [...state.candidateClips, generatedClip] : state.candidateClips, nextNodeNumber: state.nextNodeNumber + 1, selectedNodeId: id, selectedEdgeId: null, revision: state.revision + 1 };
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
    const timeline = state.timeline.map(clip => clip.id === clipId ? { ...clip, ...patch } : clip);
    return { timeline, composeWorkspaces: syncPrimaryWorkspace(state.composeWorkspaces, timeline), revision: state.revision + 1 };
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
      const availableClips = await fetchCanvasClips();
      set(state => {
        const seedIds = new Set(clips.map(item => item.id));
        const isUnlinkedSeedTimeline = state.timeline.length > 0 && state.timeline.every(item => seedIds.has(item.id) && !item.sourcePath);
        const timeline = isUnlinkedSeedTimeline && availableClips.length
          ? state.timeline.map((item, index) => availableClips[index] ? { ...availableClips[index] } : item)
          : state.timeline;
        const isUnlinkedSeedCandidates = state.candidateClips.length > 0 && state.candidateClips.every(item => seedIds.has(item.id) && !item.sourcePath);
        const candidateClips = isUnlinkedSeedCandidates && availableClips.length
          ? availableClips.map(item => ({ ...item }))
          : [...state.candidateClips, ...availableClips.filter(item => !state.candidateClips.some(existing => existing.id === item.id))];
        const timelineChanged = !sameClipList(timeline, state.timeline);
        const candidateClipsChanged = !sameClipList(candidateClips, state.candidateClips);
        const workspaces = timelineChanged ? syncPrimaryWorkspace(state.composeWorkspaces, timeline) : state.composeWorkspaces;
        return {
          availableClips,
          clipsLoaded: true,
          clipsLastLoadedAt: new Date().toISOString(),
          clipsLoadError: null,
          timeline,
          candidateClips,
          composeWorkspaces: workspaces,
          revision: timelineChanged || candidateClipsChanged ? state.revision + 1 : state.revision,
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
    const count = Math.min(state.composeClipCount, pool.length);
    const workspaces = state.composeWorkspaces.map(workspace => {
      const shuffled = [...pool].sort(() => Math.random() - 0.5);
      return { ...workspace, clips: shuffled.slice(0, count), job: null };
    });
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
    set({
      nodes: draft.nodes,
      edges: draft.edges,
      timeline: draft.timeline,
      candidateClips: draft.candidateClips ?? draft.timeline,
      composeBatchCount: draft.composeBatchCount ?? 1,
      composeClipCount: draft.composeClipCount ?? draft.timeline.length,
      composeWorkspaces: draft.composeWorkspaces ?? [{ id: "compose_1", title: "成片 1", clips: draft.timeline, job: draft.composeJob ?? null }],
      bgmName: draft.bgmName,
      bgmUrl: draft.bgmUrl ?? "",
      composeJob: draft.composeJob ?? null,
      activePanel: draft.activePanel as Panel,
      nextNodeNumber: draft.nextNodeNumber,
      hydrated: true,
      revision: 0,
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
