import { addEdge as addReactFlowEdge, applyEdgeChanges, applyNodeChanges, type Edge, type EdgeChange, type Node, type NodeChange } from "@xyflow/react";
import { create } from "zustand";

export type NodeKind = "input" | "prompt" | "generator" | "output" | "sound" | "custom";
export type Panel = "prompt" | "voice" | "overlay";

export type WorkflowData = {
  kind: NodeKind;
  title: string;
  description: string;
  status: string;
  dishName?: string;
  foodType?: string;
  assetMode?: string;
  imageName?: string;
  imagePreview?: string;
  duration?: string;
  resolution?: string;
  audio?: string;
  storyboard?: string;
  promptMode?: string;
  promptL0?: string[];
  promptMotion?: string;
  promptAmplitude?: string;
  promptL1?: string;
  promptL2Type1?: string;
  promptL2Target1?: string;
  promptL2Type2?: string;
  promptL2Target2?: string;
  outputTarget?: string;
  outputDuration?: string;
  outputAspect?: string;
  voiceText?: string;
  voiceName?: string;
  voiceVolume?: string;
  overlayMain?: string;
  overlayCta?: string;
  overlayPosition?: string;
  overlayStart?: string;
  overlayEnd?: string;
  [key: string]: unknown;
};

export type WorkflowNode = Node<WorkflowData, "workflow">;

export type TimelineClip = {
  id: string;
  dish: string;
  label: string;
  tone: string;
  timelineDuration: number;
};

export const nodeCatalog: Record<NodeKind, Pick<WorkflowData, "title" | "status" | "description"> & { kicker: string }> = {
  input: { kicker: "INPUT", title: "素材与菜品", status: "已就绪", description: "提供菜品图片、首帧或尾帧素材。" },
  prompt: { kicker: "PROMPT", title: "槽位化提示词", status: "可生成", description: "装配并校验图生视频提示词。" },
  generator: { kicker: "KLING 3.0", title: "3 秒视频片段", status: "待生成", description: "按当前提示词生成视频片段。" },
  output: { kicker: "OUTPUT", title: "成片合成", status: "草稿", description: "先将视频片段合成为无声成片。" },
  sound: { kicker: "SOUND", title: "声音与文字", status: "待配置", description: "在合成视频后添加 BGM、人声与画面文字。" },
  custom: { kicker: "PROCESS", title: "自定义处理", status: "待配置", description: "可扩展的工作流处理节点。" },
};

const clips: TimelineClip[] = [
  { id: "clip_salmon_01", dish: "炙烤三文鱼", label: "平稳推进", tone: "#355e62", timelineDuration: 2.5 },
  { id: "clip_salmon_02", dish: "炙烤三文鱼", label: "小幅弧线", tone: "#4b5d68", timelineDuration: 2.5 },
  { id: "clip_tempura_01", dish: "天妇罗", label: "右向横移", tone: "#665038", timelineDuration: 2.5 },
  { id: "clip_sashimi_01", dish: "刺身拼盘", label: "固定机位", tone: "#4c4265", timelineDuration: 2.5 },
];

function dataFor(kind: NodeKind): WorkflowData {
  const base = { kind, ...nodeCatalog[kind] };
  if (kind === "input") return { ...base, dishName: "炙烤三文鱼", foodType: "热食", assetMode: "单图模式", imageName: "当前素材" };
  if (kind === "prompt") return { ...base, promptMode: "单图模式", promptL0: ["菜品主体·热食", "配菜/装饰", "餐具器皿", "桌面/台面", "背景陈设"], promptMotion: "小角度顺时针环绕", promptAmplitude: "极轻微（约 8%）", promptL1: "菜品主体·热食", promptL2Type1: "高光滑移", promptL2Target1: "菜品", promptL2Type2: "（无）", promptL2Target2: "菜品" };
  if (kind === "generator") return { ...base, duration: "3s", resolution: "1080p", audio: "无声", storyboard: "单分镜" };
  if (kind === "output") return { ...base, outputTarget: "5-6 道菜", outputDuration: "12-15s", outputAspect: "9:16" };
  if (kind === "sound") return { ...base, voiceText: "本周到店即可领取限定优惠，欢迎来店品尝。", voiceName: "女声 · 温暖自然", voiceVolume: "85", overlayMain: "本周限定优惠", overlayCta: "到店即享 · 现在预订", overlayPosition: "底部安全区", overlayStart: "0.0s", overlayEnd: "2.5s" };
  return base;
}

export function createWorkflowNode(kind: NodeKind, id: string, position: { x: number; y: number }): WorkflowNode {
  return { id, type: "workflow", position, data: dataFor(kind) };
}

const initialNodes: WorkflowNode[] = [
  createWorkflowNode("input", "assets", { x: 24, y: 54 }),
  createWorkflowNode("prompt", "prompt", { x: 286, y: 42 }),
  createWorkflowNode("generator", "clips", { x: 548, y: 54 }),
  createWorkflowNode("output", "output", { x: 810, y: 54 }),
  createWorkflowNode("sound", "sound", { x: 810, y: 282 }),
];

const initialEdges: Edge[] = [
  { id: "assets-prompt", source: "assets", target: "prompt", type: "smoothstep" },
  { id: "prompt-clips", source: "prompt", target: "clips", type: "smoothstep" },
  { id: "clips-output", source: "clips", target: "output", type: "smoothstep" },
  { id: "output-sound", source: "output", target: "sound", type: "smoothstep" },
];

type WorkflowState = {
  nodes: WorkflowNode[];
  edges: Edge[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  activePanel: Panel;
  timeline: TimelineClip[];
  selectedClipIds: string[];
  bgmName: string;
  nextNodeNumber: number;
  setNodes: (changes: NodeChange<WorkflowNode>[]) => void;
  setEdges: (changes: EdgeChange[]) => void;
  addEdge: (edge: Edge) => void;
  setSelection: (nodeId: string | null, edgeId?: string | null) => void;
  setActivePanel: (panel: Panel) => void;
  updateNodeData: (nodeId: string, patch: Partial<WorkflowData>) => void;
  addNode: (kind: NodeKind) => void;
  deleteSelected: () => void;
  duplicateSelected: () => void;
  reorderTimeline: (sourceId: string, targetId: string) => void;
  removeTimelineClip: (clipId: string) => void;
  toggleClip: (clipId: string) => void;
  setBgmName: (name: string) => void;
};

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  nodes: initialNodes,
  edges: initialEdges,
  selectedNodeId: "assets",
  selectedEdgeId: null,
  activePanel: "prompt",
  timeline: [clips[0], clips[2], clips[3]],
  selectedClipIds: [clips[0].id],
  bgmName: "默认 BGM",
  nextNodeNumber: 1,
  setNodes: changes => set(state => ({ nodes: applyNodeChanges(changes, state.nodes) as WorkflowNode[] })),
  setEdges: changes => set(state => ({ edges: applyEdgeChanges(changes, state.edges) })),
  addEdge: edge => set(state => ({ edges: addReactFlowEdge(edge, state.edges) })),
  setSelection: (nodeId, edgeId = null) => set({ selectedNodeId: nodeId, selectedEdgeId: edgeId }),
  setActivePanel: activePanel => set({ activePanel }),
  updateNodeData: (nodeId, patch) => set(state => ({ nodes: state.nodes.map(node => node.id === nodeId ? { ...node, data: { ...node.data, ...patch } } : node) })),
  addNode: kind => set(state => {
    const id = `node_${kind}_${state.nextNodeNumber}`;
    const index = state.nextNodeNumber - 1;
    return {
      nodes: [...state.nodes, createWorkflowNode(kind, id, { x: 24 + (index % 3) * 260, y: 520 + Math.floor(index / 3) * 220 })],
      nextNodeNumber: state.nextNodeNumber + 1,
      selectedNodeId: id,
      selectedEdgeId: null,
    };
  }),
  deleteSelected: () => set(state => {
    if (state.selectedEdgeId) return { edges: state.edges.filter(edge => edge.id !== state.selectedEdgeId), selectedEdgeId: null };
    if (!state.selectedNodeId || ["assets", "prompt", "clips", "output", "sound"].includes(state.selectedNodeId)) return {};
    return { nodes: state.nodes.filter(node => node.id !== state.selectedNodeId), edges: state.edges.filter(edge => edge.source !== state.selectedNodeId && edge.target !== state.selectedNodeId), selectedNodeId: null };
  }),
  duplicateSelected: () => set(state => {
    const source = state.nodes.find(node => node.id === state.selectedNodeId);
    if (!source) return {};
    const id = `node_${source.data.kind}_${state.nextNodeNumber}`;
    const copy = { ...source, id, position: { x: source.position.x + 36, y: source.position.y + 36 }, data: { ...source.data, title: `${source.data.title} 副本` } };
    return { nodes: [...state.nodes, copy], nextNodeNumber: state.nextNodeNumber + 1, selectedNodeId: id, selectedEdgeId: null };
  }),
  reorderTimeline: (sourceId, targetId) => set(state => {
    const from = state.timeline.findIndex(clip => clip.id === sourceId);
    const to = state.timeline.findIndex(clip => clip.id === targetId);
    if (from < 0 || to < 0 || from === to) return {};
    const timeline = [...state.timeline];
    const [item] = timeline.splice(from, 1);
    timeline.splice(to, 0, item);
    return { timeline };
  }),
  removeTimelineClip: clipId => set(state => ({ timeline: state.timeline.filter(clip => clip.id !== clipId), selectedClipIds: state.selectedClipIds.filter(id => id !== clipId) })),
  toggleClip: clipId => set(state => ({ selectedClipIds: state.selectedClipIds.includes(clipId) ? state.selectedClipIds.filter(id => id !== clipId) : [...state.selectedClipIds, clipId] })),
  setBgmName: bgmName => set({ bgmName }),
}));

export function connectWouldCycle(edges: Edge[], source: string, target: string): boolean {
  const visited = new Set<string>([target]);
  const pending = [target];
  while (pending.length) {
    const current = pending.pop();
    if (current === source) return true;
    edges.filter(edge => edge.source === current).forEach(edge => {
      if (!visited.has(edge.target)) {
        visited.add(edge.target);
        pending.push(edge.target);
      }
    });
  }
  return false;
}

export { clips };
