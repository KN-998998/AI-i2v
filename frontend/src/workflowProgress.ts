import type { ComposeWorkspace, TimelineClip, WorkflowNode } from "./model";

export type GuidedWorkflowRoute =
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
  { path: "/workflow/prompts", step: "3", label: "提示词装配" },
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

export function deriveWorkflowProgress(nodes: WorkflowNode[], candidateClips: TimelineClip[], workspaces: ComposeWorkspace[]): WorkflowProgress {
  const assetsComplete = nodes.some(node => node.data.kind === "input" && Boolean(node.data.imagePreview));
  const imageProcessingComplete = nodes.some(node => node.data.kind === "image_process" && Boolean(node.data.processedImagePreview));
  const promptsComplete = nodes.some(node => node.data.kind === "prompt" && node.data.status === "已装配");
  const clipsComplete = candidateClips.some(clip => Boolean(clip.generatorNodeId && clip.sourcePath && clip.isSelected !== false));
  const compositionComplete = workspaces.some(workspace => workspace.job?.status === "done");
  const soundComplete = workspaces.some(workspace => workspace.finalJob?.status === "done");
  const completedSteps = [assetsComplete, imageProcessingComplete, promptsComplete, clipsComplete, compositionComplete, soundComplete, soundComplete];
  const steps = completedSteps.map((complete, index) => ({ complete, unlocked: index === 0 || completedSteps[index - 1] }));
  return { steps, allStepsComplete: completedSteps.slice(0, 6).every(Boolean) };
}

export function firstIncompleteWorkflowRoute(progress: WorkflowProgress): GuidedWorkflowRoute {
  const firstIncomplete = progress.steps.findIndex(step => !step.complete);
  return guidedWorkflowSteps[firstIncomplete < 0 ? guidedWorkflowSteps.length - 1 : firstIncomplete].path;
}

export function isWorkflowRouteUnlocked(route: GuidedWorkflowRoute, progress: WorkflowProgress): boolean {
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
