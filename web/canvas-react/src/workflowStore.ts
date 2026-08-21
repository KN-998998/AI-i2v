import { addEdge as addReactFlowEdge, applyEdgeChanges, applyNodeChanges, type Edge, type EdgeChange, type NodeChange } from "@xyflow/react";
import { create } from "zustand";
import { clips, createWorkflowNode, removeNodeAndEdges, reorderById, type ClipLibraryItem, type ComposeJob, type DraftPayload, type NodeKind, type Panel, type TimelineClip, type WorkflowData, type WorkflowNode } from "./model";
import { workflowSeed } from "./seed";
import { fetchCanvasClips, fetchDraft, persistDraft } from "./api";

type WorkflowState = {
  nodes: WorkflowNode[];
  edges: Edge[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  activePanel: Panel;
  timeline: TimelineClip[];
  availableClips: ClipLibraryItem[];
  clipsLoaded: boolean;
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
  loadDraft: () => Promise<void>;
  saveDraft: () => Promise<void>;
};

const protectedNodeIds = new Set(["assets", "prompt", "clips", "output", "sound"]);

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  nodes: workflowSeed.nodes,
  edges: workflowSeed.edges,
  selectedNodeId: "assets",
  selectedEdgeId: null,
  activePanel: "prompt",
  timeline: workflowSeed.timeline,
  availableClips: [],
  clipsLoaded: false,
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
    return {
      nodes,
      edges: removed.size ? state.edges.filter(edge => !removed.has(edge.source) && !removed.has(edge.target)) : state.edges,
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
    return {
      ...next,
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
    const copy = { ...source, id, position: { x: source.position.x + 36, y: source.position.y + 36 }, data: { ...source.data, title: `${source.data.title} 副本` }, selected: true };
    return { nodes: [...state.nodes, copy], nextNodeNumber: state.nextNodeNumber + 1, selectedNodeId: id, selectedEdgeId: null, revision: state.revision + 1 };
  }),
  reorderTimeline: (sourceId, targetId) => set(state => ({ timeline: reorderById(state.timeline, sourceId, targetId), revision: state.revision + 1 })),
  removeTimelineClip: clipId => set(state => ({ timeline: state.timeline.filter(clip => clip.id !== clipId), revision: state.revision + 1 })),
  updateTimelineClip: (clipId, patch) => set(state => ({ timeline: state.timeline.map(clip => clip.id === clipId ? { ...clip, ...patch } : clip), revision: state.revision + 1 })),
  toggleClip: clipId => set(state => {
    const clip = state.availableClips.find(item => item.id === clipId) ?? clips.find(item => item.id === clipId);
    if (!clip) return {};
    const exists = state.timeline.some(item => item.id === clipId);
    return { timeline: exists ? state.timeline.filter(item => item.id !== clipId) : [...state.timeline, clip], revision: state.revision + 1 };
  }),
  loadClipLibrary: async () => {
    const availableClips = await fetchCanvasClips();
    set(state => {
      const seedIds = new Set(clips.map(item => item.id));
      const isUnlinkedSeedTimeline = state.timeline.length > 0 && state.timeline.every(item => seedIds.has(item.id) && !item.sourcePath);
      const timeline = isUnlinkedSeedTimeline && availableClips.length
        ? state.timeline.map((item, index) => availableClips[index] ? { ...availableClips[index] } : item)
        : state.timeline;
      return { availableClips, clipsLoaded: true, timeline, revision: timeline === state.timeline ? state.revision : state.revision + 1 };
    });
  },
  setBgmName: bgmName => set(state => ({ bgmName, revision: state.revision + 1 })),
  setBgm: (bgmName, bgmUrl) => set(state => ({ bgmName, bgmUrl, revision: state.revision + 1 })),
  clearBgm: () => set(state => ({ bgmName: "", bgmUrl: "", revision: state.revision + 1 })),
  setComposeJob: composeJob => set(state => ({ composeJob, revision: state.revision + 1 })),
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
