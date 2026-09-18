import { useWorkflowStore } from "../workflowStore";
import { navigate, workflowRoutes, type WorkflowRoute } from "../router";
import { deriveWorkflowProgress, lockedStepHint } from "../workflowProgress";
import { requestTutorial } from "../tutorial";

export function Pipeline({ path, collapsed, onToggle }: { path: WorkflowRoute; collapsed: boolean; onToggle: () => void }) {
  const nodes = useWorkflowStore(state => state.nodes);
  const edges = useWorkflowStore(state => state.edges);
  const candidates = useWorkflowStore(state => state.candidateClips);
  const workspaces = useWorkflowStore(state => state.composeWorkspaces);
  const progress = deriveWorkflowProgress(nodes, candidates, workspaces, edges);
  // 流程画布总览、任务中心、周计划生产是辅助工作台，不参与制作步骤的顺序解锁，始终可访问。
  // 制作流程以一条竖向进度线展示全部 7 步：完成的实心点可点回改，当前步是唯一的高亮卡片，
  // 未解锁的只有空心点和浅灰名字——新手一眼看到走到哪、还剩几步，又不会被锁图标和灰卡片刷屏。
  const steps = workflowRoutes.map((item, index) => ({ item, index, progress: progress.steps[index]! }));
  return <aside id="pipeline-navigation" className="pipeline" aria-label="生产工作台导航">
    <button type="button" className="pipeline-toggle" onClick={onToggle} aria-label={collapsed ? "展开左侧菜单" : "收起左侧菜单"} aria-controls="pipeline-navigation" aria-expanded={!collapsed} title={collapsed ? "展开左侧菜单" : "收起左侧菜单"}><span aria-hidden="true">{collapsed ? "»" : "«"}</span><span className="pipeline-toggle-copy">{collapsed ? "展开" : "收起菜单"}</span></button>
    <div className="pipeline-heading"><span className="pipeline-kicker">PROJECT FLOW</span><strong>生产工作台</strong><small>从素材到最终成片</small></div>
    <button type="button" className="pipeline-tutorial-button" onClick={() => requestTutorial(path)}><span aria-hidden="true">?</span><span><strong>使用教程</strong><small>查看当前页面或步骤教学</small></span></button>
    <button type="button" className={`canvas-link ${path === "/canvas-mvp" ? "active" : ""}`} onClick={() => navigate("/canvas-mvp")} title="流程画布总览"><span className="canvas-link-icon">⌘</span><span><strong>流程画布总览</strong><small>节点与连接关系</small></span></button>
    <TaskCenterLink path={path} />
    <button type="button" className={`task-center-link ${path === "/workflow/weekly-plan" ? "active" : ""}`} onClick={() => navigate("/workflow/weekly-plan")} title="周计划生产"><span className="task-center-link-icon">周</span><span><strong>周计划生产</strong><small>配置自动选材与生成计划</small></span></button>
    <div className="pipeline-group-label"><span>01—07</span><span>制作流程</span></div>
    <ol className="step-line">{steps.map(({ item, index, progress: stepProgress }) => <StepLineItem key={item.path} item={item} active={path === item.path} progress={stepProgress} stepIndex={index} />)}</ol>
    <div className="pipeline-footer"><span className="footer-dot" />草稿自动保存<div>每 30 秒同步片段库</div></div>
  </aside>;
}

function TaskCenterLink({ path }: { path: WorkflowRoute }) {
  const workspaces = useWorkflowStore(state => state.composeWorkspaces);
  const activeTasks = workspaces.filter(item => [item.job?.status, item.finalJob?.status].some(status => ["queued", "running", "polling", "downloading", "analyzing", "retrying"].includes(status ?? ""))).length;
  return <button type="button" className={`task-center-link ${path === "/workflow/tasks" ? "active" : ""}`} onClick={() => navigate("/workflow/tasks")} title="任务中心"><span className="task-center-link-icon">↗</span><span><strong>任务中心</strong><small>{activeTasks ? `${activeTasks} 个任务处理中` : "查看全部任务状态"}</small></span>{activeTasks > 0 && <b>{activeTasks}</b>}</button>;
}

function PipelineTutorialButton({ item }: { item: typeof workflowRoutes[number] }) {
  return <button type="button" className="pipeline-step-tutorial" onClick={() => requestTutorial(item.path)} aria-label={`查看${item.label}教学`} title={`查看${item.label}教学`}>?</button>;
}

function StepLineItem({ item, active, progress, stepIndex }: { item: typeof workflowRoutes[number]; active: boolean; progress: { complete: boolean; unlocked: boolean }; stepIndex: number }) {
  const setSelection = useWorkflowStore(state => state.setSelection);
  const setActivePanel = useWorkflowStore(state => state.setActivePanel);
  const selectStage = () => {
    if (!progress.unlocked) return;
    if (item.path === "/workflow/image-processing") setSelection("image_process");
    if (item.path === "/workflow/sound") { setActivePanel("voice"); setSelection("sound"); }
    if (item.path === "/workflow/compose" || item.path === "/workflow/output") setSelection("output");
    navigate(item.path);
  };
  // 显示状态以“解锁”为先：草稿里可能残留后面步骤的旧产物（比如早前生成过的片段），
  // 让 complete 为真但步骤其实还进不去——这种一律画成空心点，与“下一步”按钮的判断保持一致。
  const state = active ? "active" : !progress.unlocked ? "todo" : progress.complete ? "done" : "open";
  const hint = !progress.unlocked ? lockedStepHint(stepIndex) : state === "done" ? "已完成，可回去修改" : active ? "当前步骤" : "可以开始";
  if (active) {
    return <li className="step-line-item active"><span className="step-dot" aria-hidden="true" /><div className="pipeline-step-row"><button type="button" className="step-line-card" aria-current="step" onClick={selectStage}><strong>{item.step}. {item.label}</strong><small>{hint}</small></button><PipelineTutorialButton item={item} /></div></li>;
  }
  return <li className={`step-line-item ${state}`}><span className="step-dot" aria-hidden="true" /><button type="button" className="step-line-link" disabled={!progress.unlocked} aria-disabled={!progress.unlocked} title={hint} onClick={selectStage}>{item.label}</button></li>;
}
