// ---------------------------------------------------------------------------
// 片段库和当前草稿的对账。
//
// 起因（2026-09-21 实测）：新建草稿一打开，候选池里就多了片段库里全部 20 条片段
// （test_01…10、Kling测试菜、别的草稿生成的玉子寿司……），「成片 1」里预先塞了 3 条，
// 第 4 步还没生成就打了勾，「智能推荐方案」还会把测试片段挑进成片。两个根源：
//   ① loadClipLibrary 把整个片段库并进候选池；
//   ② 占位只按 generatorNodeId 配对，而每份草稿都有一个叫 "clips" 的生成节点，
//      于是别的草稿的成品顶替了本草稿的占位。
//
// 现在片段库里的每条片段都带 draftId（后端 _build_clip 写进 manifest），只有本草稿的
// 片段才进候选池、才能顶替占位。别的草稿的、以及没来历的本地片段（老 manifest 没有
// 这个键），只在第 4 步「本地片段」那块看得到，不会自己跑进成片。
// ---------------------------------------------------------------------------
import { reconcileStalePendingGeneratorClips, type ClipLibraryItem, type TimelineClip } from "./model.ts";

/** 片段库里属于这份草稿的那些片段。没有 draftId 的（老片段）一律不算。 */
export function ownDraftClips(available: ClipLibraryItem[], draftId: string): ClipLibraryItem[] {
  return available.filter(clip => Boolean(clip.draftId) && clip.draftId === draftId);
}

function sameFile(item: TimelineClip, candidate: TimelineClip): boolean {
  return Boolean(
    (item.sourcePath && candidate.sourcePath === item.sourcePath)
    || (item.filename && candidate.filename === item.filename),
  );
}

/**
 * 草稿里存着的这一条，在片段库里找到同一个文件就用库里的元数据刷新（质量分、预览地址……）。
 * 身份和裁剪以草稿为准：库里那份没有人在这份草稿里做过的裁剪和勾选。
 * 找不到就原样返回同一个对象——新草稿的种子占位要和种子一模一样。
 */
function refreshFromLibrary(item: TimelineClip, available: ClipLibraryItem[]): TimelineClip {
  const match = available.find(candidate => sameFile(item, candidate));
  if (!match) return item;
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
    // 裁剪区间只要草稿写过就以草稿为准，也顺带保住了「确认裁剪」这个标记还没上线时留下的裁剪。
    ...(item.sourceStartSeconds !== undefined || item.sourceEndSeconds !== undefined ? {
      sourceStartSeconds: item.sourceStartSeconds,
      sourceEndSeconds: item.sourceEndSeconds,
      timelineDuration: item.timelineDuration,
      trimConfirmed: item.trimConfirmed,
    } : {}),
  };
}

export function reconcileDraftClips(input: {
  draftId: string;
  candidateClips: TimelineClip[];
  timeline: TimelineClip[];
  available: ClipLibraryItem[];
  activeGenerationNodeIds: ReadonlySet<string>;
}): { candidateClips: TimelineClip[]; timeline: TimelineClip[] } {
  const mine = ownDraftClips(input.available, input.draftId);
  // 刷新元数据时看整个片段库（草稿里存着的片段本来就在库里，只是可能重新分析过了）；
  // 顶替占位和追加新片段时只看 mine，别的草稿的成品不许进来。
  const refresh = (items: TimelineClip[]) => items.map(item => refreshFromLibrary(item, input.available));
  const candidateClips = reconcileStalePendingGeneratorClips(refresh(input.candidateClips), mine, input.activeGenerationNodeIds, "replace");
  const timeline = reconcileStalePendingGeneratorClips(refresh(input.timeline), mine, input.activeGenerationNodeIds, "replace");
  const missing = mine.filter(clip => !candidateClips.some(item => item.id === clip.id || sameFile(clip, item)));
  return {
    candidateClips: missing.length ? [...candidateClips, ...missing.map(clip => ({ ...clip }))] : candidateClips,
    timeline,
  };
}
