import { useWorkflowStore } from "../workflowStore";
import { navigate, workflowRoutes, type WorkflowRoute } from "../router";
import { deriveWorkflowProgress, lockedStepHint } from "../workflowProgress";

export function Pipeline({ path, collapsed, onToggle }: { path: WorkflowRoute; collapsed: boolean; onToggle: () => void }) {
  const nodes = useWorkflowStore(state => state.nodes);
  const candidates = useWorkflowStore(state => state.candidateClips);
  const workspaces = useWorkflowStore(state => state.composeWorkspaces);
  const progress = deriveWorkflowProgress(nodes, candidates, workspaces);
  const overviewUnlocked = true;
  const tasksUnlocked = true;
  const weeklyPlanUnlocked = true;
  return <aside id="pipeline-navigation" className="pipeline" aria-label="生产工作台导航">
    <button type="button" className="pipeline-toggle" onClick={onToggle} aria-label={collapsed ? "展开左侧菜单" : "收起左侧菜单"} aria-controls="pipeline-navigation" aria-expanded={!collapsed} title={collapsed ? "展开左侧菜单" : "收起左侧菜单"}><span aria-hidden="true">{collapsed ? "»" : "«"}</span><span className="pipeline-toggle-copy">{collapsed ? "展开" : "收起菜单"}</span></button>
    <div className="pipeline-heading"><span className="pipeline-kicker">PROJECT FLOW</span><strong>生产工作台</strong><small>从素材到最终成片</small></div>
    <button type="button" disabled={!overviewUnlocked} className={`canvas-link ${path === "/canvas-mvp" ? "active" : ""} ${!overviewUnlocked ? "locked" : ""}`} onClick={() => navigate("/canvas-mvp")} title={overviewUnlocked ? "流程画布总览" : "完成全部制作步骤后解锁"}><span className="canvas-link-icon">{overviewUnlocked ? "⌘" : "🔒"}</span><span><strong>流程画布总览</strong><small>{overviewUnlocked ? "节点与连接关系" : "完成全部步骤后解锁"}</small></span></button>
    <TaskCenterLink path={path} unlocked={tasksUnlocked} />
    <button type="button" disabled={!weeklyPlanUnlocked} className={`task-center-link ${path === "/workflow/weekly-plan" ? "active" : ""} ${!weeklyPlanUnlocked ? "locked" : ""}`} onClick={() => navigate("/workflow/weekly-plan")} title={weeklyPlanUnlocked ? "周计划生产" : "完成全部制作步骤后解锁"}><span className="task-center-link-icon">{weeklyPlanUnlocked ? "周" : "🔒"}</span><span><strong>周计划生产</strong><small>{weeklyPlanUnlocked ? "配置自动选材与生成计划" : "完成全部步骤后解锁"}</small></span></button>
    <div className="pipeline-group-label"><span>01—06</span><span>制作流程</span></div>
    {workflowRoutes.filter(item => item.path !== "/workflow/output").map((item, index) => <PipelineItem key={item.path} item={item} active={path === item.path} progress={progress.steps[index]} stepIndex={index} />)}
    <div className="pipeline-divider" />
    <div className="pipeline-group-label output-label"><span>07</span><span>交付</span></div>
    <PipelineItem item={workflowRoutes[workflowRoutes.length - 1]} active={path === "/workflow/output"} progress={progress.steps[workflowRoutes.length - 1]} stepIndex={workflowRoutes.length - 1} />
    <div className="pipeline-footer"><span className="footer-dot" />草稿自动保存<div>每 30 秒同步片段库</div></div>
  </aside>;
}

function TaskCenterLink({ path, unlocked }: { path: WorkflowRoute; unlocked: boolean }) {
  const workspaces = useWorkflowStore(state => state.composeWorkspaces);
  const activeTasks = workspaces.filter(item => [item.job?.status, item.finalJob?.status].some(status => ["queued", "running", "polling", "downloading", "analyzing", "retrying"].includes(status ?? ""))).length;
  return <button type="button" disabled={!unlocked} className={`task-center-link ${path === "/workflow/tasks" ? "active" : ""} ${!unlocked ? "locked" : ""}`} onClick={() => navigate("/workflow/tasks")} title={unlocked ? "任务中心" : "完成全部制作步骤后解锁"}><span className="task-center-link-icon">{unlocked ? "↗" : "🔒"}</span><span><strong>任务中心</strong><small>{unlocked ? activeTasks ? `${activeTasks} 个任务处理中` : "查看全部任务状态" : "完成全部步骤后解锁"}</small></span>{unlocked && activeTasks > 0 && <b>{activeTasks}</b>}</button>;
}

function PipelineItem({ item, active, progress, stepIndex }: { item: typeof workflowRoutes[number]; active: boolean; progress: { complete: boolean; unlocked: boolean }; stepIndex: number }) {
  const setSelection = useWorkflowStore(state => state.setSelection);
  const setActivePanel = useWorkflowStore(state => state.setActivePanel);
  const selectStage = () => {
    if (!progress.unlocked) return;
    if (item.path === "/workflow/image-processing") setSelection("image_process");
    if (item.path === "/workflow/sound") { setActivePanel("voice"); setSelection("sound"); }
    if (item.path === "/workflow/compose" || item.path === "/workflow/output") setSelection("output");
    navigate(item.path);
  };
  const hint = !progress.unlocked ? lockedStepHint(stepIndex) : progress.complete ? "已完成，可随时返回修改" : "当前步骤，完成后解锁下一步";
  return <button type="button" disabled={!progress.unlocked} aria-disabled={!progress.unlocked} className={`pipeline-item ${active ? "active" : ""} ${progress.complete ? "done" : ""} ${!progress.unlocked ? "locked" : ""}`} onClick={selectStage} title={progress.unlocked ? item.label : hint}><span className="step-index">{progress.unlocked ? item.step : "🔒"}</span><span className="pipeline-item-copy"><strong>{item.label}</strong><small>{hint}</small></span>{progress.complete && <span className="step-check">✓</span>}</button>;
}
