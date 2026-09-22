import { clips, dataFor, initialEdges, initialNodes, soundConfigFromData } from "./model.ts";

// 新草稿默认用默认曲库（assets/bgm/default/ 里那几首）；模式由 soundConfigFromData 算出来。
const defaultSoundConfig = soundConfigFromData(dataFor("sound"), "默认曲库", "");

export const workflowSeed = {
  nodes: initialNodes,
  edges: initialEdges,
  timeline: [clips[0], clips[2], clips[3]],
  candidateClips: [clips[0], clips[2], clips[3]],
  composeBatchCount: 1,
  // 参考片的镜头数中位是 6（p10 也是 6，见 docs/reference_profile.json），原来默认 3 段太单调。
  composeClipCount: 6,
  composeWorkspaces: [{ id: "compose_1", title: "成片 1", clips: [clips[0], clips[2], clips[3]], job: null, soundConfig: defaultSoundConfig }],
  bgmName: "默认曲库",
};
