import type { Edge, Node } from "@xyflow/react";
import { DEFAULT_PROMPT_CONFIG, promptLegacyPatch, type ActionVerb, type PromptConfig } from "./promptAssembler.ts";

export type NodeKind = "input" | "prompt" | "generator" | "output" | "sound" | "custom";
export type Panel = "prompt" | "voice" | "overlay";

export type OverlayPosition = "top" | "upper" | "center" | "bottom";

export type OverlayStyle = {
  fontFamily: "Microsoft YaHei" | "SimHei" | "Arial";
  fontSize: number;
  color: string;
  fontWeight: "normal" | "bold";
  strokeColor: string;
  strokeWidth: number;
  backgroundEnabled: boolean;
  backgroundColor: string;
  backgroundOpacity: number;
};

export type OverlayItem = {
  id: string;
  text: string;
  startSeconds: number;
  endSeconds: number;
  position: OverlayPosition;
  style?: Partial<OverlayStyle>;
};

export const DISH_CATEGORY_OPTIONS = ["正餐", "小吃", "甜品", "水果", "饮品", "其他"] as const;
export type DishCategory = typeof DISH_CATEGORY_OPTIONS[number];

export type WorkflowData = {
  kind: NodeKind;
  title: string;
  description: string;
  status: string;
  dishName?: string;
  foodType?: string;
  dishCategory?: DishCategory;
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
  promptL1ActionLevel?: 1 | 2 | 3 | null;
  promptL1ActionVerb?: ActionVerb | null;
  promptSpeedCurve?: "uniform" | "ease_in" | "ease_out" | null;
  promptSeamlessLoop?: boolean;
  promptEndImageName?: string;
  promptEndImagePreview?: string;
  promptConfig?: PromptConfig;
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
  overlayItems?: OverlayItem[];
  bgmVolume?: string;
};

export type DraftPayload = {
  activePanel: string;
  nextNodeNumber: number;
  nodes: WorkflowNode[];
  edges: Edge[];
  timeline: TimelineClip[];
  candidateClips?: TimelineClip[];
  composeBatchCount?: number;
  composeClipCount?: number;
  composeWorkspaces?: ComposeWorkspace[];
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
  workspace_id?: string;
};

export type ComposeWorkspace = {
  id: string;
  title: string;
  clips: TimelineClip[];
  job: ComposeJob | null;
};

export type WorkflowNode = Node<WorkflowData, "workflow">;

export type TimelineClip = {
  id: string;
  dish: string;
  label: string;
  tone: string;
  timelineDuration: number;
  sourceDurationSeconds?: number;
  sourceStartSeconds?: number;
  sourceEndSeconds?: number;
  dishCategory?: DishCategory;
  status?: "pending" | "generated";
  sourcePath?: string;
  sourceUrl?: string;
  batchId?: string;
  filename?: string;
  generatorNodeId?: string;
};

export type ClipLibraryItem = TimelineClip & {
  /** 旧批次片段才有；新版公共画布片段不依赖 batch_id。 */
  batchId?: string;
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

export const OVERLAY_POSITION_OPTIONS: Array<{ value: OverlayPosition; label: string }> = [
  { value: "top", label: "上方品牌区" },
  { value: "upper", label: "中上钩子区" },
  { value: "center", label: "画面中央" },
  { value: "bottom", label: "底部安全区" },
];

export const DEFAULT_OVERLAY_ITEMS: OverlayItem[] = [
  { id: "overlay_hook", text: "本周限定优惠", startSeconds: 0, endSeconds: 2.5, position: "upper" },
  { id: "overlay_cta", text: "到店即享 · 现在预订", startSeconds: 10.5, endSeconds: 12.5, position: "top" },
];

export const DEFAULT_OVERLAY_STYLE: OverlayStyle = {
  fontFamily: "Microsoft YaHei",
  fontSize: 42,
  color: "#FFFFFF",
  fontWeight: "bold",
  strokeColor: "#000000",
  strokeWidth: 2,
  backgroundEnabled: true,
  backgroundColor: "#111417",
  backgroundOpacity: 0.62,
};

export function overlayStyleFromItem(item: Pick<OverlayItem, "style">): OverlayStyle {
  return { ...DEFAULT_OVERLAY_STYLE, ...item.style, fontSize: clampNumber(item.style?.fontSize, 12, 120, DEFAULT_OVERLAY_STYLE.fontSize), strokeWidth: clampNumber(item.style?.strokeWidth, 0, 12, DEFAULT_OVERLAY_STYLE.strokeWidth), backgroundOpacity: clampNumber(item.style?.backgroundOpacity, 0, 1, DEFAULT_OVERLAY_STYLE.backgroundOpacity) } as OverlayStyle;
}

export function overlayItemsFromData(data: Pick<WorkflowData, "overlayItems" | "overlayMain" | "overlayCta" | "overlayPosition" | "overlayStart" | "overlayEnd">): OverlayItem[] {
  if (data.overlayItems) {
    return data.overlayItems.map(item => ({
      id: item.id,
      text: item.text,
      startSeconds: Math.max(0, Number(item.startSeconds) || 0),
      endSeconds: Math.max(0.1, Number(item.endSeconds) || 0.1),
      position: item.position ?? "upper",
      style: overlayStyleFromItem(item),
    }));
  }
  const mainText = data.overlayMain?.trim() || "";
  const ctaText = data.overlayCta?.trim() || "";
  const start = Math.max(0, Number.parseFloat(data.overlayStart ?? "0") || 0);
  const end = Math.max(start + 0.1, Number.parseFloat(data.overlayEnd ?? "2.5") || 2.5);
  const legacyPosition = data.overlayPosition?.includes("顶部") ? "top" : data.overlayPosition?.includes("中上") ? "upper" : data.overlayPosition?.includes("中央") ? "center" : "bottom";
  const items: OverlayItem[] = [];
  if (mainText) items.push({ id: "overlay_main", text: mainText, startSeconds: start, endSeconds: end, position: legacyPosition, style: { ...DEFAULT_OVERLAY_STYLE } });
  if (ctaText && ctaText !== mainText) items.push({ id: "overlay_cta", text: ctaText, startSeconds: Math.max(0, end - 2), endSeconds: end, position: "top", style: { ...DEFAULT_OVERLAY_STYLE } });
  return items;
}

export const promptL0Options = ["菜品主体·冷食", "菜品主体·热食", "配菜／装饰", "餐具器皿", "桌面／台面", "手部", "厨师上半身", "背景陈设"];

export const clips: TimelineClip[] = [
  { id: "clip_salmon_01", dish: "炙烤三文鱼", label: "平稳推进", tone: "#355e62", timelineDuration: 2.5, dishCategory: "正餐" },
  { id: "clip_salmon_02", dish: "炙烤三文鱼", label: "小幅弧线", tone: "#4b5d68", timelineDuration: 2.5, dishCategory: "正餐" },
  { id: "clip_tempura_01", dish: "天妇罗", label: "右向横移", tone: "#665038", timelineDuration: 2.5, dishCategory: "小吃" },
  { id: "clip_sashimi_01", dish: "刺身拼盘", label: "固定机位", tone: "#4c4265", timelineDuration: 2.5, dishCategory: "正餐" },
];

export function dataFor(kind: NodeKind): WorkflowData {
  const base = { kind, ...nodeCatalog[kind] };
  if (kind === "input") return { ...base, dishName: "炙烤三文鱼", foodType: "热食", dishCategory: "正餐", assetMode: "单图模式", imageName: "当前素材" };
  if (kind === "prompt") return { ...base, promptConfig: DEFAULT_PROMPT_CONFIG, ...promptLegacyPatch(DEFAULT_PROMPT_CONFIG) };
  if (kind === "generator") return { ...base, duration: "3s", resolution: "1080p", audio: "无声", storyboard: "单分镜" };
  if (kind === "output") return { ...base, outputTarget: "5-6 道菜", outputDuration: "12-15s", outputAspect: "9:16" };
  if (kind === "sound") return { ...base, voiceText: "本周到店即可领取限定优惠，欢迎来店品尝。", voiceName: "女声 · 温暖自然", voiceVolume: "85", bgmVolume: "30", overlayMain: "本周限定优惠", overlayCta: "到店即享 · 现在预订", overlayPosition: "中上钩子区", overlayStart: "0.0s", overlayEnd: "2.5s", overlayItems: DEFAULT_OVERLAY_ITEMS.map(item => ({ ...item })) };
  return base;
}

export function createWorkflowNode(kind: NodeKind, id: string, position: { x: number; y: number }): WorkflowNode {
  return { id, type: "workflow", position, data: dataFor(kind) };
}

export function createPendingGeneratorClip(nodeId: string, _nodeNumber: number, dish = "待配置菜品", dishCategory: DishCategory = "正餐"): TimelineClip {
  return {
    id: `${nodeId}_clip`,
    dish,
    label: "生成任务",
    tone: "#355e62",
    timelineDuration: 2.5,
    sourceDurationSeconds: 3,
    sourceStartSeconds: 0.5,
    sourceEndSeconds: 3,
    dishCategory,
    status: "pending",
    generatorNodeId: nodeId,
  };
}

export function normalizeTimelineClip<T extends TimelineClip>(clip: T): T {
  const sourceDuration = Math.max(0.1, Number(clip.sourceDurationSeconds ?? 3) || 3);
  const start = clampNumber(clip.sourceStartSeconds, 0, Math.max(0, sourceDuration - 0.1), Math.min(0.5, Math.max(0, sourceDuration - 0.1)));
  const end = clampNumber(clip.sourceEndSeconds, start + 0.1, sourceDuration, Math.min(sourceDuration, start + Math.max(0.1, clip.timelineDuration || 2.5)));
  return { ...clip, sourceDurationSeconds: sourceDuration, sourceStartSeconds: start, sourceEndSeconds: end, timelineDuration: Math.max(0.1, end - start) };
}

function clampNumber(value: number | undefined, min: number, max: number, fallback: number): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.min(max, Math.max(min, numeric)) : fallback;
}

const fruitKeywords = ["蜜瓜", "草莓", "西瓜", "芒果", "葡萄", "蓝莓", "树莓", "樱桃", "桃", "梨", "苹果", "橙", "柚", "柠檬"];
const dessertKeywords = ["蛋糕", "布丁", "冰淇淋", "甜点", "甜品", "慕斯", "奶油", "铜锣烧", "抹茶", "芝士"];

export function inferDishCategory(dish: string): DishCategory {
  const normalized = dish.trim().toLowerCase();
  if (fruitKeywords.some(keyword => normalized.includes(keyword))) return "水果";
  if (dessertKeywords.some(keyword => normalized.includes(keyword))) return "甜品";
  return "其他";
}

export function resolveDishCategory(clip: Pick<TimelineClip, "dish" | "dishCategory">): DishCategory {
  return clip.dishCategory && DISH_CATEGORY_OPTIONS.includes(clip.dishCategory) ? clip.dishCategory : inferDishCategory(clip.dish);
}

export function randomizeClipSelection(items: TimelineClip[], clipCount: number, random = Math.random): TimelineClip[] {
  const available = items.filter(clip => clip.sourcePath).filter((clip, index, list) => list.findIndex(item => item.id === clip.id) === index);
  const count = Math.max(0, Math.round(clipCount));
  if (count === 0 || available.length === 0) return [];
  const special = available.filter(clip => ["甜品", "水果"].includes(resolveDishCategory(clip)));
  const ordinary = available.filter(clip => !["甜品", "水果"].includes(resolveDishCategory(clip)));
  const shuffledOrdinary = shuffle(ordinary, random);
  const shuffledSpecial = shuffle(special, random);
  if (count === 1) return [shuffledSpecial[0] ?? shuffledOrdinary[0]].filter((clip): clip is TimelineClip => Boolean(clip));

  const ordinaryTarget = shuffledSpecial.length ? count - 1 : count;
  const selected = shuffledOrdinary.slice(0, Math.min(ordinaryTarget, shuffledOrdinary.length));
  if (shuffledSpecial[0] && selected.length < count) selected.push(shuffledSpecial[0]);
  return selected;
}

function shuffle<T>(items: T[], random: () => number): T[] {
  const next = [...items];
  for (let index = next.length - 1; index > 0; index -= 1) {
    const target = Math.floor(random() * (index + 1));
    [next[index], next[target]] = [next[target], next[index]];
  }
  return next;
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
