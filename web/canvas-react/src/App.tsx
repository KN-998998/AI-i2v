import { useCallback, useEffect, useRef, useState } from "react";
import { Background, Controls, MiniMap, ReactFlow, ReactFlowProvider, type Edge, type OnConnect } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { connectWouldCycle, nodeCatalog, type NodeKind, type WorkflowNode } from "./model";
import { useWorkflowStore } from "./workflowStore";
import { Inspector } from "./components/Inspector";
import { Pipeline } from "./components/Pipeline";
import { GeneratorPage, OutputPage, StepPage } from "./components/StepPages";
import { navigate, routeForPath, type WorkflowRoute } from "./router";
import { WorkflowNodeCard } from "./components/WorkflowNodeCard";
import { BatchComposePage } from "./components/BatchComposePage";

const nodeTypes = { workflow: WorkflowNodeCard };

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
  const [toast, setToast] = useState("");
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
  const save = () => saveDraft().then(() => notify("草稿已保存")).catch(() => notify("保存失败，请检查后端服务"));
  return <div className="app-shell"><header className="topbar"><button type="button" className="brand-button" onClick={() => navigate("/canvas-mvp")}><span className="eyebrow">AI VIDEO WORKBENCH</span><h1>引流视频生产画布</h1></button><div className="top-actions"><span className="status-dot">{saving ? "保存中" : lastSavedAt ? "已持久化" : hydrated ? "本地草稿" : "加载中"}</span><button type="button" className="btn" disabled={saving || !hydrated} onClick={save}>{saving ? "保存中..." : "保存草稿"}</button><button type="button" className="btn btn-primary" onClick={() => navigate("/workflow/output")}>查看成片</button></div></header><div className="workspace"><Pipeline path={path} /><RouteContent path={path} onToast={notify} /></div>{toast && <div className="toast">{toast}</div>}</div>;
}

function RouteContent({ path, onToast }: { path: WorkflowRoute; onToast: (message: string) => void }) {
  if (path === "/canvas-mvp") return <CanvasPage onToast={onToast} />;
  if (path === "/workflow/generator") return <GeneratorPage onToast={onToast} />;
  if (path === "/workflow/compose") return <BatchComposePage onToast={onToast} />;
  if (path === "/workflow/output") return <OutputPage onToast={onToast} />;
  return <StepPage route={path} onToast={onToast} />;
}

function CanvasPage({ onToast }: { onToast: (message: string) => void }) {
  const nodes = useWorkflowStore(state => state.nodes); const edges = useWorkflowStore(state => state.edges); const setNodes = useWorkflowStore(state => state.setNodes); const setEdges = useWorkflowStore(state => state.setEdges); const addEdge = useWorkflowStore(state => state.addEdge); const setSelection = useWorkflowStore(state => state.setSelection); const addNode = useWorkflowStore(state => state.addNode); const deleteSelected = useWorkflowStore(state => state.deleteSelected); const [addOpen, setAddOpen] = useState(false);
  const onConnect = useCallback<OnConnect>(connection => { if (!connection.source || !connection.target) return; const current = useWorkflowStore.getState(); if (connection.source === connection.target) return onToast("不能连接节点自身"); if (current.edges.some(edge => edge.source === connection.source && edge.target === connection.target)) return onToast("连接已存在"); if (connectWouldCycle(current.edges, connection.source, connection.target)) return onToast("连接会形成循环"); addEdge({ id: `${connection.source}-${connection.target}-${current.edges.length + 1}`, source: connection.source, target: connection.target, type: "smoothstep" }); onToast("已建立节点连接"); }, [addEdge, onToast]);
  const onSelectionChange = useCallback(({ nodes: selectedNodes, edges: selectedEdges }: { nodes: WorkflowNode[]; edges: Edge[] }) => { const selectedNode = selectedNodes[0]; const selectedEdge = selectedEdges[0]; setSelection(selectedNode?.id ?? null, selectedNode ? null : selectedEdge?.id ?? null); }, [setSelection]);
  const add = (kind: NodeKind) => { addNode(kind); setAddOpen(false); onToast(`已添加${nodeCatalog[kind].title}`); };
  return <><main className="main-column"><div className="canvas-toolbar"><div><span className="panel-label">CANVAS OVERVIEW</span><strong>流程画布总览</strong></div><div className="toolbar-actions"><div className="add-menu"><button type="button" className="btn btn-primary" onClick={() => setAddOpen(value => !value)}>＋ 添加节点</button>{addOpen && <div className="add-menu-pop">{(["input", "prompt", "generator", "output", "sound", "custom"] as NodeKind[]).map(kind => <button type="button" key={kind} onClick={() => add(kind)}>{nodeCatalog[kind].title}</button>)}</div>}</div><button type="button" className="btn" onClick={() => { deleteSelected(); onToast("已删除选中对象"); }}>删除选中</button></div></div><div className="flow-shell flow-overview"><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={setNodes} onEdgesChange={setEdges} onConnect={onConnect} onSelectionChange={onSelectionChange} onPaneClick={() => setSelection(null)} fitView fitViewOptions={{ padding: 0.12 }} minZoom={0.05} maxZoom={8} deleteKeyCode={["Backspace", "Delete"]} proOptions={{ hideAttribution: true }}><Background color="#2b3438" gap={24} size={1} /><Controls position="bottom-right" /><MiniMap position="top-right" nodeColor="#355e62" maskColor="rgba(10,14,16,.26)" /></ReactFlow></div><div className="overview-help"><strong>按步骤进入独立页面</strong><span>画布只负责查看和连接流程；片段生成、排序、合成和声音配置在左侧对应页面完成。</span></div></main><Inspector onToast={onToast} /></>;
}

export default function AppRoot() { return <ReactFlowProvider><App /></ReactFlowProvider>; }
