import type { Edge } from "@xyflow/react";
import type { WorkflowNode } from "./model.ts";
import { assemblePrompt } from "./promptAssembler.ts";
import { effectivePromptConfig } from "./effectRules.ts";

/** Return the immediate image-processing and input ancestors for a prompt node. */
export function promptUpstreamNodes(promptNode: WorkflowNode, nodes: WorkflowNode[], edges: Edge[]) {
  if (promptNode.data.kind !== "prompt") return { process: undefined, input: undefined };
  const processId = edges
    .filter(edge => edge.target === promptNode.id)
    .map(edge => nodes.find(node => node.id === edge.source))
    .find(node => node?.data.kind === "image_process")?.id;
  const process = processId ? nodes.find(node => node.id === processId) : undefined;
  const inputId = process
    ? edges
      .filter(edge => edge.target === process.id)
      .map(edge => nodes.find(node => node.id === edge.source))
      .find(node => node?.data.kind === "input")?.id
    : undefined;
  const input = inputId ? nodes.find(node => node.id === inputId) : undefined;
  return { process, input };
}

export function promptAssemblyBlockReason(promptNode: WorkflowNode, nodes: WorkflowNode[], edges: Edge[]): string | null {
  if (promptNode.data.kind !== "prompt") return "当前节点不是提示词节点";
  const { input, process } = promptUpstreamNodes(promptNode, nodes, edges);
  if (!input) return "未连接对应的素材节点";
  if (!input.data.imagePreview) return "请先上传该菜品的原始图片";
  if (!process) return "未连接对应的图片处理节点";
  if (!process.data.processedImagePreview) {
    return process.data.status === "处理失败"
      ? "对应图片处理失败，请先到图片处理页面重试"
      : "请先完成该菜品的图片处理";
  }
  // 校验的是这道菜实际会用的配置（按它自己的冷热现算），不是提示词节点里存着的那一份：
  // 存着的那份可能是在知道冷热之前建的，校验通过、生成出来却是热菜写法。
  const result = assemblePrompt(effectivePromptConfig(promptNode.data, input.data));
  if (result.blocked) return `提示词校验未通过：${result.errors[0]?.message ?? "请修正配置"}`;
  return null;
}

/** A prompt can be assembled only when its own upstream chain and fields are ready. */
export function canAssemblePromptNode(promptNode: WorkflowNode, nodes: WorkflowNode[], edges: Edge[]): boolean {
  return promptAssemblyBlockReason(promptNode, nodes, edges) === null;
}
