export type WorkflowRoute =
  | "/canvas-mvp"
  | "/workflow/assets"
  | "/workflow/prompts"
  | "/workflow/generator"
  | "/workflow/compose"
  | "/workflow/sound"
  | "/workflow/output";

export const workflowRoutes: Array<{ path: WorkflowRoute; label: string; step: string }> = [
  { path: "/workflow/assets", label: "素材与菜品", step: "1" },
  { path: "/workflow/prompts", label: "提示词装配", step: "2" },
  { path: "/workflow/generator", label: "生成视频片段", step: "3" },
  { path: "/workflow/compose", label: "成片合成", step: "4" },
  { path: "/workflow/sound", label: "声音与文字", step: "5" },
  { path: "/workflow/output", label: "成片结果", step: "6" },
];

export function routeForPath(pathname: string): WorkflowRoute {
  if (pathname === "/" || pathname === "/canvas-mvp") return "/canvas-mvp";
  if (pathname === "/workflow/timeline") return "/workflow/compose";
  return workflowRoutes.some(item => item.path === pathname) ? pathname as WorkflowRoute : "/canvas-mvp";
}

export function navigate(path: WorkflowRoute): void {
  if (window.location.pathname === path) return;
  window.history.pushState({}, "", path);
  window.dispatchEvent(new Event("workflow:navigate"));
}
