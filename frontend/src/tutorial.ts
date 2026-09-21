import type { WorkflowRoute } from "./router";

export const TUTORIAL_VERSION = "tutorial-v1";
export const TUTORIAL_STORAGE_KEY = `restaurant-video.${TUTORIAL_VERSION}.dismissed`;

export type TutorialKind = "welcome" | "project" | "workflow-step" | "complete";

export type TutorialChapter = {
  id: string;
  kind: TutorialKind;
  title: string;
  eyebrow: string;
  description: string;
  route?: WorkflowRoute;
  screenshot?: string;
  bullets: string[];
  checkpoint?: string;
  warning?: string;
};

const stepContent: Array<{ route: WorkflowRoute; title: string; description: string; screenshot: string; bullets: string[]; checkpoint: string; warning: string }> = [
  { route: "/workflow/assets", title: "素材与菜品", description: "上传菜品首帧，填写菜名和分类，让后续步骤知道这条素材属于谁。", screenshot: "step-1-assets.png", bullets: ["上传首帧或从素材库选择已有图片。", "填写菜名、冷热属性、菜品分类和画面主体类型。", "保存后第 2 步会自动解锁；原始素材始终保留。"], checkpoint: "至少有一个素材节点包含有效图片。", warning: "不要只填写菜名而跳过图片上传，否则后续图片处理无法开始。" },
  { route: "/workflow/image-processing", title: "图片处理", description: "将菜品主体与背景模板合成视频首帧；人物或手部素材可以保留原图。", screenshot: "step-2-image-processing.png", bullets: ["普通菜品先选择背景模板，再执行抠图与合成。", "人物、厨师或手部素材选择保留原图模式。", "检查处理结果后再进入动态效果。"], checkpoint: "处理节点出现有效的处理后首帧。", warning: "点击节点卡片上的其他按钮不会解锁本步骤，必须完成真实图片处理。" },
  { route: "/workflow/prompts", title: "动态效果", description: "这一步决定第 2 步那张首帧怎么动：镜头怎么走、哪里在动、哪里保持不动。工具已经按每道菜的冷热配好，一般看一眼就过。", screenshot: "step-3-prompts.png", bullets: ["每道菜一张卡片，写着配了什么效果、为什么这样配；点卡片看这道菜会怎么动。", "冷菜默认光泽流转，热菜默认热气升腾，原图有手或厨师的让人保持不动。", "不合适就在右边点一个换掉；换了之后批量生产里同类的菜也跟着换。"], checkpoint: "每道菜都显示“已配好”。", warning: "冷菜看不到“热气升腾”、没有手的图看不到“淋酱”不是出错：那些效果这道菜用不了，硬配出来生成会被拦下。" },
  { route: "/workflow/generator", title: "生成视频片段", description: "使用已确认的提示词提交 Kling 任务，下载真实 MP4 并选择当前使用版本。", screenshot: "step-4-generator.png", bullets: ["确认 3 秒、1080p、无声和单分镜参数。", "等待任务完成并自动下载片段。", "同一素材可保留多个版本，但只有当前版本进入候选池。"], checkpoint: "至少一个当前版本片段已下载并关联生成节点。", warning: "生成任务完成不等于片段可合成，必须确认本地真实 MP4 已关联。" },
  { route: "/workflow/compose", title: "成片合成", description: "排序、裁剪候选片段，生成一套或多套无声成片方案。", screenshot: "step-5-compose.png", bullets: ["先使用智能推荐或随机生成方案。", "拖动片段调整顺序，设置精彩区间。", "运行预检确认所有片段都是真实文件。"], checkpoint: "至少一个工作区的无声合成任务完成。", warning: "未关联真实 MP4 的历史片段不会计入可合成候选池。" },
  { route: "/workflow/sound", title: "声音与文字", description: "为无声成片配置 BGM、人声和时间轴文字，生成最终有声视频。", screenshot: "step-6-sound.png", bullets: ["上传或选择 BGM，并调整音量。", "按时间段配置人声和画面文字。", "确认字幕位置、字体和语音绑定关系。"], checkpoint: "声音与文字合成任务完成。", warning: "声音步骤必须建立在无声成片完成之后，不能直接从动态效果那一步跳入。" },
  { route: "/workflow/output", title: "成片结果", description: "预览最终文件，完成人工审核后下载或交付给运营团队。", screenshot: "step-7-output.png", bullets: ["查看最终视频和任务状态。", "检查画面、声音、文字和品牌规范。", "审核通过后下载并记录交付结果。"], checkpoint: "最终成片可预览并完成审核。", warning: "导出完成仍建议人工检查，不以任务状态代替内容审核。" },
];

export const tutorialChapters: TutorialChapter[] = [
  { id: "welcome", kind: "welcome", title: "欢迎使用 AI 图生视频工作流", eyebrow: "WELCOME", description: "用一套可追踪的流程，把菜品素材稳定地变成可交付的竖版短视频。", bullets: ["适合餐饮运营、品牌和内容制作同事。", "每一步都有明确产物，完成前一步才会解锁下一步。", "随时可以从顶部“使用教程”重新打开本教程。"] },
  { id: "project", kind: "project", title: "项目介绍", eyebrow: "PROJECT OVERVIEW", description: "这是一个面向内部生产团队的图生视频工作台，集中管理素材、提示词、生成任务和成片交付。", screenshot: "project-overview.png", bullets: ["左侧是工作台导航，前三个辅助页面始终可访问。", "中间画布用于查看节点关系；编辑会从右侧抽屉打开。", "步骤页面负责真实操作，状态会自动同步回画布。"] },
  ...stepContent.map((step, index) => ({ id: `step-${index + 1}`, kind: "workflow-step" as const, eyebrow: `STEP ${index + 1} / 7`, ...step })),
  { id: "complete", kind: "complete", title: "准备开始制作", eyebrow: "YOU ARE READY", description: "记住：先完成素材，再按顺序推进。遇到不确定的地方，可以随时打开对应步骤教学。", bullets: ["从左侧第 1 步“素材与菜品”开始。", "每一步完成后，下一步会自动解锁。", "顶部“使用教程”入口会一直保留。"] },
];

export function chapterIndexForRoute(route: WorkflowRoute): number {
  const index = tutorialChapters.findIndex(chapter => chapter.route === route);
  return index >= 0 ? index : 1;
}

export function isTutorialDismissed(): boolean {
  try { return window.localStorage.getItem(TUTORIAL_STORAGE_KEY) === "true"; } catch { return false; }
}

export function dismissTutorial(): void {
  try { window.localStorage.setItem(TUTORIAL_STORAGE_KEY, "true"); } catch { /* Storage is optional. */ }
}

/** Open the shared tutorial from any page without duplicating modal state. */
export function requestTutorial(route?: WorkflowRoute): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("tutorial:open", { detail: { route } }));
}
