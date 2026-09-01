import type { Edge, Node } from "@xyflow/react";
import { DEFAULT_PROMPT_CONFIG, promptLegacyPatch, type ActionVerb, type PromptConfig } from "./promptAssembler.ts";

export type NodeKind = "input" | "image_process" | "prompt" | "generator" | "output" | "sound" | "custom";
export type Panel = "prompt" | "voice" | "overlay";

export type OverlayPosition = "top" | "upper" | "center" | "bottom" | "custom";
export type OverlayAnimation = "static" | "typewriter";

export const OVERLAY_FONT_OPTIONS = ["Microsoft YaHei", "SimHei", "KaiTi", "FangSong", "DengXian", "Arial", "Arial Black"] as const;
export type OverlayFontFamily = typeof OVERLAY_FONT_OPTIONS[number];

export type OverlayStyle = {
  fontFamily: OverlayFontFamily;
  fontSize: number;
  textBoxWidth: number;
  singleLine: boolean;
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
  enabled?: boolean;
  /** Runtime-only marker for the counterpart generated when a track is independent. */
  placeholder?: boolean;
  startSeconds: number;
  endSeconds: number;
  position: OverlayPosition;
  /** Normalized text center coordinates. Omitted values use the legacy position fallback. */
  x?: number;
  y?: number;
  animation?: OverlayAnimation;
  syncVoiceId?: string;
  style?: Partial<OverlayStyle>;
};

export type VoiceItem = {
  id: string;
  text: string;
  enabled?: boolean;
  /** Runtime-only marker for the counterpart generated when a track is independent. */
  placeholder?: boolean;
  startSeconds: number;
  endSeconds: number;
  provider?: string;
  model?: string;
  voiceId?: string;
  voiceName?: string;
  volume?: number;
};

export type SoundConfig = {
  voiceText?: string;
  voiceName?: string;
  voiceVolume?: string;
  voiceItems?: VoiceItem[];
  overlayMain?: string;
  overlayCta?: string;
  overlayPosition?: string;
  overlayStart?: string;
  overlayEnd?: string;
  overlayItems?: OverlayItem[];
  bgmName: string;
  bgmUrl: string;
  bgmVolume?: string;
};

export type CaptionSegment = {
  id: string;
  overlay: OverlayItem;
  voice: VoiceItem;
};

export type CaptionTiming = {
  startSeconds: number;
  endSeconds: number;
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
  sourceLibraryCategory?: string;
  sourceLibraryPath?: string;
  assetMode?: string;
  imageName?: string;
  imagePreview?: string;
  assetAnalysis?: MediaAnalysis;
  backgroundTemplateId?: string;
  backgroundTemplateName?: string;
  backgroundPreview?: string;
  backgroundBlur?: number;
  backgroundBrightness?: number;
  subjectScale?: number;
  subjectX?: number;
  subjectY?: number;
  processedImageName?: string;
  processedImagePreview?: string;
  processedImageAnalysis?: MediaAnalysis;
  imageProcessingJobId?: string;
  duration?: string;
  resolution?: string;
  audio?: string;
  storyboard?: string;
  promptMode?: string;
  promptL0?: string[];
  promptMotion?: string;
  promptAmplitude?: string;
  promptShotSize?: string;
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
  voiceItems?: VoiceItem[];
  overlayMain?: string;
  overlayCta?: string;
  overlayPosition?: string;
  overlayStart?: string;
  overlayEnd?: string;
  overlayItems?: OverlayItem[];
  bgmVolume?: string;
};

export function soundConfigFromData(
  data: Pick<WorkflowData, "voiceText" | "voiceName" | "voiceVolume" | "voiceItems" | "overlayMain" | "overlayCta" | "overlayPosition" | "overlayStart" | "overlayEnd" | "overlayItems" | "bgmVolume">,
  bgmName = "",
  bgmUrl = "",
): SoundConfig {
  const config: SoundConfig = { bgmName, bgmUrl };
  if (data.voiceText !== undefined) config.voiceText = data.voiceText;
  if (data.voiceName !== undefined) config.voiceName = data.voiceName;
  if (data.voiceVolume !== undefined) config.voiceVolume = data.voiceVolume;
  if (data.voiceItems !== undefined) config.voiceItems = data.voiceItems.map(item => ({ ...item }));
  if (data.overlayMain !== undefined) config.overlayMain = data.overlayMain;
  if (data.overlayCta !== undefined) config.overlayCta = data.overlayCta;
  if (data.overlayPosition !== undefined) config.overlayPosition = data.overlayPosition;
  if (data.overlayStart !== undefined) config.overlayStart = data.overlayStart;
  if (data.overlayEnd !== undefined) config.overlayEnd = data.overlayEnd;
  if (data.overlayItems !== undefined) config.overlayItems = data.overlayItems.map(item => ({ ...item, style: item.style ? { ...item.style } : undefined }));
  if (data.bgmVolume !== undefined) config.bgmVolume = data.bgmVolume;
  return config;
}

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
  activeComposeWorkspaceId?: string | null;
  bgmName: string;
  bgmUrl: string;
  composeJob?: ComposeJob | null;
  assetLibraryPlan?: AssetLibraryPlan | null;
};

export type ComposeJob = {
  job_id: string;
  draft_id?: string;
  status: "running" | "done" | "error";
  timeline_count: number;
  output_url: string | null;
  error: string | null;
  workspace_id?: string;
  include_sound?: boolean;
  voice_timings?: Record<string, CaptionTiming>;
};

export type ComposeWorkspace = {
  id: string;
  title: string;
  clips: TimelineClip[];
  /** The silent assembly generated in step 5. */
  job: ComposeJob | null;
  /** The sound-and-caption render generated for this specific workspace. */
  finalJob?: ComposeJob | null;
  /** Sound, captions, and BGM are configured independently per composition. */
  soundConfig?: SoundConfig;
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
  trimConfirmed?: boolean;
  dishCategory?: DishCategory;
  status?: "pending" | "generated";
  sourcePath?: string;
  sourceUrl?: string;
  previewUrl?: string;
  filename?: string;
  generatorNodeId?: string;
  generationJobId?: string;
  qualityScore?: number;
  qualityLabel?: "good" | "warning" | "reject";
  qualityWarnings?: string[];
  analysisMode?: string;
};

/**
 * The persisted node label is only a snapshot. Resolve it from the actual
 * clip reference whenever a draft or the local clip library is loaded.
 */
export function resolveGeneratorNodeStatus(
  currentStatus: string,
  clip?: Pick<TimelineClip, "status" | "sourcePath">,
): string {
  if (clip?.sourcePath) return "已生成";
  if (clip?.status === "pending") return "生成中";
  return ["生成中", "待关联真实文件", "已生成"].includes(currentStatus)
    ? "待生成"
    : currentStatus;
}

export type MediaAnalysis = {
  kind: "image" | "video";
  analysisMode: string;
  qualityScore: number;
  qualityLabel: "good" | "warning" | "reject";
  qualityWarnings: string[];
  category?: DishCategory;
  width?: number;
  height?: number;
  durationSeconds?: number;
  fps?: number;
  semanticReview?: string;
};

export type GenerationJob = {
  job_id: string;
  draft_id?: string;
  node_id: string;
  status: "queued" | "running" | "done" | "error";
  stage?: string;
  task_id?: string | null;
  clip?: TimelineClip | null;
  error?: string | null;
};

export type ImageProcessingJob = {
  job_id: string;
  draft_id?: string;
  node_id: string;
  status: "queued" | "running" | "done" | "error";
  stage?: string;
  result_url?: string | null;
  result_name?: string | null;
  cutout_name?: string | null;
  analysis?: MediaAnalysis | null;
  error?: string | null;
};

export type BackgroundTemplate = {
  id: string;
  name: string;
  url: string;
  source: "local";
};

export type AssetLibraryPlanItem = {
  dishName: string;
  displayName?: string;
  sourceCategory: string;
  dishCategory: string;
  foodType: string;
  imageName: string;
  imagePreview: string;
  sourcePath: string;
  storedName: string;
  background: BackgroundTemplate;
  reviewRequired?: boolean;
  classificationReason?: string;
  categoryCandidates?: string[];
  suggestedCategory?: string;
  sourceFolderCount?: number;
  sourceNames?: string[];
};

export type AssetLibraryReviewItem = {
  dishName: string;
  displayName?: string;
  sourceCategory: string;
  classificationReason: string;
  categoryCandidates: string[];
  suggestedCategory: string;
  foodType?: "冷食" | "热食" | null;
  folderCount?: number;
  sourceNames?: string[];
};

export type AssetLibraryPlan = {
  assetRoot: string;
  backgroundRoot: string;
  selected: AssetLibraryPlanItem[];
  warnings: string[];
  categoryCounts: Record<string, number>;
  reviewItems?: AssetLibraryReviewItem[];
  classificationMode?: "qwen" | "local" | "local_fallback" | "manual_rules";
  classificationWarning?: string | null;
};

export type ClipLibraryItem = TimelineClip & {
  filename: string;
  sourcePath: string;
  sourceUrl: string;
  previewUrl?: string;
  durationSeconds: number;
};

export type NodeCatalogItem = Pick<WorkflowData, "title" | "status" | "description"> & { kicker: string };

export const nodeCatalog: Record<NodeKind, NodeCatalogItem> = {
  input: { kicker: "INPUT", title: "素材与菜品", status: "已就绪", description: "提供菜品图片、首帧或尾帧素材。" },
  image_process: { kicker: "IMAGE PROCESS", title: "图片处理", status: "待处理", description: "商品抠图、背景模板合成并输出视频首帧。" },
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
  { value: "custom", label: "自定义位置" },
];

export const DEFAULT_OVERLAY_ITEMS: OverlayItem[] = [
  { id: "overlay_hook", text: "本周限定优惠", startSeconds: 0, endSeconds: 2.5, position: "custom", x: 0.5, y: 0.5 },
  { id: "overlay_cta", text: "到店即享 · 现在预订", startSeconds: 10.5, endSeconds: 12.5, position: "custom", x: 0.5, y: 0.5 },
];

export const DEFAULT_OVERLAY_STYLE: OverlayStyle = {
  fontFamily: "Microsoft YaHei",
  fontSize: 42,
  textBoxWidth: 0.84,
  singleLine: true,
  color: "#FFFFFF",
  fontWeight: "bold",
  strokeColor: "#000000",
  strokeWidth: 2,
  backgroundEnabled: true,
  backgroundColor: "#111417",
  backgroundOpacity: 0.62,
};

export function overlayStyleFromItem(item: Pick<OverlayItem, "style">): OverlayStyle {
  return { ...DEFAULT_OVERLAY_STYLE, ...item.style, fontSize: clampNumber(item.style?.fontSize, 12, 120, DEFAULT_OVERLAY_STYLE.fontSize), textBoxWidth: clampNumber(item.style?.textBoxWidth, 0.3, 0.95, DEFAULT_OVERLAY_STYLE.textBoxWidth), singleLine: item.style?.singleLine ?? DEFAULT_OVERLAY_STYLE.singleLine, strokeWidth: clampNumber(item.style?.strokeWidth, 0, 12, DEFAULT_OVERLAY_STYLE.strokeWidth), backgroundOpacity: clampNumber(item.style?.backgroundOpacity, 0, 1, DEFAULT_OVERLAY_STYLE.backgroundOpacity) } as OverlayStyle;
}

export function overlayPositionCoordinates(position: OverlayPosition): { x: number; y: number } {
  if (position === "top") return { x: 0.5, y: 0.1 };
  if (position === "upper") return { x: 0.5, y: 0.3 };
  if (position === "bottom") return { x: 0.5, y: 0.9 };
  return { x: 0.5, y: 0.5 };
}

export function overlayCoordinatesFromItem(item: Pick<OverlayItem, "position" | "x" | "y">): { x: number; y: number } {
  const fallback = overlayPositionCoordinates(item.position);
  return {
    x: clampNumber(item.x, 0.05, 0.95, fallback.x),
    y: clampNumber(item.y, 0.05, 0.95, fallback.y),
  };
}

export function overlayItemsFromData(data: Pick<WorkflowData, "overlayItems" | "overlayMain" | "overlayCta" | "overlayPosition" | "overlayStart" | "overlayEnd">): OverlayItem[] {
  if (data.overlayItems) {
    return uniqueById(data.overlayItems.map(item => ({
      id: item.id,
      text: item.text,
      enabled: item.enabled !== false,
      placeholder: item.placeholder === true || item.id.startsWith("overlay_for_"),
      startSeconds: Math.max(0, Number(item.startSeconds) || 0),
      endSeconds: Math.max(0.1, Number(item.endSeconds) || 0.1),
      position: item.position ?? "upper",
      ...overlayCoordinatesFromItem({ position: item.position ?? "upper", x: item.x, y: item.y }),
      animation: item.animation === "typewriter" ? "typewriter" : "static",
      syncVoiceId: item.syncVoiceId?.startsWith("voice_for_") ? "" : item.syncVoiceId,
      style: overlayStyleFromItem(item),
    })));
  }
  const mainText = data.overlayMain?.trim() || "";
  const ctaText = data.overlayCta?.trim() || "";
  const start = Math.max(0, Number.parseFloat(data.overlayStart ?? "0") || 0);
  const end = Math.max(start + 0.1, Number.parseFloat(data.overlayEnd ?? "2.5") || 2.5);
  const legacyPosition = data.overlayPosition?.includes("顶部") ? "top" : data.overlayPosition?.includes("中上") ? "upper" : data.overlayPosition?.includes("中央") ? "center" : "bottom";
  const items: OverlayItem[] = [];
  if (mainText) items.push({ id: "overlay_main", text: mainText, startSeconds: start, endSeconds: end, position: legacyPosition, ...overlayPositionCoordinates(legacyPosition), animation: "static", style: { ...DEFAULT_OVERLAY_STYLE } });
  if (ctaText && ctaText !== mainText) items.push({ id: "overlay_cta", text: ctaText, startSeconds: Math.max(0, end - 2), endSeconds: end, position: "top", ...overlayPositionCoordinates("top"), animation: "static", style: { ...DEFAULT_OVERLAY_STYLE } });
  return items;
}

export function voiceItemsFromData(data: Pick<WorkflowData, "voiceItems" | "voiceText" | "voiceName" | "voiceVolume">): VoiceItem[] {
  const defaultVoice = data.voiceName?.trim() || "无";
  const defaultVolume = clampNumber(Number(data.voiceVolume), 0, 100, 85);
  if (data.voiceItems) {
    return uniqueById(data.voiceItems.map((item, index) => {
      const start = Math.max(0, Number(item.startSeconds) || 0);
      const end = Math.max(start + 0.1, Number(item.endSeconds) || start + 2);
      const voiceId = item.voiceId || legacyVoiceId(item.voiceName || defaultVoice);
      return {
        id: item.id || `voice_${index + 1}`,
        text: item.text || "",
        enabled: item.enabled !== false && voiceId !== "none",
        placeholder: item.placeholder === true || item.id.startsWith("voice_for_"),
        startSeconds: start,
        endSeconds: end,
        provider: item.provider || "qwen",
        model: item.model || "",
        voiceId,
        voiceName: item.voiceName || defaultVoice,
        volume: clampNumber(Number(item.volume), 0, 100, defaultVolume),
      };
    }));
  }
  const text = data.voiceText?.trim() || "";
  const voiceId = legacyVoiceId(defaultVoice);
  return text ? [{ id: "voice_main", text, enabled: voiceId !== "none", startSeconds: 0, endSeconds: 4, provider: "qwen", model: "", voiceId, voiceName: defaultVoice, volume: defaultVolume }] : [];
}

/** Build one-to-one caption segments while preserving old separate-track drafts. */
export function captionSegmentsFromData(data: Pick<WorkflowData, "overlayItems" | "overlayMain" | "overlayCta" | "overlayPosition" | "overlayStart" | "overlayEnd" | "voiceItems" | "voiceText" | "voiceName" | "voiceVolume">): CaptionSegment[] {
  const overlays = overlayItemsFromData(data).filter(item => !item.placeholder);
  const voices = voiceItemsFromData(data).filter(item => !item.placeholder);
  const claimedVoiceIds = new Set<string>();
  const segments: CaptionSegment[] = [];

  overlays.forEach((overlay, index) => {
    const hasExplicitBinding = overlay.syncVoiceId !== undefined;
    const matchedVoice = hasExplicitBinding
      ? voices.find(voice => voice.id === overlay.syncVoiceId)
      : voices.find(voice => !claimedVoiceIds.has(voice.id) && voices.indexOf(voice) === index)
        ?? voices.find(voice => !claimedVoiceIds.has(voice.id));
    const voice = matchedVoice ? { ...matchedVoice } : {
      id: `voice_for_${overlay.id}`,
      text: overlay.text,
      enabled: false,
      placeholder: true,
      startSeconds: overlay.startSeconds,
      endSeconds: overlay.endSeconds,
      provider: "qwen",
      model: "",
      voiceId: "none",
      voiceName: "none",
      volume: 85,
    };
    claimedVoiceIds.add(voice.id);
    segments.push({
      id: voice.id,
      overlay: { ...overlay },
      voice: { ...voice },
    });
  });

  voices.filter(voice => !claimedVoiceIds.has(voice.id)).forEach(voice => {
    segments.push({
      id: voice.id,
      overlay: {
        id: `overlay_for_${voice.id}`,
        text: voice.text,
        enabled: false,
        placeholder: true,
        startSeconds: voice.startSeconds,
        endSeconds: voice.endSeconds,
        position: "custom",
        ...overlayPositionCoordinates("custom"),
        animation: "static",
        syncVoiceId: voice.id,
        style: { ...DEFAULT_OVERLAY_STYLE },
      },
      voice: { ...voice },
    });
  });
  return segments;
}

export function captionSegmentsPatch(segments: CaptionSegment[]): Partial<WorkflowData> {
  const overlayItems = uniqueById(segments.filter(segment => !segment.overlay.placeholder).map(segment => ({ ...segment.overlay })));
  const voiceItems = uniqueById(segments.filter(segment => !segment.voice.placeholder).map(segment => ({ ...segment.voice })));
  const visibleOverlays = overlayItems.filter(item => item.enabled !== false);
  const enabledVoices = voiceItems.filter(item => item.enabled !== false);
  const firstOverlay = visibleOverlays[0];
  const lastOverlay = visibleOverlays.at(-1);
  const firstVoice = enabledVoices[0];
  return {
    overlayItems,
    voiceItems,
    overlayMain: firstOverlay?.text ?? "",
    overlayCta: lastOverlay?.text ?? "",
    overlayStart: firstOverlay ? `${firstOverlay.startSeconds}s` : "0s",
    overlayEnd: firstOverlay ? `${firstOverlay.endSeconds}s` : "2.5s",
    voiceText: firstVoice?.text ?? "",
    voiceName: firstVoice?.voiceName ?? "none",
    voiceVolume: String(firstVoice?.volume ?? 85),
  };
}

function uniqueById<T extends { id: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter(item => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

export function captionSegmentsWithTimings(segments: CaptionSegment[], timings: Record<string, CaptionTiming>): CaptionSegment[] {
  return segments.map(segment => {
    const timing = timings[segment.voice.id];
    if (!timing) return segment;
    const startSeconds = Math.max(0, Number(timing.startSeconds) || 0);
    const endSeconds = Math.max(startSeconds + 0.1, Number(timing.endSeconds) || startSeconds + 0.1);
    return {
      ...segment,
      overlay: segment.overlay.enabled === false || (segment.overlay.syncVoiceId !== undefined && segment.overlay.syncVoiceId !== segment.voice.id)
        ? segment.overlay
        : { ...segment.overlay, startSeconds, endSeconds, ...(segment.overlay.syncVoiceId === undefined ? {} : { syncVoiceId: segment.voice.id }) },
      voice: { ...segment.voice, startSeconds, endSeconds },
    };
  });
}

function legacyVoiceId(value: string): string {
  if (!value || value === "无" || value === "none") return "none";
  if (["女声 · 温暖自然", "female_warm", "女声 · Cherry · 温暖自然"].includes(value)) return "Cherry";
  if (["男声 · 稳重清晰", "male_clear", "男声 · Ethan · 稳重清晰"].includes(value)) return "Ethan";
  return value;
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
  if (kind === "image_process") return { ...base, backgroundBlur: 4, backgroundBrightness: 0.72, subjectScale: 0.68, subjectX: 0.5, subjectY: 0.58 };
  if (kind === "prompt") return { ...base, promptConfig: DEFAULT_PROMPT_CONFIG, ...promptLegacyPatch(DEFAULT_PROMPT_CONFIG) };
  if (kind === "generator") return { ...base, duration: "3s", resolution: "1080p", audio: "无声", storyboard: "单分镜" };
  if (kind === "output") return { ...base, outputTarget: "5-6 道菜", outputDuration: "12-15s", outputAspect: "9:16" };
  if (kind === "sound") return { ...base, voiceText: "", voiceName: "无", voiceVolume: "85", bgmVolume: "30", overlayMain: "本周限定优惠", overlayCta: "到店即享 · 现在预订", overlayPosition: "中上钩子区", overlayStart: "0.0s", overlayEnd: "2.5s", overlayItems: DEFAULT_OVERLAY_ITEMS.map(item => ({ ...item })) };
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

export function recommendClipSelection(items: TimelineClip[], clipCount: number): TimelineClip[] {
  const available = items
    .filter(clip => clip.sourcePath)
    .filter((clip, index, list) => list.findIndex(item => item.id === clip.id) === index)
    .sort((left, right) => clipRecommendationScore(right) - clipRecommendationScore(left));
  const count = Math.max(0, Math.round(clipCount));
  if (count === 0 || available.length === 0) return [];
  const special = available.filter(clip => ["甜品", "水果"].includes(resolveDishCategory(clip)));
  const ordinary = available.filter(clip => !["甜品", "水果"].includes(resolveDishCategory(clip)));
  if (count === 1) return [available[0]];

  const selected: TimelineClip[] = [];
  const targetOrdinary = Math.min(ordinary.length, special.length ? count - 1 : count);
  const byDish = new Set<string>();
  for (const clip of ordinary) {
    if (selected.length >= targetOrdinary) break;
    if (!byDish.has(clip.dish)) {
      selected.push(clip);
      byDish.add(clip.dish);
    }
  }
  for (const clip of ordinary) {
    if (selected.length >= targetOrdinary) break;
    if (!selected.some(item => item.id === clip.id)) selected.push(clip);
  }
  if (special[0] && selected.length < count) selected.push(special[0]);
  return selected;
}

function clipRecommendationScore(clip: TimelineClip): number {
  const quality = Number.isFinite(Number(clip.qualityScore)) ? Number(clip.qualityScore) : 50;
  const readyBonus = clip.sourcePath ? 20 : 0;
  const warningPenalty = (clip.qualityWarnings?.length ?? 0) * 4;
  return quality + readyBonus - warningPenalty;
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
  createWorkflowNode("image_process", "image_process", { x: 286, y: 42 }),
  createWorkflowNode("prompt", "prompt", { x: 548, y: 42 }),
  createWorkflowNode("generator", "clips", { x: 810, y: 54 }),
  createWorkflowNode("output", "output", { x: 1072, y: 54 }),
  createWorkflowNode("sound", "sound", { x: 1072, y: 282 }),
];

export const initialEdges: Edge[] = [
  { id: "assets-image-process", source: "assets", target: "image_process", type: "smoothstep" },
  { id: "image-process-prompt", source: "image_process", target: "prompt", type: "smoothstep" },
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
