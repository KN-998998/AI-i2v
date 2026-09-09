import { useWorkflowStore } from "../workflowStore";
import { navigate, workflowRoutes, type WorkflowRoute } from "../router";

export function Pipeline({ path, collapsed, onToggle }: { path: WorkflowRoute; collapsed: boolean; onToggle: () => void }) {
  return <aside id="pipeline-navigation" className="pipeline" aria-label="生产工作台导航">
    <button type="button" className="pipeline-toggle" onClick={onToggle} aria-label={collapsed ? "展开左侧菜单" : "收起左侧菜单"} aria-controls="pipeline-navigation" aria-expanded={!collapsed} title={collapsed ? "展开左侧菜单" : "收起左侧菜单"}><span aria-hidden="true">{collapsed ? "»" : "«"}</span><span className="pipeline-toggle-copy">{collapsed ? "展开" : "收起菜单"}</span></button>
    <div className="pipeline-heading"><span className="pipeline-kicker">PROJECT FLOW</span><strong>生产工作台</strong><small>从素材到最终成片</small></div>
    <button type="button" className={`canvas-link ${path === "/canvas-mvp" ? "active" : ""}`} onClick={() => navigate("/canvas-mvp")} title="流程画布总览"><span className="canvas-link-icon">⌘</span><span><strong>流程画布总览</strong><small>节点与连接关系</small></span></button>
    <TaskCenterLink path={path} />
    <button type="button" className={`task-center-link ${path === "/workflow/weekly-plan" ? "active" : ""}`} onClick={() => navigate("/workflow/weekly-plan")} title="周计划生产"><span className="task-center-link-icon">周</span><span><strong>周计划生产</strong><small>配置自动选材与生成计划</small></span></button>
    <div className="pipeline-group-label"><span>01—06</span><span>制作流程</span></div>
    {workflowRoutes.filter(item => item.path !== "/workflow/output").map(item => <PipelineItem key={item.path} item={item} active={path === item.path} />)}
    <div className="pipeline-divider" />
    <div className="pipeline-group-label output-label"><span>07</span><span>交付</span></div>
    <PipelineItem item={workflowRoutes[workflowRoutes.length - 1]} active={path === "/workflow/output"} />
    <div className="pipeline-footer"><span className="footer-dot" />草稿自动保存<div>每 30 秒同步片段库</div></div>
  </aside>;
}

function TaskCenterLink({ path }: { path: WorkflowRoute }) {
  const workspaces = useWorkflowStore(state => state.composeWorkspaces);
  const activeTasks = workspaces.filter(item => [item.job?.status, item.finalJob?.status].some(status => ["queued", "running", "polling", "downloading", "analyzing", "retrying"].includes(status ?? ""))).length;
  return <button type="button" className={`task-center-link ${path === "/workflow/tasks" ? "active" : ""}`} onClick={() => navigate("/workflow/tasks")} title="任务中心"><span className="task-center-link-icon">↗</span><span><strong>任务中心</strong><small>{activeTasks ? `${activeTasks} 个任务处理中` : "查看全部任务状态"}</small></span>{activeTasks > 0 && <b>{activeTasks}</b>}</button>;
}

function PipelineItem({ item, active }: { item: typeof workflowRoutes[number]; active: boolean }) {
  const setSelection = useWorkflowStore(state => state.setSelection);
  const setActivePanel = useWorkflowStore(state => state.setActivePanel);
  const candidates = useWorkflowStore(state => state.candidateClips);
  const workspaces = useWorkflowStore(state => state.composeWorkspaces);
  const hasCurrentGeneratedClip = candidates.some(clip => Boolean(clip.generatorNodeId && clip.sourcePath && clip.isSelected !== false));
  const hasComposedCurrentClip = workspaces.some(workspace => workspace.clips.some(clip => Boolean(clip.sourcePath && clip.isSelected !== false)));
  const stepStatus = item.path === "/workflow/generator"
    ? (hasCurrentGeneratedClip ? "ready" : "pending")
    : item.path === "/workflow/compose"
      ? (hasComposedCurrentClip ? "ready" : "pending")
      : item.path === "/workflow/sound"
        ? (workspaces.some(workspace => workspace.job?.status === "done") ? "ready" : "pending")
        : item.path === "/workflow/output"
          ? (workspaces.some(workspace => workspace.finalJob?.status === "done" || workspace.job?.status === "done") ? "ready" : "pending")
          : "ready";
  const selectStage = () => {
    if (item.path === "/workflow/image-processing") setSelection("image_process");
    if (item.path === "/workflow/sound") { setActivePanel("voice"); setSelection("sound"); }
    if (item.path === "/workflow/compose" || item.path === "/workflow/output") setSelection("output");
    navigate(item.path);
  };
  const hint = item.path === "/workflow/compose" ? "选片、排序并合成" : item.path === "/workflow/sound" ? stepStatus === "ready" ? "配置声音与文字" : "等待无声成片" : item.path === "/workflow/output" ? stepStatus === "ready" ? "查看已生成成片" : "等待成片结果" : item.path === "/workflow/generator" ? stepStatus === "ready" ? "已有可用片段" : "等待生成真实片段" : "进入独立操作页面";
  return <button type="button" className={`pipeline-item ${active ? "active" : ""} ${stepStatus === "ready" ? "done" : ""}`} onClick={selectStage} title={item.label}><span className="step-index">{item.step}</span><span className="pipeline-item-copy"><strong>{item.label}</strong><small>{hint}</small></span>{stepStatus === "ready" && <span className="step-check">✓</span>}</button>;
}
