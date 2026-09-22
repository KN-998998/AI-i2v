import { addEdge as addReactFlowEdge, applyEdgeChanges, applyNodeChanges, type Edge, type EdgeChange, type NodeChange } from "@xyflow/react";
import { create } from "zustand";
import { assetIdForDishName, clips, createPendingGeneratorClip, createWorkflowNode, inferDishCategory, nodeCatalog, normalizeDishCategory, normalizeTimelineClip, randomizeClipSelection, recommendClipSelection, reconcileStalePendingGeneratorClips, removeNodeAndEdges, reorderById, soundConfigFromData, type AssetLibraryPlan, type AssetLibraryPlanItem, type ClipLibraryItem, type ComposeJob, type ComposeWorkspace, type DraftPayload, type FoodType, type GenerationJob, type ImageProcessingJob, type NodeKind, type Panel, type SoundConfig, type TimelineClip, type VisualSubjectType, type WorkflowData, type WorkflowNode, type ImageRecomposeResult } from "./model";
import { workflowSeed } from "./seed";
import { fetchCanvasClips, fetchDraft, persistDraft, recomposeCanvasImage, startCanvasGeneration, startCanvasImageProcessing, waitForCanvasGeneration, waitForCanvasImageProcessing } from "./api";
import { DEFAULT_PROMPT_CONFIG, promptLegacyPatch, type PromptConfig, type PromptPresetId } from "./promptAssembler";
import { browserDraftId } from "./draftIdentity";
import { generatorGenerationBlockReason, generatorUpstreamNodes, hasSelectedGeneratedClip } from "./generatorReadiness";
// 有手或厨师入镜时怎么改主运动对象，只留 effectRules.ts 那一份，别在这里再写一遍。
import { promptConfigForVisualSubject, withEffectRule } from "./effectRules";
import { promptUpstreamNodes } from "./promptAssemblyReadiness";

type NodeEditSnapshot = Pick<WorkflowState, "nodes" | "timeline" | "candidateClips" | "composeWorkspaces" | "bgmName" | "bgmUrl" | "composeJob" | "activePanel" | "selectedNodeId" | "selectedEdgeId">;

export type BatchGenerationFailure = { generatorId: string; dish: string; stage: "图片处理" | "视频生成"; message: string };
export type BatchGenerationProgress = { phase: "图片处理" | "视频生成"; completed: number; total: number; failures: number };
export type BatchGenerationSummary = {
  total: number;
  processed: number;
  alreadyProcessed: number;
  generated: number;
  alreadyGenerated: number;
  failures: BatchGenerationFailure[];
};

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
  activeComposeWorkspaceId: string | null;
  availableClips: ClipLibraryItem[];
  clipsLoaded: boolean;
  clipsLastLoadedAt: string | null;
  clipsLoadError: string | null;
  bgmName: string;
  bgmUrl: string;
  composeJob: ComposeJob | null;
  assetLibraryPlan: AssetLibraryPlan | null;
  nextNodeNumber: number;
  draftId: string;
  hydrated: boolean;
  saving: boolean;
  lastSavedAt: string | null;
  revision: number;
  editingNodeId: string | null;
  nodeEditSnapshot: NodeEditSnapshot | null;
  setNodes: (changes: NodeChange<WorkflowNode>[]) => void;
  setEdges: (changes: EdgeChange[]) => void;
  addEdge: (edge: Edge) => void;
  setSelection: (nodeId: string | null, edgeId?: string | null) => void;
  beginNodeEdit: (nodeId: string) => void;
  saveNodeEdit: () => void;
  discardNodeEdit: () => void;
  setActivePanel: (panel: Panel) => void;
  updateNodeData: (nodeId: string, patch: Partial<WorkflowData>) => void;
  setDishEffect: (promptNodeId: string, presetId: PromptPresetId) => void;
  setPromptCustomConfig: (promptNodeId: string, config: PromptConfig) => void;
  resetPromptEffect: (promptNodeId: string) => void;
  registerGeneratorClip: (nodeId: string) => void;
  attachGeneratedClip: (nodeId: string, clip: TimelineClip) => void;
  selectGeneratorClip: (nodeId: string, clipId: string) => void;
  generateNode: (nodeId: string) => Promise<GenerationJob>;
  processImageNode: (nodeId: string) => Promise<ImageProcessingJob>;
  recomposeImageNode: (nodeId: string) => Promise<ImageRecomposeResult>;
  addNode: (kind: NodeKind) => void;
  arrangeWorkflowNodes: () => void;
  createBatchWorkflows: (items: AssetLibraryPlanItem[]) => string[];
  runBatchGeneration: (generatorIds: string[], onProgress?: (progress: BatchGenerationProgress) => void) => Promise<BatchGenerationSummary>;
  deleteNode: (nodeId: string) => void;
  duplicateNode: (nodeId: string) => void;
  deleteSelected: () => boolean;
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
  useDefaultBgm: () => void;
  updateWorkspaceSoundConfig: (workspaceId: string, patch: Partial<SoundConfig>) => void;
  setComposeJob: (job: ComposeJob | null) => void;
  setComposeBatchCount: (count: number) => void;
  setComposeClipCount: (count: number) => void;
  setActiveComposeWorkspace: (workspaceId: string | null) => void;
  randomizeComposeWorkspaces: () => void;
  recommendComposeWorkspaces: () => void;
  reorderWorkspace: (workspaceId: string, sourceId: string, targetId: string) => void;
  removeWorkspaceClip: (workspaceId: string, clipId: string) => void;
  addWorkspaceClip: (workspaceId: string, clipId: string) => void;
  setWorkspaceJob: (workspaceId: string, job: ComposeJob | null) => void;
  setAssetLibraryPlan: (plan: AssetLibraryPlan | null) => void;
  updateAssetLibraryReviewClassification: (dishName: string, category: string, foodType: FoodType | "" | null, visualSubjectType?: VisualSubjectType) => void;
  loadDraft: () => Promise<void>;
  saveDraft: () => Promise<void>;
};

const protectedNodeIds = new Set(["assets", "image_process", "prompt", "clips", "output", "sound"]);

const promptConfigurationFields = new Set<keyof WorkflowData>([
  "promptConfig",
  "promptMode",
  "promptL0",
  "promptMotion",
  "promptAmplitude",
  "promptShotSize",
  "promptL1",
  "promptL2Type1",
  "promptL2Target1",
  "promptL2Type2",
  "promptL2Target2",
  "promptL1ActionLevel",
  "promptL1ActionVerb",
  "promptSpeedCurve",
  "promptSeamlessLoop",
  "promptEndImageName",
  "promptEndImagePreview",
]);

function promptConfigurationChanged(patch: Partial<WorkflowData>): boolean {
  return Object.keys(patch).some(key => promptConfigurationFields.has(key as keyof WorkflowData));
}

function normalizedVisualSubjectType(value: string | undefined): VisualSubjectType {
  return value === "手部" || value === "厨师上半身" || value === "手部+厨师上半身" ? value : "菜品主体";
}

function imageProcessingModeForVisualSubject(value: string | undefined): "matting_composite" | "preserve_original" {
  return normalizedVisualSubjectType(value) === "菜品主体" ? "matting_composite" : "preserve_original";
}

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

function syncImageProcessStrategies(nodes: WorkflowNode[], edges: Edge[]): WorkflowNode[] {
  const inputById = new Map(nodes.filter(node => node.data.kind === "input").map(node => [node.id, node]));
  return nodes.map(node => {
    if (node.data.kind !== "image_process") return node;
    const sourceId = edges.find(edge => edge.target === node.id)?.source;
    const input = sourceId ? inputById.get(sourceId) : undefined;
    if (!input) return node;
    const visualSubjectType = normalizedVisualSubjectType(input.data.visualSubjectType);
    const processingMode = imageProcessingModeForVisualSubject(visualSubjectType);
    if (node.data.visualSubjectType === visualSubjectType && node.data.processingMode === processingMode) return node;
    return { ...node, data: { ...node.data, imagePreview: input.data.imagePreview, visualSubjectType, processingMode } };
  });
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
      && clip.assetId === other.assetId
      && clip.clipVersion === other.clipVersion
      && clip.isSelected === other.isSelected
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
      assetId: item.assetId ?? match.assetId,
      clipId: item.clipId ?? match.clipId,
      clipVersion: item.clipVersion ?? match.clipVersion,
      isSelected: item.isSelected ?? match.isSelected,
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
    const linked = candidateClips.filter(item => item.generatorNodeId === node.id);
    const completedCurrentJob = node.data.generationJobId
      ? linked.find(item => item.sourcePath && item.generationJobId === node.data.generationJobId)
      : undefined;
    const generationJobId = completedCurrentJob ? undefined : node.data.generationJobId;
    const clip = linked.find(item => item.id === node.data.selectedClipId && item.sourcePath)
      ?? linked.find(item => item.isSelected !== false && item.sourcePath)
      ?? linked.find(item => item.sourcePath)
      ?? linked.find(item => item.status === "pending")
      ?? linked[0];
    const status = clip?.sourcePath
      ? "已生成"
      : clip?.status === "pending" && generationJobId
        ? "生成中"
        : node.data.status === "生成失败"
          ? "生成失败"
          : "待生成";
    return status === node.data.status && generationJobId === node.data.generationJobId
      ? node
      : { ...node, data: { ...node.data, status, generationJobId } };
  });
}

function syncPrimaryWorkspace(workspaces: ComposeWorkspace[], timeline: TimelineClip[]): ComposeWorkspace[] {
  return workspaces.map((workspace, index) => index === 0 ? { ...workspace, clips: timeline, job: null, finalJob: null } : workspace);
}

function patchWorkspaceSoundConfig(workspace: ComposeWorkspace, patch: Partial<SoundConfig>, fallback: SoundConfig): ComposeWorkspace {
  return { ...workspace, soundConfig: { ...fallback, ...(workspace.soundConfig ?? {}), ...patch }, finalJob: null };
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

type DishNodeDedupeResult = { nodes: WorkflowNode[]; edges: Edge[]; removedGeneratorIds: Set<string> };

function workflowChainForInput(inputId: string, nodes: WorkflowNode[], edges: Edge[]): Set<string> {
  const nodeById = new Map(nodes.map(node => [node.id, node]));
  const ids = new Set<string>([inputId]);
  let current = inputId;
  for (const kind of ["image_process", "prompt", "generator"] as const) {
    const next = edges
      .filter(edge => edge.source === current)
      .map(edge => nodeById.get(edge.target))
      .find(node => node?.data.kind === kind);
    if (!next) break;
    ids.add(next.id);
    current = next.id;
  }
  return ids;
}

/** Keep one connected workflow chain per dish, preserving the latest input node. */
export function dedupeDishWorkflowNodes(nodes: WorkflowNode[], edges: Edge[]): DishNodeDedupeResult {
  const groups = new Map<string, WorkflowNode[]>();
  nodes.filter(node => node.data.kind === "input" && node.data.dishName?.trim()).forEach(node => {
    const key = node.data.dishName!.normalize("NFKC").trim().toLocaleLowerCase();
    groups.set(key, [...(groups.get(key) ?? []), node]);
  });
  const removeIds = new Set<string>();
  const removedGeneratorIds = new Set<string>();
  groups.forEach(inputs => {
    const canonical = inputs.at(-1)!;
    inputs.slice(0, -1).forEach(input => {
      const chain = workflowChainForInput(input.id, nodes, edges);
      chain.forEach(id => {
        removeIds.add(id);
        if (nodes.find(node => node.id === id)?.data.kind === "generator") removedGeneratorIds.add(id);
      });
    });
    const canonicalIndex = nodes.findIndex(node => node.id === canonical.id);
    if (canonicalIndex >= 0 && canonical.data.assetId !== assetIdForDishName(canonical.data.dishName ?? "")) {
      nodes[canonicalIndex] = { ...canonical, data: { ...canonical.data, assetId: assetIdForDishName(canonical.data.dishName ?? "") } };
    }
  });
  return {
    nodes: nodes.filter(node => !removeIds.has(node.id)),
    edges: edges.filter(edge => !removeIds.has(edge.source) && !removeIds.has(edge.target)),
    removedGeneratorIds,
  };
}

function arrangedWorkflowNodes(nodes: WorkflowNode[], edges: Edge[]): WorkflowNode[] {
  const nodeById = new Map(nodes.map(node => [node.id, node]));
  const outgoing = new Map<string, string[]>();
  edges.forEach(edge => {
    const targets = outgoing.get(edge.source) ?? [];
    targets.push(edge.target);
    outgoing.set(edge.source, targets);
  });
  const firstTargetOfKind = (sourceId: string, kind: NodeKind) => (outgoing.get(sourceId) ?? [])
    .map(id => nodeById.get(id))
    .find(node => node?.data.kind === kind);
  const rows = nodes
    .filter(node => node.data.kind === "input")
    .map(input => {
      const imageProcess = firstTargetOfKind(input.id, "image_process");
      const prompt = imageProcess && firstTargetOfKind(imageProcess.id, "prompt");
      const generator = prompt && firstTargetOfKind(prompt.id, "generator");
      return { input, imageProcess, prompt, generator };
    })
    .sort((left, right) => left.input.position.y - right.input.position.y || left.input.position.x - right.input.position.x);
  const positions = new Map<string, { x: number; y: number }>();
  const columns: Record<NodeKind, number> = {
    input: 40,
    image_process: 330,
    prompt: 620,
    generator: 910,
    output: 1210,
    sound: 1210,
    custom: 40,
  };
  // Image-bearing input and processing cards can grow to about 300px. Keep
  // enough vertical clearance so separate workflow branches never overlap.
  const rowHeight = 420;
  rows.forEach((row, index) => {
    const y = 40 + index * rowHeight;
    positions.set(row.input.id, { x: columns.input, y });
    if (row.imageProcess) positions.set(row.imageProcess.id, { x: columns.image_process, y });
    if (row.prompt) positions.set(row.prompt.id, { x: columns.prompt, y });
    if (row.generator) positions.set(row.generator.id, { x: columns.generator, y });
  });
  const outputNodes = nodes.filter(node => node.data.kind === "output");
  const outputY = rows.length > 1 ? 40 + ((rows.length - 1) * rowHeight) / 2 : 40;
  outputNodes.forEach((node, index) => positions.set(node.id, { x: columns.output, y: outputY + index * 180 }));
  nodes.filter(node => node.data.kind === "sound").forEach((node, index) => {
    positions.set(node.id, { x: columns.sound, y: outputY + 260 + index * 180 });
  });
  const remaining = nodes
    .filter(node => !positions.has(node.id))
    .sort((left, right) => left.position.y - right.position.y || left.position.x - right.position.x);
  const remainingY = Math.max(40 + rows.length * rowHeight + 80, outputY + 460);
  remaining.forEach((node, index) => positions.set(node.id, { x: columns.custom + (index % 4) * 290, y: remainingY + Math.floor(index / 4) * 220 }));
  return nodes.map(node => {
    const position = positions.get(node.id);
    return position ? { ...node, position } : node;
  });
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
  activeComposeWorkspaceId: workflowSeed.composeWorkspaces[0]?.id ?? null,
  availableClips: [],
  clipsLoaded: false,
  clipsLastLoadedAt: null,
  clipsLoadError: null,
  bgmName: workflowSeed.bgmName,
  bgmUrl: "",
  composeJob: null,
  assetLibraryPlan: null,
  nextNodeNumber: 1,
  draftId: browserDraftId(),
  hydrated: false,
  saving: false,
  lastSavedAt: null,
  revision: 0,
  editingNodeId: null,
  nodeEditSnapshot: null,
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
  beginNodeEdit: nodeId => set(state => {
    if (!state.nodes.some(node => node.id === nodeId)) return {};
    const snapshot: NodeEditSnapshot = structuredClone({
      nodes: state.nodes,
      timeline: state.timeline,
      candidateClips: state.candidateClips,
      composeWorkspaces: state.composeWorkspaces,
      bgmName: state.bgmName,
      bgmUrl: state.bgmUrl,
      composeJob: state.composeJob,
      activePanel: state.activePanel,
      selectedNodeId: state.selectedNodeId,
      selectedEdgeId: state.selectedEdgeId,
    });
    return { editingNodeId: nodeId, nodeEditSnapshot: snapshot, selectedNodeId: nodeId, selectedEdgeId: null };
  }),
  saveNodeEdit: () => set({ editingNodeId: null, nodeEditSnapshot: null }),
  discardNodeEdit: () => set(state => {
    if (!state.nodeEditSnapshot) return { editingNodeId: null };
    return { ...state.nodeEditSnapshot, editingNodeId: null, nodeEditSnapshot: null, revision: state.revision + 1 };
  }),
  setActivePanel: activePanel => set(state => ({ activePanel, revision: state.revision + 1 })),
  updateNodeData: (nodeId, patch) => set(state => {
    const node = state.nodes.find(item => item.id === nodeId);
    const data = node ? { ...node.data, ...patch } : null;
    if (node?.data.kind === "input" && "visualSubjectType" in patch && data) {
      const visualSubjectType = normalizedVisualSubjectType(data.visualSubjectType);
      const processingMode = imageProcessingModeForVisualSubject(visualSubjectType);
      const processIds = new Set(state.edges
        .filter(edge => edge.source === nodeId && state.nodes.find(item => item.id === edge.target)?.data.kind === "image_process")
        .map(edge => edge.target));
      const promptIds = new Set(state.edges
        .filter(edge => processIds.has(edge.source) && state.nodes.find(item => item.id === edge.target)?.data.kind === "prompt")
        .map(edge => edge.target));
      const nodes = state.nodes.map(item => {
        if (item.id === nodeId) return { ...item, data: { ...data, visualSubjectType } };
        if (processIds.has(item.id)) {
          return {
            ...item,
            data: {
              ...item.data,
              status: nodeCatalog.image_process.status,
              imagePreview: data.imagePreview,
              visualSubjectType,
              processingMode,
              processedImagePreview: undefined,
              processedImageName: undefined,
              processedImageAnalysis: undefined,
              processedImageMode: undefined,
              imageProcessingJobId: undefined,
              processedCutoutName: undefined,
              processedCutoutSourceName: undefined,
            },
          };
        }
        if (!promptIds.has(item.id)) return item;
        const promptConfig = promptConfigForVisualSubject({
          ...(item.data.promptConfig ?? DEFAULT_PROMPT_CONFIG),
          food_type: data.foodType,
        } as typeof DEFAULT_PROMPT_CONFIG, visualSubjectType);
        return { ...item, data: { ...item.data, promptConfig, ...promptLegacyPatch(promptConfig), status: "可生成" } };
      });
      return { nodes, revision: state.revision + 1 };
    }
    const primaryInput = state.nodes.find(item => item.data.kind === "input");
    const shouldSyncClipMetadata = node?.data.kind === "input"
      && primaryInput?.id === nodeId
      && ("dishName" in patch || "dishCategory" in patch || "foodType" in patch || "visualSubjectType" in patch);
    if (!shouldSyncClipMetadata || !data) {
      const inputMediaChanged = node?.data.kind === "input"
        && ("imagePreview" in patch || "imageName" in patch || "assetMode" in patch);
      const processIds = inputMediaChanged
        ? new Set(state.edges
          .filter(edge => edge.source === nodeId && state.nodes.find(item => item.id === edge.target)?.data.kind === "image_process")
          .map(edge => edge.target))
        : new Set<string>();
      const promptIds = inputMediaChanged
        ? new Set(state.edges
          .filter(edge => processIds.has(edge.source) && state.nodes.find(item => item.id === edge.target)?.data.kind === "prompt")
          .map(edge => edge.target))
        : new Set<string>();
      const nodes = state.nodes.map(item => {
        if (inputMediaChanged && processIds.has(item.id)) {
          return {
            ...item,
            data: {
              ...item.data,
              imagePreview: data?.imagePreview,
              status: "待处理",
              processedImagePreview: undefined,
              processedImageName: undefined,
              processedImageAnalysis: undefined,
              processedImageMode: undefined,
              imageProcessingJobId: undefined,
              processedCutoutName: undefined,
              processedCutoutSourceName: undefined,
            },
          };
        }
        if (inputMediaChanged && promptIds.has(item.id)) return { ...item, data: { ...item.data, status: "可生成" } };
        if (item.id !== nodeId) return item;
        const nextData = { ...item.data, ...patch };
        if (item.data.kind === "prompt" && promptConfigurationChanged(patch) && !("status" in patch)) nextData.status = "可生成";
        return { ...item, data: nextData };
      });
      if (node?.data.kind !== "sound") return { nodes, revision: state.revision + 1 };
      const activeWorkspace = state.composeWorkspaces.find(item => item.id === state.activeComposeWorkspaceId);
      const fallback = soundConfigFromData({ ...node.data, ...patch }, state.bgmName, state.bgmUrl);
      const composeWorkspaces = state.composeWorkspaces.map(workspace => workspace.id === activeWorkspace?.id
        ? patchWorkspaceSoundConfig(workspace, patch as Partial<SoundConfig>, fallback)
        : workspace);
      return { nodes, composeWorkspaces, revision: state.revision + 1 };
    }
    const dish = data.dishName || "待配置菜品";
    const dishCategory = normalizeDishCategory(data.dishCategory, data.dishName ? dish : "");
    const foodType = dishCategory === "套餐" ? "混合/多温" : data.foodType as FoodType | undefined;
    const nextInputData = { ...data, foodType };
    const visualSubjectType = data.visualSubjectType ?? "菜品主体";
    const syncClip = (clip: TimelineClip) => clip.generatorNodeId ? { ...clip, dish, dishCategory, foodType, visualSubjectType } : clip;
    const candidateClips = state.candidateClips.map(syncClip);
    const timeline = state.timeline.map(syncClip);
    const composeWorkspaces = state.composeWorkspaces.map(workspace => ({ ...workspace, clips: workspace.clips.map(syncClip) }));
    const nodes = state.nodes.map(item => {
      if (item.id === nodeId) return { ...item, data: nextInputData };
      if (item.data.kind === "image_process" && "visualSubjectType" in patch) {
        return { ...item, data: { ...item.data, status: "待处理", processedImagePreview: undefined, processedImageName: undefined, processedImageAnalysis: undefined, processedImageMode: undefined, imageProcessingJobId: undefined, processedCutoutName: undefined, processedCutoutSourceName: undefined } };
      }
      if (item.data.kind !== "prompt") return item;
      const promptConfig = promptConfigForVisualSubject({ ...(item.data.promptConfig ?? DEFAULT_PROMPT_CONFIG), food_type: foodType } as typeof DEFAULT_PROMPT_CONFIG, data.visualSubjectType);
      return { ...item, data: { ...item.data, promptConfig, ...promptLegacyPatch(promptConfig), status: "可生成" } };
    });
    return {
      nodes,
      candidateClips,
      timeline,
      composeWorkspaces,
      revision: state.revision + 1,
    };
  }),
  // 第 3 步换效果：写成「这一类菜用这个效果」的规则，同一类的菜和批量生产都跟着换。
  setDishEffect: (promptNodeId, presetId) => set(state => {
    const promptNode = state.nodes.find(item => item.id === promptNodeId && item.data.kind === "prompt");
    if (!promptNode) return {};
    const { input } = promptUpstreamNodes(promptNode, state.nodes, state.edges);
    const nodes = withEffectRule(state.nodes, promptNodeId, input?.data ?? {}, presetId);
    // 这道菜用不了这个效果时 withEffectRule 原样返回，什么也别改（也别白占一次自动保存）。
    if (nodes === state.nodes) return {};
    return { nodes, revision: state.revision + 1 };
  }),
  // 在高级设置里逐项调过：从此按存着的配置走，不再跟着冷热规则变。
  setPromptCustomConfig: (promptNodeId, config) => set(state => {
    const nodes = state.nodes.map(item => item.id === promptNodeId && item.data.kind === "prompt"
      ? { ...item, data: { ...item.data, effectMode: "custom" as const, promptConfig: config, ...promptLegacyPatch(config) } }
      : item);
    return { nodes, revision: state.revision + 1 };
  }),
  resetPromptEffect: promptNodeId => set(state => {
    const nodes = state.nodes.map(item => item.id === promptNodeId && item.data.kind === "prompt"
      ? { ...item, data: { ...item.data, effectMode: "rule" as const } }
      : item);
    return { nodes, revision: state.revision + 1 };
  }),
  registerGeneratorClip: nodeId => set(state => {
    const node = state.nodes.find(item => item.id === nodeId && item.data.kind === "generator");
    if (!node) return {};
    const existing = state.candidateClips.find(item => item.generatorNodeId === nodeId && item.status === "pending");
    const input = generatorUpstreamNodes(node, state.nodes, state.edges).input;
    const dish = input?.data.dishName || existing?.dish || "待配置菜品";
    const dishCategory = normalizeDishCategory(input?.data.dishCategory ?? existing?.dishCategory, input?.data.dishName ? dish : "");
    const foodType = dishCategory === "套餐" ? "混合/多温" : input?.data.foodType as FoodType | undefined;
    const visualSubjectType = input?.data.visualSubjectType ?? "菜品主体";
    const assetId = input?.data.assetId ?? existing?.assetId ?? `asset_${nodeId}`;
    const clip = existing
      ? { ...existing, dish, dishCategory, foodType, visualSubjectType, assetId, label: "生成任务", status: "pending" as const }
      : { ...createPendingGeneratorClip(nodeId, state.nextNodeNumber, dish, dishCategory, assetId), ...(state.candidateClips.some(item => item.generatorNodeId === nodeId) ? { id: `${nodeId}_pending_${state.nextNodeNumber}` } : {}), isSelected: false, foodType, visualSubjectType };
    const candidateClips = existing
      ? state.candidateClips.map(item => item.id === existing.id ? clip : item)
      : [...state.candidateClips, clip];
    return {
      nodes: state.nodes.map(item => item.id === nodeId ? { ...item, data: { ...item.data, assetId, status: "待关联真实文件" } } : item),
      candidateClips,
      revision: state.revision + 1,
    };
  }),
  attachGeneratedClip: (nodeId, clip) => set(state => {
    const existing = state.candidateClips.find(item => item.generatorNodeId === nodeId && item.status === "pending");
    const previousVersion = state.candidateClips.find(item => item.generatorNodeId === nodeId && item.generationJobId === clip.generationJobId);
    const nextClip = normalizeTimelineClip({
      ...clip,
      id: existing?.id ?? clip.id,
      generatorNodeId: nodeId,
      status: "generated" as const,
      isSelected: true,
    });
    const candidateClips = previousVersion
      ? state.candidateClips
      : existing
        ? state.candidateClips.map(item => item.id === existing.id ? nextClip : item)
        : [...state.candidateClips.map(item => item.generatorNodeId === nodeId ? { ...item, isSelected: false } : item), nextClip];
    const selectedCandidates = candidateClips.map(item => item.generatorNodeId === nodeId ? { ...item, isSelected: item.id === nextClip.id } : item);
    const replace = (items: TimelineClip[]) => items.map(item => item.generatorNodeId === nodeId ? nextClip : item);
    const composeWorkspaces = state.composeWorkspaces.map(workspace => ({ ...workspace, clips: replace(workspace.clips) }));
    return {
      candidateClips: previousVersion ? candidateClips : selectedCandidates,
      timeline: replace(state.timeline),
      composeWorkspaces,
      availableClips: [...state.availableClips.filter(item => item.sourcePath !== nextClip.sourcePath), nextClip as ClipLibraryItem],
       nodes: state.nodes.map(item => item.id === nodeId ? { ...item, data: { ...item.data, assetId: nextClip.assetId ?? item.data.assetId, selectedClipId: nextClip.id, generationJobId: undefined, status: "已生成" } } : item),
      revision: state.revision + 1,
    };
  }),
  selectGeneratorClip: (nodeId, clipId) => set(state => {
    const selected = state.candidateClips.find(item => item.id === clipId && item.generatorNodeId === nodeId && item.sourcePath);
    if (!selected) return {};
    const candidateClips = state.candidateClips.map(item => item.generatorNodeId === nodeId ? { ...item, isSelected: item.id === clipId } : item);
    const replace = (items: TimelineClip[]) => items.map(item => item.generatorNodeId === nodeId ? { ...selected } : item);
    const composeWorkspaces = state.composeWorkspaces.map(workspace => ({ ...workspace, clips: replace(workspace.clips), job: null, finalJob: null }));
    return {
      candidateClips,
      timeline: replace(state.timeline),
      composeWorkspaces,
      nodes: state.nodes.map(item => item.id === nodeId ? { ...item, data: { ...item.data, selectedClipId: clipId, status: "已生成" } } : item),
      revision: state.revision + 1,
    };
  }),
  generateNode: async nodeId => {
    const state = get();
    const node = state.nodes.find(item => item.id === nodeId && item.data.kind === "generator");
    if (!node) throw new Error("生成节点不存在");
    const blockReason = generatorGenerationBlockReason(node, state.nodes, state.edges);
    if (blockReason) throw new Error(blockReason);
    state.registerGeneratorClip(nodeId);
    state.updateNodeData(nodeId, { status: "生成中" });
    await get().saveDraft();
    try {
      const started = await startCanvasGeneration(get().draftId, nodeId);
      get().updateNodeData(nodeId, { generationJobId: started.job_id });
      await get().saveDraft();
      const completed = await waitForCanvasGeneration(get().draftId, started);
      if (completed.status === "error") throw new Error(completed.error || "Kling 生成失败");
      if (completed.status !== "done" || !completed.clip) throw new Error("生成任务超时，请检查后端日志");
      get().attachGeneratedClip(nodeId, completed.clip);
      await get().saveDraft();
      return completed;
    } catch (error) {
      get().updateNodeData(nodeId, { status: "生成失败", generationJobId: undefined });
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
        processedImageMode: completed.processingMode,
        visualSubjectType: completed.visualSubjectType,
        processedCutoutName: completed.cutout_name ?? undefined,
        processedCutoutSourceName: completed.cutout_source_name ?? undefined,
      });
      await get().saveDraft();
      return completed;
    } catch (error) {
      get().updateNodeData(nodeId, { status: "处理失败" });
      throw error;
    }
  },
  recomposeImageNode: async nodeId => {
    const node = get().nodes.find(item => item.id === nodeId);
    if (!node) throw new Error("图片处理节点不存在");
    const data = node.data;
    const result = await recomposeCanvasImage(get().draftId, nodeId, {
      backgroundTemplateId: data.backgroundTemplateId,
      backgroundTemplateName: data.backgroundTemplateName,
      backgroundPreview: data.backgroundPreview,
      backgroundBlur: data.backgroundBlur,
      backgroundBrightness: data.backgroundBrightness,
      subjectScale: data.subjectScale,
      subjectX: data.subjectX,
      subjectY: data.subjectY,
    });
    get().updateNodeData(nodeId, {
      status: "已处理",
      processedImagePreview: result.result_url,
      processedImageName: result.result_name,
      processedImageAnalysis: result.analysis ?? undefined,
      processedImageMode: result.processingMode,
    });
    await get().saveDraft();
    return result;
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
  arrangeWorkflowNodes: () => set(state => ({
    nodes: arrangedWorkflowNodes(state.nodes, state.edges),
    revision: state.revision + 1,
  })),
  createBatchWorkflows: items => {
    const createdIds: string[] = [];
    set(state => {
      const deduped = dedupeDishWorkflowNodes([...state.nodes], [...state.edges]);
      let nodes = deduped.nodes;
      let edges = deduped.edges;
      let artifacts: Pick<WorkflowState, "candidateClips" | "composeWorkspaces" | "timeline"> = removeNodeArtifacts(state, deduped.removedGeneratorIds);
      let nextNodeNumber = state.nextNodeNumber;
      let newNodeIndex = 0;
      const latestItems = new Map<string, AssetLibraryPlanItem>();
      items.forEach(item => latestItems.set(item.dishName.normalize("NFKC").trim().toLocaleLowerCase(), item));
      latestItems.forEach(item => {
        const assetId = assetIdForDishName(item.dishName);
        const dishKey = item.dishName.normalize("NFKC").trim().toLocaleLowerCase();
        const existingInput = nodes.find(node => node.data.kind === "input" && node.data.dishName?.normalize("NFKC").trim().toLocaleLowerCase() === dishKey);
        if (existingInput) {
          const chainIds = workflowChainForInput(existingInput.id, nodes, edges);
          const processNode = [...chainIds].map(id => nodes.find(node => node.id === id)).find(node => node?.data.kind === "image_process");
          const promptNode = [...chainIds].map(id => nodes.find(node => node.id === id)).find(node => node?.data.kind === "prompt");
          const generatorNode = [...chainIds].map(id => nodes.find(node => node.id === id)).find(node => node?.data.kind === "generator");
          const visualSubjectType = normalizedVisualSubjectType(item.visualSubjectType);
          const processingMode = imageProcessingModeForVisualSubject(visualSubjectType);
          if (generatorNode) artifacts = removeNodeArtifacts(artifacts, new Set([generatorNode.id]));
          nodes = nodes.map(node => {
            if (node.id === existingInput.id) return { ...node, data: { ...node.data, assetId, title: item.dishName, dishName: item.dishName, sourceLibraryCategory: item.sourceCategory, dishCategory: item.dishCategory as typeof node.data.dishCategory, foodType: item.foodType, visualSubjectType, imageName: item.imageName, imagePreview: item.imagePreview, status: "已就绪", selectedClipId: undefined } };
            if (node.id === processNode?.id) return { ...node, data: { ...node.data, imagePreview: item.imagePreview, backgroundTemplateId: item.background.id, backgroundTemplateName: item.background.name, backgroundPreview: item.background.url, status: "待处理", visualSubjectType, processingMode, processedImagePreview: undefined, processedImageName: undefined, processedImageAnalysis: undefined, processedImageMode: undefined, imageProcessingJobId: undefined } };
            if (node.id === promptNode?.id) {
              const promptConfig = promptConfigForVisualSubject({ ...(node.data.promptConfig ?? DEFAULT_PROMPT_CONFIG), food_type: item.foodType } as typeof DEFAULT_PROMPT_CONFIG, visualSubjectType);
              return { ...node, data: { ...node.data, title: `${item.dishName} 提示词`, promptConfig, ...promptLegacyPatch(promptConfig), status: "可生成" } };
            }
            if (node.id === generatorNode?.id) return { ...node, data: { ...node.data, assetId, title: `${item.dishName} 视频片段`, status: "待生成", selectedClipId: undefined } };
            return node;
          });
          if (generatorNode) createdIds.push(generatorNode.id);
          return;
        }
        const base = nextNodeNumber;
        nextNodeNumber += 4;
        const y = 520 + newNodeIndex * 250;
        newNodeIndex += 1;
        const inputId = `node_input_${base}`;
        const processId = `node_image_process_${base + 1}`;
        const promptId = `node_prompt_${base + 2}`;
        const generatorId = `node_generator_${base + 3}`;
        const cold = item.foodType === "冷食";
        const mixed = item.foodType === "混合/多温";
        const promptConfig = promptConfigForVisualSubject({
          ...DEFAULT_PROMPT_CONFIG,
          elements: [cold ? "dish_cold" : "dish_hot", "tableware", "surface", "backdrop"],
          l1_subject: cold ? "dish_cold" : "dish_hot",
          l2_dynamics: [{ type: "specular", target: "菜品" }],
          food_type: mixed ? "混合/多温" : item.foodType === "冷食" ? "冷食" : "热食",
        } as typeof DEFAULT_PROMPT_CONFIG, item.visualSubjectType);
        const input = createWorkflowNode("input", inputId, { x: 24, y });
        input.data = { ...input.data, assetId, title: item.dishName, dishName: item.dishName, sourceLibraryCategory: item.sourceCategory, dishCategory: item.dishCategory as typeof input.data.dishCategory, foodType: item.foodType, visualSubjectType: item.visualSubjectType, imageName: item.imageName, imagePreview: item.imagePreview, status: "已就绪" };
        const process = createWorkflowNode("image_process", processId, { x: 286, y });
        const visualSubjectType = normalizedVisualSubjectType(item.visualSubjectType);
        process.data = {
          ...process.data,
          imagePreview: item.imagePreview,
          visualSubjectType,
          processingMode: imageProcessingModeForVisualSubject(visualSubjectType),
          backgroundTemplateId: item.background.id,
          backgroundTemplateName: item.background.name,
          backgroundPreview: item.background.url,
          status: "待处理",
        };
        const prompt = createWorkflowNode("prompt", promptId, { x: 548, y });
        prompt.data = { ...prompt.data, title: `${item.dishName} 提示词`, promptConfig, ...promptLegacyPatch(promptConfig) };
        const generator = createWorkflowNode("generator", generatorId, { x: 810, y });
        generator.data = { ...generator.data, assetId, title: `${item.dishName} 视频片段`, status: "待生成", duration: "3s", resolution: "1080p" };
        nodes.push(input, process, prompt, generator);
        edges.push(
          { id: `${inputId}-${processId}`, source: inputId, target: processId, type: "smoothstep" },
          { id: `${processId}-${promptId}`, source: processId, target: promptId, type: "smoothstep" },
          { id: `${promptId}-${generatorId}`, source: promptId, target: generatorId, type: "smoothstep" },
          { id: `${generatorId}-output`, source: generatorId, target: "output", type: "smoothstep" },
        );
        createdIds.push(generatorId);
      });
      return { nodes, edges, ...artifacts, nextNodeNumber, selectedNodeId: createdIds.at(-1) ?? state.selectedNodeId, selectedEdgeId: null, revision: state.revision + 1 };
    });
    return createdIds;
  },
  runBatchGeneration: async (generatorIds, onProgress) => {
    const ids = [...new Set(generatorIds)];
    const failures: BatchGenerationFailure[] = [];
    const readyGeneratorIds: string[] = [];
    let processed = 0;
    let alreadyProcessed = 0;
    let generated = 0;
    let alreadyGenerated = 0;

    for (let index = 0; index < ids.length; index += 1) {
      const generatorId = ids[index];
      const state = get();
      const generator = state.nodes.find(node => node.id === generatorId && node.data.kind === "generator");
      const dish = generator?.data.title ?? generatorId;
      const process = generator ? generatorUpstreamNodes(generator, state.nodes, state.edges).process : undefined;
      if (!generator || !process) {
        failures.push({ generatorId, dish, stage: "图片处理", message: "缺少对应的图片处理节点连接" });
      } else if (process.data.processedImagePreview) {
        alreadyProcessed += 1;
        readyGeneratorIds.push(generatorId);
      } else {
        try {
          await get().processImageNode(process.id);
          processed += 1;
          readyGeneratorIds.push(generatorId);
        } catch (error) {
          failures.push({ generatorId, dish, stage: "图片处理", message: error instanceof Error ? error.message : "图片处理失败" });
        }
      }
      onProgress?.({ phase: "图片处理", completed: index + 1, total: ids.length, failures: failures.length });
    }

    for (let index = 0; index < readyGeneratorIds.length; index += 1) {
      const generatorId = readyGeneratorIds[index];
      const state = get();
      const generator = state.nodes.find(node => node.id === generatorId && node.data.kind === "generator");
      const dish = generator?.data.title ?? generatorId;
      if (!generator) {
        failures.push({ generatorId, dish, stage: "视频生成", message: "生成节点不存在" });
      } else if (hasSelectedGeneratedClip(generatorId, state.candidateClips)) {
        alreadyGenerated += 1;
      } else {
        try {
          await get().generateNode(generatorId);
          generated += 1;
        } catch (error) {
          failures.push({ generatorId, dish, stage: "视频生成", message: error instanceof Error ? error.message : "视频生成失败" });
        }
      }
      onProgress?.({ phase: "视频生成", completed: index + 1, total: readyGeneratorIds.length, failures: failures.length });
    }

    return { total: ids.length, processed, alreadyProcessed, generated, alreadyGenerated, failures };
  },
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
  deleteSelected: () => {
    let deleted = false;
    set(state => {
      const removedNodeIds = new Set([
        ...state.nodes.filter(node => node.selected && !protectedNodeIds.has(node.id)).map(node => node.id),
        ...(state.selectedNodeId && !protectedNodeIds.has(state.selectedNodeId) ? [state.selectedNodeId] : []),
      ]);
      const removedEdgeIds = new Set([
        ...state.edges.filter(edge => edge.selected).map(edge => edge.id),
        ...(state.selectedEdgeId ? [state.selectedEdgeId] : []),
      ]);
      if (!removedNodeIds.size && !removedEdgeIds.size) return {};
      const nodes = state.nodes.filter(node => !removedNodeIds.has(node.id));
      const edges = state.edges.filter(edge => !removedEdgeIds.has(edge.id) && !removedNodeIds.has(edge.source) && !removedNodeIds.has(edge.target));
      const artifacts = removedNodeIds.size ? removeNodeArtifacts(state, removedNodeIds) : {};
      deleted = true;
      return { nodes, edges, ...artifacts, selectedNodeId: null, selectedEdgeId: null, revision: state.revision + 1 };
    });
    return deleted;
  },
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
      return includesClip ? { ...workspace, clips: workspace.clips.map(update), job: null, finalJob: null } : workspace;
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
        const completedJobKeys = new Set(
          [...availableClips, ...state.candidateClips]
            .filter(clip => clip.sourcePath && clip.generatorNodeId && clip.generationJobId)
            .map(clip => `${clip.generatorNodeId}:${clip.generationJobId}`),
        );
        const activeGenerationNodeIds = new Set(state.nodes
          .filter(node => node.data.kind === "generator"
            && Boolean(node.data.generationJobId)
            && !completedJobKeys.has(`${node.id}:${node.data.generationJobId}`))
          .map(node => node.id));
        const normalizedTimeline = reconcileStalePendingGeneratorClips(
          state.timeline.map(clip => withResolvedDishCategory(normalizeTimelineClip(clip))),
          availableClips,
          activeGenerationNodeIds,
          "replace",
        );
        const normalizedCandidates = reconcileStalePendingGeneratorClips(
          state.candidateClips.map(clip => withResolvedDishCategory(normalizeTimelineClip(clip))),
          availableClips,
          activeGenerationNodeIds,
        );
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
        const workspaces = state.composeWorkspaces.map((workspace, index) => {
          const workspaceClips = reconcileStalePendingGeneratorClips(
            workspace.clips.map(clip => withResolvedDishCategory(normalizeTimelineClip(clip))),
            availableClips,
            activeGenerationNodeIds,
            "replace",
          );
          return index === 0 && timelineChanged
            ? { ...workspace, clips: timeline, job: null, finalJob: null }
            : sameClipList(workspaceClips, workspace.clips) ? workspace : { ...workspace, clips: workspaceClips, job: null, finalJob: null };
        });
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
  setBgmName: bgmName => set(state => {
    const workspaceId = state.activeComposeWorkspaceId;
    const soundNode = state.nodes.find(node => node.data.kind === "sound");
    const fallback = soundNode ? soundConfigFromData(soundNode.data, state.bgmName, state.bgmUrl) : soundConfigFromData({}, state.bgmName, state.bgmUrl);
    const composeWorkspaces = state.composeWorkspaces.map(workspace => workspace.id === workspaceId
      ? { ...workspace, soundConfig: { ...fallback, ...(workspace.soundConfig ?? {}), bgmName }, finalJob: null }
      : workspace);
    return { bgmName, composeWorkspaces, revision: state.revision + 1 };
  }),
  // BGM 三态都写显式的 bgmMode：光看名字和 url 猜不出「不要音乐」和「还没选」的区别。
  setBgm: (bgmName, bgmUrl) => set(state => {
    const workspaceId = state.activeComposeWorkspaceId;
    const soundNode = state.nodes.find(node => node.data.kind === "sound");
    const fallback = soundNode ? soundConfigFromData(soundNode.data, state.bgmName, state.bgmUrl) : soundConfigFromData({}, state.bgmName, state.bgmUrl);
    const composeWorkspaces = state.composeWorkspaces.map(workspace => workspace.id === workspaceId
      ? { ...workspace, soundConfig: { ...fallback, ...(workspace.soundConfig ?? {}), bgmName, bgmUrl, bgmMode: "custom" as const }, finalJob: null }
      : workspace);
    return { bgmName, bgmUrl, composeWorkspaces, revision: state.revision + 1 };
  }),
  clearBgm: () => set(state => {
    const workspaceId = state.activeComposeWorkspaceId;
    const soundNode = state.nodes.find(node => node.data.kind === "sound");
    const fallback = soundNode ? soundConfigFromData(soundNode.data, state.bgmName, state.bgmUrl) : soundConfigFromData({}, state.bgmName, state.bgmUrl);
    const composeWorkspaces = state.composeWorkspaces.map(workspace => workspace.id === workspaceId
      ? { ...workspace, soundConfig: { ...fallback, ...(workspace.soundConfig ?? {}), bgmName: "", bgmUrl: "", bgmMode: "none" as const }, finalJob: null }
      : workspace);
    return { bgmName: "", bgmUrl: "", composeWorkspaces, revision: state.revision + 1 };
  }),
  useDefaultBgm: () => set(state => {
    const workspaceId = state.activeComposeWorkspaceId;
    const soundNode = state.nodes.find(node => node.data.kind === "sound");
    const fallback = soundNode ? soundConfigFromData(soundNode.data, state.bgmName, state.bgmUrl) : soundConfigFromData({}, state.bgmName, state.bgmUrl);
    const composeWorkspaces = state.composeWorkspaces.map(workspace => workspace.id === workspaceId
      ? { ...workspace, soundConfig: { ...fallback, ...(workspace.soundConfig ?? {}), bgmName: "默认曲库", bgmUrl: "", bgmMode: "default" as const }, finalJob: null }
      : workspace);
    return { bgmName: "默认曲库", bgmUrl: "", composeWorkspaces, revision: state.revision + 1 };
  }),
  updateWorkspaceSoundConfig: (workspaceId, patch) => set(state => {
    const soundNode = state.nodes.find(node => node.data.kind === "sound");
    const fallback = soundNode ? soundConfigFromData(soundNode.data, state.bgmName, state.bgmUrl) : soundConfigFromData({}, state.bgmName, state.bgmUrl);
    const composeWorkspaces = state.composeWorkspaces.map(workspace => workspace.id === workspaceId ? patchWorkspaceSoundConfig(workspace, patch, fallback) : workspace);
    const mirror = workspaceId === state.activeComposeWorkspaceId ? composeWorkspaces.find(workspace => workspace.id === workspaceId)?.soundConfig : undefined;
    return mirror ? { composeWorkspaces, bgmName: mirror.bgmName, bgmUrl: mirror.bgmUrl, revision: state.revision + 1 } : { composeWorkspaces, revision: state.revision + 1 };
  }),
  setComposeJob: composeJob => set(state => ({ composeJob, revision: state.revision + 1 })),
  setComposeBatchCount: count => set(state => {
    const nextCount = Math.max(1, Math.min(20, Math.round(count)));
    const soundNode = state.nodes.find(node => node.data.kind === "sound");
    const fallback = soundNode ? soundConfigFromData(soundNode.data, state.bgmName, state.bgmUrl) : soundConfigFromData({}, state.bgmName, state.bgmUrl);
    const workspaces = Array.from({ length: nextCount }, (_, index) => state.composeWorkspaces[index] ?? { id: `compose_${index + 1}`, title: `成片 ${index + 1}`, clips: [], job: null, finalJob: null, soundConfig: fallback });
    const activeComposeWorkspaceId = workspaces.some(workspace => workspace.id === state.activeComposeWorkspaceId) ? state.activeComposeWorkspaceId : workspaces[0]?.id ?? null;
    return { composeBatchCount: nextCount, composeWorkspaces: workspaces, activeComposeWorkspaceId, revision: state.revision + 1 };
  }),
  setComposeClipCount: count => set(state => ({ composeClipCount: Math.max(1, Math.min(20, Math.round(count))), revision: state.revision + 1 })),
  setActiveComposeWorkspace: activeComposeWorkspaceId => set(state => {
    const workspace = state.composeWorkspaces.find(item => item.id === activeComposeWorkspaceId);
    return {
      activeComposeWorkspaceId,
      bgmName: workspace?.soundConfig?.bgmName ?? state.bgmName,
      bgmUrl: workspace?.soundConfig?.bgmUrl ?? state.bgmUrl,
      revision: state.revision + 1,
    };
  }),
  randomizeComposeWorkspaces: () => set(state => {
    const pool = state.candidateClips.filter(clip => clip.sourcePath && clip.isSelected !== false);
    const workspaces = state.composeWorkspaces.map(workspace => {
      return { ...workspace, clips: randomizeClipSelection(pool, state.composeClipCount), job: null, finalJob: null };
    });
    return { composeWorkspaces: workspaces, timeline: workspaces[0]?.clips ?? [], revision: state.revision + 1 };
  }),
  recommendComposeWorkspaces: () => set(state => {
    const pool = state.candidateClips.filter(clip => clip.sourcePath && clip.isSelected !== false);
    const workspaces = state.composeWorkspaces.map(workspace => ({
      ...workspace,
      clips: recommendClipSelection(pool, state.composeClipCount),
      job: null,
      finalJob: null,
    }));
    return { composeWorkspaces: workspaces, timeline: workspaces[0]?.clips ?? [], revision: state.revision + 1 };
  }),
  reorderWorkspace: (workspaceId, sourceId, targetId) => set(state => {
    const composeWorkspaces = state.composeWorkspaces.map(workspace => workspace.id === workspaceId ? { ...workspace, clips: reorderById(workspace.clips, sourceId, targetId), job: null, finalJob: null } : workspace);
    return { composeWorkspaces, timeline: composeWorkspaces[0]?.clips ?? state.timeline, revision: state.revision + 1 };
  }),
  removeWorkspaceClip: (workspaceId, clipId) => set(state => {
    const composeWorkspaces = state.composeWorkspaces.map(workspace => workspace.id === workspaceId ? { ...workspace, clips: workspace.clips.filter(clip => clip.id !== clipId), job: null, finalJob: null } : workspace);
    return { composeWorkspaces, timeline: composeWorkspaces[0]?.clips ?? state.timeline, revision: state.revision + 1 };
  }),
  addWorkspaceClip: (workspaceId, clipId) => set(state => {
    const clip = state.candidateClips.find(item => item.id === clipId);
    if (!clip) return {};
    const composeWorkspaces = state.composeWorkspaces.map(workspace => workspace.id === workspaceId && !workspace.clips.some(item => item.id === clipId) ? { ...workspace, clips: [...workspace.clips, clip], job: null, finalJob: null } : workspace);
    return { composeWorkspaces, timeline: composeWorkspaces[0]?.clips ?? state.timeline, revision: state.revision + 1 };
  }),
  setWorkspaceJob: (workspaceId, job) => set(state => ({
    composeWorkspaces: state.composeWorkspaces.map(workspace => workspace.id === workspaceId
      ? { ...workspace, ...(job?.include_sound ? { finalJob: job } : { job }) }
      : workspace),
    composeJob: job,
    revision: state.revision + 1,
  })),
  setAssetLibraryPlan: assetLibraryPlan => set(state => ({ assetLibraryPlan, revision: state.revision + 1 })),
  updateAssetLibraryReviewClassification: (dishName, category, foodType, visualSubjectType) => set(state => {
    if (!state.assetLibraryPlan) return {};
    const reviewItems = (state.assetLibraryPlan.reviewItems ?? []).map(item => item.dishName === dishName ? { ...item, suggestedCategory: category, foodType: foodType || null, visualSubjectType: visualSubjectType ?? item.visualSubjectType ?? "菜品主体" } : item);
    return { assetLibraryPlan: { ...state.assetLibraryPlan, reviewItems }, revision: state.revision + 1 };
  }),
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
    const strategyNodes = syncImageProcessStrategies(migrated.nodes, migrated.edges);
    const normalizedNodes = strategyNodes.map(node => {
      const portableData = node.data.kind === "input"
        ? { ...node.data, sourceLibraryPath: undefined, dishCategory: normalizeDishCategory(node.data.dishCategory, node.data.dishName ?? "") }
        : node.data;
      return portableData.kind === "input" && !portableData.dishCategory
        ? { ...node, data: { ...portableData, dishCategory: portableData.dishName ? inferDishCategory(portableData.dishName) : "其他" } }
        : portableData === node.data ? node : { ...node, data: portableData };
    });
    const deduped = dedupeDishWorkflowNodes(normalizedNodes, migrated.edges);
    const migratedNodes = deduped.nodes.map(node => node.data.kind === "prompt" && (node.id === "prompt" || node.data.title === "槽位化提示词")
      ? { ...node, data: { ...node.data, title: "基础提示词模板", description: node.data.description || nodeCatalog.prompt.description } }
      : node);
    const normalizedCandidatesAfterDedupe = deduped.removedGeneratorIds.size
      ? removeNodeArtifacts({ candidateClips: normalizedCandidates, composeWorkspaces: (draft.composeWorkspaces ?? []).map(workspace => ({ ...workspace, clips: workspace.clips.map(normalizeTimelineClip) })), timeline: draft.timeline.map(normalizeTimelineClip) }, deduped.removedGeneratorIds)
      : { candidateClips: normalizedCandidates, composeWorkspaces: (draft.composeWorkspaces ?? []).map(workspace => ({ ...workspace, clips: workspace.clips.map(normalizeTimelineClip) })), timeline: draft.timeline.map(normalizeTimelineClip) };
    const nodes = syncGeneratorNodeStatuses(migratedNodes, normalizedCandidatesAfterDedupe.candidateClips);
    const nodesChanged = nodes.length !== migrated.nodes.length || nodes.some((node, index) => node !== migrated.nodes[index]);
    set({
      nodes,
      edges: deduped.edges,
      timeline: normalizedCandidatesAfterDedupe.timeline,
      candidateClips: normalizedCandidatesAfterDedupe.candidateClips,
      composeBatchCount: draft.composeBatchCount ?? 1,
      composeClipCount: draft.composeClipCount ?? draft.timeline.length,
       composeWorkspaces: (draft.composeWorkspaces ?? [{ id: "compose_1", title: "成片 1", clips: draft.timeline, job: draft.composeJob ?? null }]).map(workspace => ({ ...workspace, clips: normalizedCandidatesAfterDedupe.composeWorkspaces.find(item => item.id === workspace.id)?.clips ?? workspace.clips.map(normalizeTimelineClip), finalJob: workspace.finalJob ?? null, soundConfig: workspace.soundConfig ?? soundConfigFromData(nodes.find(node => node.data.kind === "sound")?.data ?? {}, draft.bgmName ?? "", draft.bgmUrl ?? "") })),
      activeComposeWorkspaceId: draft.activeComposeWorkspaceId ?? draft.composeWorkspaces?.[0]?.id ?? "compose_1",
       bgmName: draft.bgmName ?? "",
      bgmUrl: draft.bgmUrl ?? "",
      composeJob: draft.composeJob ?? null,
      assetLibraryPlan: draft.assetLibraryPlan ?? null,
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
        nodes: state.nodes.map(({ selected: _selected, measured: _measured, ...node }) => node.data.kind === "input" && node.data.sourceLibraryPath
          ? { ...node, data: { ...node.data, sourceLibraryPath: undefined } }
          : node),
        edges: state.edges.map(({ selected: _selected, ...edge }) => edge),
        timeline: state.timeline,
        candidateClips: state.candidateClips,
        composeBatchCount: state.composeBatchCount,
        composeClipCount: state.composeClipCount,
        composeWorkspaces: state.composeWorkspaces,
        activeComposeWorkspaceId: state.activeComposeWorkspaceId,
        bgmName: state.bgmName,
        bgmUrl: state.bgmUrl,
        composeJob: state.composeJob,
        assetLibraryPlan: state.assetLibraryPlan
          ? {
            ...state.assetLibraryPlan,
            assetRoot: "",
            backgroundRoot: "",
            selected: state.assetLibraryPlan.selected.map(item => ({ ...item, sourcePath: "" })),
          }
          : null,
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
