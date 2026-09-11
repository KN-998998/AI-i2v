import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Background, ConnectionLineType, Controls, MarkerType, MiniMap, ReactFlow, ReactFlowProvider, type Edge, type OnConnect } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { connectWouldCycle, nodeCatalog, type NodeKind, type WorkflowNode } from "./model";
import { useWorkflowStore } from "./workflowStore";
import { Inspector } from "./components/Inspector";
import { Pipeline } from "./components/Pipeline";
import { GeneratorPage, OutputPage, StepPage } from "./components/StepPages";
import { navigate, routeForPath, workflowRoutes, type WorkflowRoute } from "./router";
import { deriveWorkflowProgress, firstIncompleteWorkflowRoute, isWorkflowRouteUnlocked } from "./workflowProgress";
import { WorkflowNodeCard } from "./components/WorkflowNodeCard";
import { BatchComposePage } from "./components/BatchComposePage";
import { ImageProcessingPage } from "./components/ImageProcessingPage";
import { ManualAssetLibraryPage } from "./components/ManualAssetLibraryPage";
import { TaskCenterPage } from "./components/TaskCenterPage";
import { WeeklyPlanPage } from "./components/WeeklyPlanPage";
import { ClipReviewPage } from "./components/ClipReviewPage";

const nodeTypes = { workflow: WorkflowNodeCard };
const pipelinePreferenceKey = "restaurant-video.pipeline-collapsed";
const alwaysAvailableWorkspaceRoutes = new Set<WorkflowRoute>(["/canvas-mvp", "/workflow/tasks", "/workflow/weekly-plan"]);

function loadPipelinePreference() {
  try {
    return window.localStorage.getItem(pipelinePreferenceKey) === "true";
  } catch {
    return false;
  }
}

function useWorkflowPath(): WorkflowRoute {
  const resolvePath = () => {
    const nextPath = routeForPath(window.location.pathname);
    if (window.location.pathname === "/workflow/timeline") window.history.replaceState({}, "", "/workflow/compose");
    return nextPath;
  };
  const [path, setPath] = useState<WorkflowRoute>(resolvePath);
  useEffect(() => {
    const update = () => setPath(resolvePath());
    window.addEventListener("popstate", update);
    window.addEventListener("workflow:navigate", update);
    return () => { window.removeEventListener("popstate", update); window.removeEventListener("workflow:navigate", update); };
  }, []);
  return path;
}

function App() {
  const path = useWorkflowPath();
  const loadDraft = useWorkflowStore(state => state.loadDraft);
  const loadClipLibrary = useWorkflowStore(state => state.loadClipLibrary);
  const saveDraft = useWorkflowStore(state => state.saveDraft);
  const hydrated = useWorkflowStore(state => state.hydrated);
  const saving = useWorkflowStore(state => state.saving);
  const lastSavedAt = useWorkflowStore(state => state.lastSavedAt);
  const revision = useWorkflowStore(state => state.revision);
  const nodes = useWorkflowStore(state => state.nodes);
  const candidateClips = useWorkflowStore(state => state.candidateClips);
  const composeWorkspaces = useWorkflowStore(state => state.composeWorkspaces);
  const [toast, setToast] = useState("");
  const [pipelineCollapsed, setPipelineCollapsed] = useState(loadPipelinePreference);
  const workflowProgress = useMemo(() => deriveWorkflowProgress(nodes, candidateClips, composeWorkspaces), [nodes, candidateClips, composeWorkspaces]);
  const toastTimer = useRef<number | null>(null);
  useEffect(() => () => { if (toastTimer.current !== null) window.clearTimeout(toastTimer.current); }, []);
  const notify = useCallback((message: string) => { if (toastTimer.current !== null) window.clearTimeout(toastTimer.current); setToast(message); toastTimer.current = window.setTimeout(() => { toastTimer.current = null; setToast(""); }, 2600); }, []);
  useEffect(() => { loadDraft().then(loadClipLibrary).catch(() => notify("草稿或本地片段加载失败，当前使用临时画布")); }, [loadDraft, loadClipLibrary, notify]);
  useEffect(() => {
    if (!hydrated) return;
    const timer = window.setInterval(() => {
      loadClipLibrary().catch(() => {
        // 自动扫描失败不打断当前页面，状态会保留在片段库提示中。
      });
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [hydrated, loadClipLibrary]);
  useEffect(() => { if (!hydrated || revision === 0) return; const timer = window.setTimeout(() => saveDraft().catch(() => notify("自动保存失败，请检查后端服务")), 800); return () => window.clearTimeout(timer); }, [hydrated, revision, saveDraft, notify]);
  useEffect(() => {
    try {
      window.localStorage.setItem(pipelinePreferenceKey, String(pipelineCollapsed));
    } catch {
      // 无法写入本地偏好时，仍保证当前页面可正常开合。
    }
  }, [pipelineCollapsed]);
  useEffect(() => {
    if (!hydrated || alwaysAvailableWorkspaceRoutes.has(path) || isWorkflowRouteUnlocked(path, workflowProgress)) return;
    const fallback = firstIncompleteWorkflowRoute(workflowProgress);
    window.history.replaceState({}, "", fallback);
    window.dispatchEvent(new Event("workflow:navigate"));
  }, [hydrated, path, workflowProgress]);
  const save = () => saveDraft().then(() => notify("草稿已保存")).catch(() => notify("保存失败，请检查后端服务"));
  const workspaceLabel = path === "/canvas-mvp" ? "流程总览" : path === "/workflow/weekly-plan" ? "自动化生产" : "分步编辑";
  const overviewUnlocked = isWorkflowRouteUnlocked("/canvas-mvp", workflowProgress);
  const outputUnlocked = isWorkflowRouteUnlocked("/workflow/output", workflowProgress);
  return <div className="app-shell">
    <header className="topbar">
      <button type="button" className="brand-button" onClick={() => navigate(overviewUnlocked ? "/canvas-mvp" : firstIncompleteWorkflowRoute(workflowProgress))}>
        <span className="brand-mark"><img src={`${import.meta.env.BASE_URL}favicon.png`} alt="" /></span>
        <span className="brand-copy"><span className="eyebrow">AI VIDEO WORKFLOW</span><h1>AI 图生视频工作流</h1></span>
      </button>
      <div className="topbar-context"><span className="context-label">当前模式</span><strong>{workspaceLabel}</strong><span className="context-divider" /><span className="context-label">自动化工作台</span></div>
      <div className="top-actions"><span className="status-dot">{saving ? "保存中" : lastSavedAt ? "已保存" : hydrated ? "就绪" : "加载中"}</span><button type="button" className="btn" disabled={saving || !hydrated} onClick={save}>{saving ? "保存中..." : "保存草稿"}</button><button type="button" className="btn btn-primary" disabled={!outputUnlocked} title={outputUnlocked ? "查看成片" : "请先完成前序步骤"} onClick={() => navigate("/workflow/output")}>查看成片</button></div>
    </header>
    <div className={`workspace ${pipelineCollapsed ? "pipeline-collapsed" : ""}`}><Pipeline path={path} collapsed={pipelineCollapsed} onToggle={() => setPipelineCollapsed(value => !value)} /><RouteContent path={path} onToast={notify} /></div>
    {toast && <div className="toast">{toast}</div>}
  </div>;
}

function RouteContent({ path, onToast }: { path: WorkflowRoute; onToast: (message: string) => void }) {
  if (path === "/canvas-mvp") return <CanvasWorkspace onToast={onToast} />;
  if (path === "/workflow/image-processing") return <ImageProcessingPage onToast={onToast} />;
  if (path === "/workflow/generator") return <GeneratorPage onToast={onToast} />;
  if (path === "/workflow/compose") return <BatchComposePage onToast={onToast} />;
  if (path === "/workflow/output") return <OutputPage onToast={onToast} />;
  if (path === "/workflow/tasks") return <TaskCenterPage onToast={onToast} />;
  if (path === "/workflow/asset-library-review") return <ManualAssetLibraryPage onToast={onToast} />;
  if (path === "/workflow/weekly-plan") return <WeeklyPlanPage onToast={onToast} />;
  if (path === "/workflow/clip-review") return <ClipReviewPage onToast={onToast} />;
  return <StepPage route={path} onToast={onToast} />;
}

function CanvasPageLegacy({ onToast }: { onToast: (message: string) => void }) {
  const nodes = useWorkflowStore(state => state.nodes); const edges = useWorkflowStore(state => state.edges); const selectedNodeId = useWorkflowStore(state => state.selectedNodeId); const selectedEdgeId = useWorkflowStore(state => state.selectedEdgeId); const setNodes = useWorkflowStore(state => state.setNodes); const setEdges = useWorkflowStore(state => state.setEdges); const addEdge = useWorkflowStore(state => state.addEdge); const setSelection = useWorkflowStore(state => state.setSelection); const addNode = useWorkflowStore(state => state.addNode); const arrangeWorkflowNodes = useWorkflowStore(state => state.arrangeWorkflowNodes); const saveDraft = useWorkflowStore(state => state.saveDraft); const deleteSelected = useWorkflowStore(state => state.deleteSelected); const [addOpen, setAddOpen] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [freshEdgeId, setFreshEdgeId] = useState<string | null>(null);
  const connectionFeedbackTimer = useRef<number | null>(null);
  useEffect(() => () => { if (connectionFeedbackTimer.current !== null) window.clearTimeout(connectionFeedbackTimer.current); }, []);
  const showConnectionSuccess = useCallback((edgeId: string) => {
    if (connectionFeedbackTimer.current !== null) window.clearTimeout(connectionFeedbackTimer.current);
    setFreshEdgeId(edgeId);
    connectionFeedbackTimer.current = window.setTimeout(() => { connectionFeedbackTimer.current = null; setFreshEdgeId(null); }, 1800);
  }, []);
  const onConnect = useCallback<OnConnect>(connection => { if (!connection.source || !connection.target) return; const current = useWorkflowStore.getState(); if (connection.source === connection.target) return onToast("不能连接节点自身"); if (current.edges.some(edge => edge.source === connection.source && edge.target === connection.target)) return onToast("连接已存在"); if (connectWouldCycle(current.edges, connection.source, connection.target)) return onToast("连接会形成循环"); const edgeId = `${connection.source}-${connection.target}-${current.edges.length + 1}`; addEdge({ id: edgeId, source: connection.source, target: connection.target, type: "smoothstep", markerEnd: { type: MarkerType.ArrowClosed, color: "#7bd8d0", width: 15, height: 15 } }); showConnectionSuccess(edgeId); onToast("已建立节点连接"); }, [addEdge, onToast, showConnectionSuccess]);
  const onSelectionChange = useCallback(({ nodes: selectedNodes, edges: selectedEdges }: { nodes: WorkflowNode[]; edges: Edge[] }) => { const selectedNode = selectedNodes[0]; const selectedEdge = selectedEdges[0]; setSelection(selectedNode?.id ?? null, selectedNode ? null : selectedEdge?.id ?? null); }, [setSelection]);
  const add = (kind: NodeKind) => { addNode(kind); setAddOpen(false); onToast(`已添加${nodeCatalog[kind].title}`); };
  const arrange = async () => {
    arrangeWorkflowNodes();
    try {
      await saveDraft();
      onToast("已按流程整理节点并保存草稿");
    } catch {
      onToast("节点已整理，但草稿保存失败");
    }
  };
  const hasSelection = Boolean(selectedNodeId || selectedEdgeId);
  const displayEdges = edges.map(edge => edge.id === freshEdgeId ? { ...edge, animated: true, className: `${edge.className ?? ""} edge-fresh` } : edge);
  return <><main className="main-column canvas-main"><div className="canvas-toolbar"><div><span className="panel-label">CANVAS OVERVIEW</span><strong>流程画布总览</strong></div><div className="toolbar-actions"><button type="button" className="btn" onClick={() => void arrange()}>整理流程</button><div className="add-menu"><button type="button" className="btn btn-primary" onClick={() => setAddOpen(value => !value)}>＋ 添加节点</button>{addOpen && <div className="add-menu-pop">{(["input", "image_process", "prompt", "generator", "output", "sound", "custom"] as NodeKind[]).map(kind => <button type="button" key={kind} onClick={() => add(kind)}>{nodeCatalog[kind].title}</button>)}</div>}</div><button type="button" className="btn" onClick={() => { deleteSelected(); onToast("已删除选中对象"); }}>删除选中</button></div></div><div className={`flow-shell flow-overview ${isConnecting ? "is-connecting" : ""}`}><ReactFlow nodes={nodes} edges={displayEdges} nodeTypes={nodeTypes} onNodesChange={setNodes} onEdgesChange={setEdges} onConnect={onConnect} onConnectStart={() => setIsConnecting(true)} onConnectEnd={() => setIsConnecting(false)} onSelectionChange={onSelectionChange} onPaneClick={() => setSelection(null)} onInit={instance => { window.setTimeout(() => instance.fitView({ padding: 0.18, minZoom: 0.45, maxZoom: 1.2 }), 0); }} fitView fitViewOptions={{ padding: 0.18, minZoom: 0.45, maxZoom: 1.2 }} connectionLineType={ConnectionLineType.SmoothStep} connectionLineStyle={{ stroke: "#8ee5dc", strokeWidth: 2.5, strokeDasharray: "7 5" }} defaultEdgeOptions={{ type: "smoothstep", markerEnd: { type: MarkerType.ArrowClosed, color: "#718287", width: 15, height: 15 } }} minZoom={0.05} maxZoom={8} deleteKeyCode={["Backspace", "Delete"]} proOptions={{ hideAttribution: true }}><Background color="#2b3438" gap={24} size={1} /><Controls position="bottom-right" /><MiniMap position="top-right" nodeColor="#355e62" maskColor="rgba(10,14,16,.26)" /></ReactFlow></div><div className="overview-help"><strong>按步骤进入独立页面</strong><span>画布只负责查看和连接流程；图片处理、片段生成、排序、合成和声音配置在左侧对应页面完成。</span></div></main>{hasSelection && <Inspector onToast={onToast} />}</>;
}

function CanvasWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const nodes = useWorkflowStore(state => state.nodes);
  const edges = useWorkflowStore(state => state.edges);
  const candidateClips = useWorkflowStore(state => state.candidateClips);
  const composeWorkspaces = useWorkflowStore(state => state.composeWorkspaces);
  const setSelection = useWorkflowStore(state => state.setSelection);
  const beginNodeEdit = useWorkflowStore(state => state.beginNodeEdit);
  const progress = useMemo(() => deriveWorkflowProgress(nodes, candidateClips, composeWorkspaces), [nodes, candidateClips, composeWorkspaces]);
  const completedCount = progress.steps.filter(step => step.complete).length;
  const [tab, setTab] = useState<"canvas" | "nodes" | "timeline">("canvas");
  return <div className="canvas-workspace-refresh"><section className="canvas-hero"><div><span className="panel-label">WORKSPACE OVERVIEW</span><h2>把每一次制作，变成可追踪的流程</h2><p>从素材上传到最终交付，状态、产物和下一步动作都集中在这里。</p></div><div className="canvas-hero-meta"><span className="status-chip success">● 草稿已同步</span><span className="hero-meta-note">{completedCount} / 7 个步骤已完成</span></div></section><section className="overview-stat-grid" aria-label="项目状态摘要"><article className="overview-stat-card"><span className="stat-icon purple">◈</span><div><small>流程进度</small><strong>{Math.round((completedCount / 7) * 100)}<em>%</em></strong><span className="stat-detail">{completedCount ? "按顺序推进" : "从第 1 步开始"}</span></div></article><article className="overview-stat-card"><span className="stat-icon green">✓</span><div><small>已完成步骤</small><strong>{completedCount}</strong><span className="stat-detail">共 7 个制作步骤</span></div></article><article className="overview-stat-card"><span className="stat-icon amber">↗</span><div><small>待处理动作</small><strong>{Math.max(7 - completedCount, 0)}</strong><span className="stat-detail">优先处理当前解锁步骤</span></div></article><article className="overview-stat-card"><span className="stat-icon blue">⌁</span><div><small>画布连接</small><strong>{edges.length}</strong><span className="stat-detail">节点关系清晰可见</span></div></article></section><div className="canvas-view-tabs" role="tablist" aria-label="总览视图"><button type="button" role="tab" aria-selected={tab === "canvas"} className={tab === "canvas" ? "active" : ""} onClick={() => setTab("canvas")}>流程画布</button><button type="button" role="tab" aria-selected={tab === "nodes"} className={tab === "nodes" ? "active" : ""} onClick={() => setTab("nodes")}>节点列表 <span>{nodes.length}</span></button><button type="button" role="tab" aria-selected={tab === "timeline"} className={tab === "timeline" ? "active" : ""} onClick={() => setTab("timeline")}>步骤时间轴</button></div>{tab === "canvas" && <CanvasPageLegacy onToast={onToast} />}{tab === "nodes" && <section className="overview-panel node-list-panel"><div className="overview-panel-head"><div><span className="panel-label">NODE INVENTORY</span><h3>工作节点</h3></div><span className="panel-muted">点击列表项可直接打开编辑抽屉</span></div><div className="node-list">{nodes.map(node => <button type="button" className="node-list-row" key={node.id} onClick={() => { setSelection(node.id); beginNodeEdit(node.id); }}><span className="node-list-index">{node.data.kind}</span><span className="node-list-copy"><strong>{node.data.title}</strong><small>{node.data.description}</small></span><span className="status-chip neutral">{node.data.status}</span><span className="node-list-arrow">→</span></button>)}</div>{nodes.length === 0 && <div className="empty-state compact">暂无节点，请先添加一个工作节点。</div>}</section>}{tab === "timeline" && <section className="overview-panel timeline-panel"><div className="overview-panel-head"><div><span className="panel-label">PRODUCTION TIMELINE</span><h3>按步骤推进</h3></div><span className="panel-muted">完成当前步骤后自动解锁下一步</span></div><div className="overview-timeline">{workflowRoutes.map((item, index) => { const step = progress.steps[index]; return <button type="button" key={item.path} className={`timeline-step ${step.complete ? "done" : step.unlocked ? "current" : "locked"}`} disabled={!step.unlocked} onClick={() => navigate(item.path)}><span className="timeline-marker">{step.complete ? "✓" : step.unlocked ? item.step : "·"}</span><span><strong>{item.label}</strong><small>{step.complete ? "已完成，可返回修改" : step.unlocked ? "当前可操作" : `完成第 ${index} 步后解锁`}</small></span><span className="timeline-arrow">{index < workflowRoutes.length - 1 ? "→" : "交付"}</span></button>; })}</div></section>}</div>;
}

export default function AppRoot() { return <ReactFlowProvider><App /></ReactFlowProvider>; }
