import { useWorkflowStore } from "../workflowStore";
import { navigate, workflowRoutes, type WorkflowRoute } from "../router";

export function Pipeline({ path }: { path: WorkflowRoute }) {
  return <aside className="pipeline"><button type="button" className={`canvas-link ${path === "/canvas-mvp" ? "active" : ""}`} onClick={() => navigate("/canvas-mvp")}>流程画布总览</button><div className="panel-label">WORKFLOW STEPS</div>{workflowRoutes.filter(item => item.path !== "/workflow/output").map(item => <PipelineItem key={item.path} item={item} active={path === item.path} />)}<div className="pipeline-divider" /><PipelineItem item={workflowRoutes[workflowRoutes.length - 1]} active={path === "/workflow/output"} /></aside>;
}

function PipelineItem({ item, active }: { item: typeof workflowRoutes[number]; active: boolean }) {
  const setSelection = useWorkflowStore(state => state.setSelection);
  const setActivePanel = useWorkflowStore(state => state.setActivePanel);
  const selectStage = () => {
    if (item.path === "/workflow/sound") { setActivePanel("voice"); setSelection("sound"); }
    if (item.path === "/workflow/compose" || item.path === "/workflow/output") setSelection("output");
    navigate(item.path);
  };
  return <button type="button" className={`pipeline-item ${active ? "active" : ""}`} onClick={selectStage}><span className="step-index">{item.step}</span><span>{item.label}<small>{item.path === "/workflow/compose" ? "选片、排序并合成" : "独立操作页面"}</small></span></button>;
}
