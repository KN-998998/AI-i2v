import { clips, dataFor, initialEdges, initialNodes, soundConfigFromData } from "./model";

const defaultSoundConfig = soundConfigFromData(dataFor("sound"), "默认 BGM", "");

export const workflowSeed = {
  nodes: initialNodes,
  edges: initialEdges,
  timeline: [clips[0], clips[2], clips[3]],
  candidateClips: [clips[0], clips[2], clips[3]],
  composeBatchCount: 1,
  composeClipCount: 3,
  composeWorkspaces: [{ id: "compose_1", title: "成片 1", clips: [clips[0], clips[2], clips[3]], job: null, soundConfig: defaultSoundConfig }],
  bgmName: "默认 BGM",
};
