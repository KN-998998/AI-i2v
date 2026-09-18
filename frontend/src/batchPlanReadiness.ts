import { nodeCatalog, type NodeKind } from "./model.ts";

/**
 * 批量生产开工前的检查。
 *
 * 批量生产每天要跑的那份草稿，是后端从「样板草稿」里按类型逐个复制节点拼出来的
 * （web/services/weekly_plans.py::_create_daily_draft），缺任何一类节点都会在
 * 第二天早上执行时才报错。素材和背景同理：数量不够只有到抽菜那一步才发现。
 * 这个文件把这些检查提前到点「开始批量生产」之前，用大白话说清楚缺什么、去哪儿补。
 */

/** 拼每日草稿时会逐类复制的节点，缺一类就跑不起来。 */
export const REQUIRED_TEMPLATE_KINDS: NodeKind[] = ["input", "image_process", "prompt", "generator", "output", "sound"];

/** 拦路的原因该去哪一页解决。null 表示就在本页改。 */
export type BatchBlockerAction = "library" | "background" | "template" | null;

export type BatchLibrarySummary = {
  /** 素材库里分类已确认、可以直接参与抽取的菜品数。 */
  dishCount: number;
  /** 扣掉最近 3 天已被其他计划预留后，今天还能抽的菜品数。 */
  availableCount: number;
  /** 还没确认分类、暂时抽不到的菜品数。 */
  pendingCount: number;
  /** 可用的门店背景图张数。 */
  backgroundCount: number;
};

export type BatchReadinessInput = {
  loading: boolean;
  /** 用整理好的素材库时传摘要；改用自定义文件夹时传 null。 */
  library: BatchLibrarySummary | null;
  /** 改用自定义文件夹时传这两个路径，否则传 null。 */
  customRoots: { asset: string; background: string } | null;
  missingKinds: NodeKind[];
  /** 这次计划每天要抽多少道菜。 */
  candidateCount: number;
  clipsPerVideo: number;
};

export type BatchReadiness = {
  ok: boolean;
  /** 不能开工的原因；空串表示能开工。 */
  blocker: string;
  action: BatchBlockerAction;
  /** 能开工、但值得先知道的一句话。 */
  note: string;
  /** 按库存算，每天最多能出几条成片。 */
  maxVideosPerDay: number;
};

function templateNames(kinds: NodeKind[]): string {
  return kinds.map(kind => nodeCatalog[kind].title).join("、");
}

export function missingTemplateKinds(nodes: Array<{ data: { kind: NodeKind } }>): NodeKind[] {
  const present = new Set(nodes.map(node => node.data.kind));
  return REQUIRED_TEMPLATE_KINDS.filter(kind => !present.has(kind));
}

export function batchPlanReadiness(input: BatchReadinessInput): BatchReadiness {
  const { library, customRoots, missingKinds, candidateCount, clipsPerVideo } = input;
  const maxVideosPerDay = clipsPerVideo > 0 && library ? Math.floor(library.dishCount / clipsPerVideo) : 0;
  const blocked = (blocker: string, action: BatchBlockerAction, note = ""): BatchReadiness => ({ ok: false, blocker, action, note, maxVideosPerDay });
  if (input.loading) return blocked("正在读取素材库…", null);
  if (missingKinds.length) return blocked(`样板里缺少「${templateNames(missingKinds)}」，每天的草稿拼不出来。先把样板补齐。`, "template");
  if (customRoots) {
    if (!customRoots.asset.trim() || !customRoots.background.trim()) return blocked("先填好菜品素材库和背景素材库的文件夹。", null);
    return { ok: true, blocker: "", action: null, note: "用的是自定义文件夹，菜品数量够不够要到开工时才知道。", maxVideosPerDay: 0 };
  }
  if (!library) return blocked("没读到素材库情况，刷新页面再试一次。", null);
  // 「待确认」的菜抽不到，但补一句就行，不拦人。
  const note = library.pendingCount > 0 ? `素材库里还有 ${library.pendingCount} 道菜没确认分类，确认之后也能参与抽取。` : "";
  if (library.dishCount === 0) return blocked("素材库里还没有确认好分类的菜品，先去整理素材库。", "library");
  if (library.backgroundCount === 0) return blocked("还没有可用的门店背景图，先去「图片处理」那一步传几张。", "background", note);
  if (maxVideosPerDay < 1) return blocked(`素材库一共只有 ${library.dishCount} 道菜，连一条成片（要 ${clipsPerVideo} 道）都凑不齐。先去素材库补菜。`, "library", note);
  if (library.dishCount < candidateCount) {
    return blocked(`每天要抽 ${candidateCount} 道菜，素材库一共只有 ${library.dishCount} 道。把每天条数降到 ${maxVideosPerDay} 条，或者去素材库补菜。`, "library", note);
  }
  // 预留是按日期滚动的：今天被占的菜，过两天就放出来了，所以只提醒不拦。
  const reserved = library.dishCount - library.availableCount;
  const crowded = library.availableCount < candidateCount
    ? `最近 3 天已有 ${reserved} 道菜被别的计划预留，从今天开工可能抽不满；往后排几天就没这个问题。`
    : "";
  return { ok: true, blocker: "", action: null, note: [note, crowded].filter(Boolean).join(" "), maxVideosPerDay };
}
