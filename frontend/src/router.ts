export type WorkflowRoute =
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

// goal：每个步骤页顶部的一句话——这一步做什么、做完得到什么。写给第一次用的运营看，不解释实现。
export const workflowRoutes: Array<{ path: WorkflowRoute; label: string; step: string; goal: string }> = [
  { path: "/workflow/assets", label: "素材与菜品", step: "1", goal: "上传菜品图，填菜名和分类，告诉工具画面里有没有手或人。做完得到一份待处理的菜品清单。" },
  { path: "/workflow/image-processing", label: "图片处理", step: "2", goal: "把菜品从原图里抠出来，换到门店背景上。做完得到视频的第一帧。" },
  { path: "/workflow/prompts", label: "提示词装配", step: "3", goal: "给这道菜选一个动态效果（热气、淋酱、推近镜头……）。做完得到一段给 AI 的生成指令。" },
  { path: "/workflow/generator", label: "生成视频片段", step: "4", goal: "AI 按上一步的效果生成 3 秒动态片段，一道菜可以多生成几条挑最好的。做完得到可用片段。" },
  { path: "/workflow/compose", label: "成片合成", step: "5", goal: "把几道菜的片段拼成一条 12–15 秒的竖版视频。做完得到无声成片。" },
  { path: "/workflow/sound", label: "声音与文字", step: "6", goal: "加 BGM、旁白和字幕。做完得到可以直接发布的成片。" },
  { path: "/workflow/output", label: "成片结果", step: "7", goal: "预览、下载成片；不满意可以回第 6 步改声音和文字。" },
];

export function workflowStep(route: WorkflowRoute) {
  return workflowRoutes.find(item => item.path === route);
}

export function routeForPath(pathname: string): WorkflowRoute {
  if (pathname === "/" || pathname === "/canvas-mvp") return "/canvas-mvp";
  if (pathname === "/workflow/timeline") return "/workflow/compose";
  if (pathname === "/workflow/asset-library-review") return "/workflow/asset-library-review";
  if (pathname === "/workflow/tasks") return "/workflow/tasks";
  if (pathname === "/workflow/weekly-plan") return "/workflow/weekly-plan";
  if (pathname === "/workflow/clip-review") return "/workflow/clip-review";
  return workflowRoutes.some(item => item.path === pathname) ? pathname as WorkflowRoute : "/canvas-mvp";
}

export function navigate(path: WorkflowRoute): void {
  if (window.location.pathname === path) return;
  window.history.pushState({}, "", path);
  window.dispatchEvent(new Event("workflow:navigate"));
}
