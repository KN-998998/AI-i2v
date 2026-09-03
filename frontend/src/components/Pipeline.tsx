import { useWorkflowStore } from "../workflowStore";
import { navigate, workflowRoutes, type WorkflowRoute } from "../router";

export function Pipeline({ path }: { path: WorkflowRoute }) {
  return <aside className="pipeline"><button type="button" className={`canvas-link ${path === "/canvas-mvp" ? "active" : ""}`} onClick={() => navigate("/canvas-mvp")}>流程画布总览</button><div className="panel-label">WORKFLOW STEPS</div>{workflowRoutes.filter(item => item.path !== "/workflow/output").map(item => <PipelineItem key={item.path} item={item} active={path === item.path} />)}<div className="pipeline-divider" /><PipelineItem item={workflowRoutes[workflowRoutes.length - 1]} active={path === "/workflow/output"} /></aside>;
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
  const hint = item.path === "/workflow/compose" ? "选片、排序并合成" : item.path === "/workflow/sound" ? stepStatus === "ready" ? "可配置声音文字" : "等待无声成片" : item.path === "/workflow/output" ? stepStatus === "ready" ? "查看已生成成片" : "等待成片结果" : item.path === "/workflow/generator" ? stepStatus === "ready" ? "已有可用片段" : "待生成真实片段" : "独立操作页面";
  return <button type="button" className={`pipeline-item ${active ? "active" : ""} ${stepStatus === "ready" ? "done" : ""}`} onClick={selectStage}><span className="step-index">{item.step}</span><span>{item.label}<small>{hint}</small></span></button>;
}
