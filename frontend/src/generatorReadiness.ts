import type { Edge } from "@xyflow/react";
import type { TimelineClip, WorkflowNode } from "./model";
import { promptAssemblyBlockReason, promptUpstreamNodes } from "./promptAssemblyReadiness.ts";

export type GeneratorUpstreamNodes = {
  prompt?: WorkflowNode;
  process?: WorkflowNode;
  input?: WorkflowNode;
};

/** Resolve the prompt, image-processing and input nodes connected to one generator. */
export function generatorUpstreamNodes(generatorNode: WorkflowNode, nodes: WorkflowNode[], edges: Edge[]): GeneratorUpstreamNodes {
  if (generatorNode.data.kind !== "generator") return {};
  const prompt = edges
    .filter(edge => edge.target === generatorNode.id)
    .map(edge => nodes.find(node => node.id === edge.source))
    .find(node => node?.data.kind === "prompt");
  if (!prompt) return {};
  const { process, input } = promptUpstreamNodes(prompt, nodes, edges);
  return { prompt, process, input };
}

/** Explain why a generator cannot be submitted yet. */
export function generatorGenerationBlockReason(generatorNode: WorkflowNode, nodes: WorkflowNode[], edges: Edge[]): string | null {
  if (generatorNode.data.kind !== "generator") return "当前节点不是视频生成节点";
  const { prompt, process, input } = generatorUpstreamNodes(generatorNode, nodes, edges);
  if (!prompt) return "请先连接对应的提示词节点";
  if (!input) return "请先连接对应的素材节点";
  if (!input.data.imagePreview) return "请先上传该菜品的原始图片";
  if (!process) return "请先连接对应的图片处理节点";
  if (!process.data.processedImagePreview) {
    return process.data.status === "处理失败"
      ? "对应图片处理失败，请先到图片处理页面重试"
      : "请先完成该菜品的图片处理";
  }
  return promptAssemblyBlockReason(prompt, nodes, edges);
}

/** Whether a generator has a selected, locally available clip version. */
export function hasSelectedGeneratedClip(generatorNodeId: string, clips: TimelineClip[]): boolean {
  return clips.some(clip => clip.generatorNodeId === generatorNodeId && Boolean(clip.sourcePath) && clip.isSelected !== false);
}
