import type { Edge } from "@xyflow/react";
import type { ComposeWorkspace, TimelineClip, WorkflowNode } from "./model";
import { generatorGenerationBlockReason, generatorUpstreamNodes } from "./generatorReadiness.ts";

export type GuidedWorkflowRoute =
  | "/"
  | "/canvas-mvp"
  | "/workflow/assets"
  | "/workflow/image-processing"
  | "/workflow/prompts"
  | "/workflow/generator"
  | "/workflow/compose"
  | "/workflow/sound"
  | "/workflow/output"
  | "/workflow/tasks"
  | "/workflow/asset-library-review"
  | "/workflow/weekly-plan"
  | "/workflow/clip-review";

const guidedWorkflowSteps = [
  { path: "/workflow/assets", step: "1", label: "素材与菜品" },
  { path: "/workflow/image-processing", step: "2", label: "图片处理" },
  { path: "/workflow/prompts", step: "3", label: "动态效果" },
  { path: "/workflow/generator", step: "4", label: "生成视频片段" },
  { path: "/workflow/compose", step: "5", label: "成片合成" },
  { path: "/workflow/sound", step: "6", label: "声音与文字" },
  { path: "/workflow/output", step: "7", label: "成片结果" },
] as const;

export type WorkflowStepProgress = {
  complete: boolean;
  unlocked: boolean;
};

export type WorkflowProgress = {
  steps: WorkflowStepProgress[];
  allStepsComplete: boolean;
};

export function deriveWorkflowProgress(nodes: WorkflowNode[], candidateClips: TimelineClip[], workspaces: ComposeWorkspace[], edges: Edge[] = []): WorkflowProgress {
  const generators = nodes.filter(node => node.data.kind === "generator");
  const chains = generators.map(generator => ({ generator, ...generatorUpstreamNodes(generator, nodes, edges) }));
  // A draft can contain several dishes at different stages. The workflow step
  // is unlocked once at least one real chain reaches that stage; each card
  // still enforces its own upstream checks before it can be processed/generated.
  const assetsComplete = chains.some(chain => Boolean(chain.input?.data.imagePreview));
  const imageProcessingComplete = chains.some(chain => Boolean(chain.process?.data.processedImagePreview));
  // 第 3 步不再要人点「实时装配」：效果是按冷热现算的，算得出、生成没被拦下就算做完。
  // 原来还要求 status === "已装配"，运营走到这一页会卡住，因为那颗按钮只是把状态改个名字。
  const promptsComplete = chains.some(chain => Boolean(
    chain.prompt
    && generatorGenerationBlockReason(chain.generator, nodes, edges) === null,
  ));
  const clipsComplete = candidateClips.some(clip => Boolean(clip.generatorNodeId && clip.sourcePath && clip.isSelected !== false));
  const compositionComplete = workspaces.some(workspace => workspace.job?.status === "done");
  const soundComplete = workspaces.some(workspace => workspace.finalJob?.status === "done");
  const completedSteps = [assetsComplete, imageProcessingComplete, promptsComplete, clipsComplete, compositionComplete, soundComplete, soundComplete];
  const steps = completedSteps.map((complete, index) => ({ complete, unlocked: index === 0 || completedSteps.slice(0, index).every(Boolean) }));
  return { steps, allStepsComplete: completedSteps.slice(0, 6).every(Boolean) };
}

export function firstIncompleteWorkflowRoute(progress: WorkflowProgress): GuidedWorkflowRoute {
  const firstIncomplete = progress.steps.findIndex(step => !step.complete);
  return guidedWorkflowSteps[firstIncomplete < 0 ? guidedWorkflowSteps.length - 1 : firstIncomplete].path;
}

export function isWorkflowRouteUnlocked(route: GuidedWorkflowRoute, progress: WorkflowProgress): boolean {
  if (route === "/") return true; // 首页是入口，任何时候都能回
  const stepIndex = guidedWorkflowSteps.findIndex(item => item.path === route);
  if (stepIndex >= 0) return progress.steps[stepIndex].unlocked;
  if (route === "/workflow/asset-library-review") return progress.steps[0].unlocked;
  if (route === "/workflow/clip-review") return progress.steps[3].unlocked;
  return progress.allStepsComplete;
}

export function lockedStepHint(stepIndex: number): string {
  const previous = guidedWorkflowSteps[stepIndex - 1];
  return previous ? `请先完成第 ${previous.step} 步「${previous.label}」` : "";
}
