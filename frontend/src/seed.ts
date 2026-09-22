import { createPendingGeneratorClip, dataFor, initialEdges, initialNodes, soundConfigFromData } from "./model.ts";

// 新草稿默认用默认曲库（assets/bgm/default/ 里那几首）；模式由 soundConfigFromData 算出来。
const defaultSoundConfig = soundConfigFromData(dataFor("sound"), "默认曲库", "");

// 「成片 1」只放一条绑在种子生成节点上的待生成占位。原来塞的是三条演示片段
// （炙烤三文鱼 / 天妇罗 / 刺身拼盘）：没有文件、永远「待下载」，又没绑生成节点，
// 自己生成的片段顶替不了它们，9/22 Patrick 得先 × 三次。绑上 clips 之后，
// 第一条真片一到就被 reconcileDraftClips 顶掉，不用人动手。
const placeholder = createPendingGeneratorClip("clips", 0);

export const workflowSeed = {
  nodes: initialNodes,
  edges: initialEdges,
  timeline: [placeholder],
  candidateClips: [placeholder],
  composeBatchCount: 1,
  // 参考片的镜头数中位是 6（p10 也是 6，见 docs/reference_profile.json），原来默认 3 段太单调。
  composeClipCount: 6,
  composeWorkspaces: [{ id: "compose_1", title: "成片 1", clips: [placeholder], job: null, soundConfig: defaultSoundConfig }],
  bgmName: "默认曲库",
};
