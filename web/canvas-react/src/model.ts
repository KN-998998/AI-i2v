import type { Edge, Node } from "@xyflow/react";

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
};

export type DraftPayload = {
  activePanel: string;
  nextNodeNumber: number;
  nodes: WorkflowNode[];
  edges: Edge[];
  timeline: TimelineClip[];
  bgmName: string;
  bgmUrl: string;
  composeJob?: ComposeJob | null;
};

export type ComposeJob = {
  job_id: string;
  draft_id?: string;
  status: "running" | "done" | "error";
  timeline_count: number;
  output_url: string | null;
  error: string | null;
};

export type WorkflowNode = Node<WorkflowData, "workflow">;

export type TimelineClip = {
  id: string;
  dish: string;
  label: string;
  tone: string;
  timelineDuration: number;
  status?: "pending" | "generated";
  sourcePath?: string;
  sourceUrl?: string;
  batchId?: string;
  filename?: string;
};

export type ClipLibraryItem = TimelineClip & {
  batchId: string;
  filename: string;
  sourcePath: string;
  sourceUrl: string;
  durationSeconds: number;
};

export type NodeCatalogItem = Pick<WorkflowData, "title" | "status" | "description"> & { kicker: string };

export const nodeCatalog: Record<NodeKind, NodeCatalogItem> = {
  input: { kicker: "INPUT", title: "素材与菜品", status: "已就绪", description: "提供菜品图片、首帧或尾帧素材。" },
  prompt: { kicker: "PROMPT", title: "槽位化提示词", status: "可生成", description: "装配并校验图生视频提示词。" },
  generator: { kicker: "KLING 3.0", title: "3 秒视频片段", status: "待生成", description: "按当前提示词生成视频片段。" },
  output: { kicker: "OUTPUT", title: "成片合成", status: "草稿", description: "先将视频片段合成为无声成片。" },
  sound: { kicker: "SOUND", title: "声音与文字", status: "待配置", description: "在合成视频后添加 BGM、人声与画面文字。" },
  custom: { kicker: "PROCESS", title: "自定义处理", status: "待配置", description: "可扩展的工作流处理节点。" },
};

export const promptL0Options = ["菜品主体·冷食", "菜品主体·热食", "配菜/装饰", "餐具器皿", "桌面/台面", "手部", "厨师上半身", "背景陈设"];

export const clips: TimelineClip[] = [
  { id: "clip_salmon_01", dish: "炙烤三文鱼", label: "平稳推进", tone: "#355e62", timelineDuration: 2.5 },
  { id: "clip_salmon_02", dish: "炙烤三文鱼", label: "小幅弧线", tone: "#4b5d68", timelineDuration: 2.5 },
  { id: "clip_tempura_01", dish: "天妇罗", label: "右向横移", tone: "#665038", timelineDuration: 2.5 },
  { id: "clip_sashimi_01", dish: "刺身拼盘", label: "固定机位", tone: "#4c4265", timelineDuration: 2.5 },
];

export function dataFor(kind: NodeKind): WorkflowData {
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

export const initialNodes: WorkflowNode[] = [
  createWorkflowNode("input", "assets", { x: 24, y: 54 }),
  createWorkflowNode("prompt", "prompt", { x: 286, y: 42 }),
  createWorkflowNode("generator", "clips", { x: 548, y: 54 }),
  createWorkflowNode("output", "output", { x: 810, y: 54 }),
  createWorkflowNode("sound", "sound", { x: 810, y: 282 }),
];

export const initialEdges: Edge[] = [
  { id: "assets-prompt", source: "assets", target: "prompt", type: "smoothstep" },
  { id: "prompt-clips", source: "prompt", target: "clips", type: "smoothstep" },
  { id: "clips-output", source: "clips", target: "output", type: "smoothstep" },
  { id: "output-sound", source: "output", target: "sound", type: "smoothstep" },
];

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

export function reorderById<T extends { id: string }>(items: T[], sourceId: string, targetId: string): T[] {
  const from = items.findIndex(item => item.id === sourceId);
  const to = items.findIndex(item => item.id === targetId);
  if (from < 0 || to < 0 || from === to) return items;
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export function totalTimelineDuration(items: TimelineClip[]): number {
  return items.reduce((sum, clip) => sum + clip.timelineDuration, 0);
}

export function removeNodeAndEdges(nodes: WorkflowNode[], edges: Edge[], nodeId: string) {
  return {
    nodes: nodes.filter(node => node.id !== nodeId),
    edges: edges.filter(edge => edge.source !== nodeId && edge.target !== nodeId),
  };
}
