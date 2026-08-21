import { clips, initialEdges, initialNodes } from "./model";

export const workflowSeed = {
  nodes: initialNodes,
  edges: initialEdges,
  timeline: [clips[0], clips[2], clips[3]],
  bgmName: "默认 BGM",
};
