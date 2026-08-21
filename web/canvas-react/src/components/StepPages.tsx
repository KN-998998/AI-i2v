import { useEffect, useState, type ReactNode } from "react";
import { clips, nodeCatalog, totalTimelineDuration, type ComposeJob, type NodeKind, type TimelineClip, type WorkflowNode } from "../model";
import { getCanvasComposeStatus, startCanvasCompose } from "../api";
import { useWorkflowStore } from "../workflowStore";
import { Inspector } from "./Inspector";
import { navigate, type WorkflowRoute } from "../router";

type StepPageProps = { onToast: (message: string) => void };
type ManagedNodeKind = Extract<NodeKind, "input" | "prompt" | "generator" | "output" | "sound">;

export function StepPage({ route, onToast }: StepPageProps & { route: WorkflowRoute }) {
  const nodes = useWorkflowStore(state => state.nodes);
  const selectedNodeId = useWorkflowStore(state => state.selectedNodeId);
  const kind = managedKindForRoute(route);
  const nodeId = resolveStepNodeId(kind, nodes, selectedNodeId);
  const panel = route === "/workflow/sound" ? "voice" : route === "/workflow/prompts" ? "prompt" : undefined;
  const title = route === "/workflow/assets" ? "素材与菜品" : route === "/workflow/prompts" ? "提示词装配" : route === "/workflow/sound" ? "声音与文字" : "成片结果";
  const description = route === "/workflow/assets" ? "管理菜品、首帧和尾帧素材。" : route === "/workflow/prompts" ? "编辑 L0/L1/L2 槽位并准备视频生成参数。" : route === "/workflow/sound" ? "在无声成片完成后配置 BGM、人声和画面文字。" : "查看当前草稿的合成任务与最终视频。";
  const setSelection = useWorkflowStore(state => state.setSelection);
  const setActivePanel = useWorkflowStore(state => state.setActivePanel);
  useEffect(() => {
    setSelection(nodeId);
    if (panel) setActivePanel(panel);
  }, [nodeId, panel, setActivePanel, setSelection]);

  return <StepFrame route={route} title={title} description={description} onToast={onToast}>
    <div className="step-page-grid"><div className="step-page-main">{kind && <NodeManager kind={kind} onToast={onToast} />}<div className="step-context"><StepSummary route={route} nodeId={nodeId} /><StepNext route={route} /></div></div><Inspector onToast={onToast} /></div>
  </StepFrame>;
}

function managedKindForRoute(route: WorkflowRoute): ManagedNodeKind | null {
  if (route === "/workflow/assets") return "input";
  if (route === "/workflow/prompts") return "prompt";
  if (route === "/workflow/sound") return "sound";
  if (route === "/workflow/output") return "output";
  return null;
}

function resolveStepNodeId(kind: ManagedNodeKind | null, nodes: WorkflowNode[], selectedNodeId: string | null): string | null {
  if (!kind) return null;
  const selectedNode = nodes.find(node => node.id === selectedNodeId && node.data.kind === kind);
  if (selectedNode) return selectedNode.id;
  return kind === "input" ? "assets" : kind === "prompt" ? "prompt" : kind === "sound" ? "sound" : "output";
}

function NodeManager({ kind, onToast }: { kind: ManagedNodeKind; onToast: (message: string) => void }) {
  const nodes = useWorkflowStore(state => state.nodes).filter(node => node.data.kind === kind);
  const selectedNodeId = useWorkflowStore(state => state.selectedNodeId);
  const bgmName = useWorkflowStore(state => state.bgmName);
  const setSelection = useWorkflowStore(state => state.setSelection);
  const addNode = useWorkflowStore(state => state.addNode);
  const deleteNode = useWorkflowStore(state => state.deleteNode);
  const duplicateNode = useWorkflowStore(state => state.duplicateNode);
  const add = () => {
    addNode(kind);
    onToast(`已新增${nodeCatalog[kind].title}节点`);
  };
  const duplicate = (node: WorkflowNode) => {
    duplicateNode(node.id);
    onToast(`已复制${node.data.title}`);
  };
  const remove = (node: WorkflowNode) => {
    if (node.id === "assets" || node.id === "prompt" || node.id === "clips" || node.id === "output" || node.id === "sound") {
      onToast("流程核心节点不能删除");
      return;
    }
    deleteNode(node.id);
    onToast(`已删除${node.data.title}`);
  };
  return <section className="node-manager"><div className="panel-section-head"><div><span className="panel-label">NODE CRUD</span><h2>{nodeCatalog[kind].title} · {nodes.length} 个节点</h2></div><button type="button" className="btn btn-primary" onClick={add}>＋ 新增节点</button></div><div className="node-record-grid">{nodes.map((node, index) => { const selected = selectedNodeId === node.id; const protectedNode = ["assets", "prompt", "clips", "output", "sound"].includes(node.id); return <article className={`node-record ${selected ? "selected" : ""}`} key={node.id} onClick={() => setSelection(node.id)}><div className="node-record-head"><span className="node-record-index">{String(index + 1).padStart(2, "0")}</span><div><strong>{node.data.title}</strong><small>{node.id}</small></div><span className="node-status">{node.data.status}</span></div><div className="node-record-body">{node.data.kind === "input" && <><span>菜品：{node.data.dishName || "未设置"}</span><span>素材：{node.data.imageName || "未上传"}</span></>}{node.data.kind === "prompt" && <><span>L0：{node.data.promptL0?.length ?? 0} 个画面元素</span><span>运动：{node.data.promptMotion || "未设置"}</span></>}{node.data.kind === "generator" && <><span>规格：{node.data.duration || "3s"} · {node.data.resolution || "1080p"}</span><span>音频：{node.data.audio || "无声"}</span></>}{node.data.kind === "output" && <><span>目标：{node.data.outputTarget || "未设置"}</span><span>画幅：{node.data.outputAspect || "9:16"}</span></>}{node.data.kind === "sound" && <><span>BGM：{bgmName || "未上传"}</span><span>文字：{node.data.overlayMain || "未设置"}</span></>}</div><div className="node-record-actions"><button type="button" className="btn" onClick={event => { event.stopPropagation(); setSelection(node.id); }}>编辑</button><button type="button" className="btn" onClick={event => { event.stopPropagation(); duplicate(node); }}>复制</button><button type="button" className="btn btn-danger" disabled={protectedNode} onClick={event => { event.stopPropagation(); remove(node); }}>{protectedNode ? "核心节点" : "删除"}</button></div></article>; })}</div></section>;
}

function StepSummary({ route, nodeId }: { route: WorkflowRoute; nodeId: string | null }) {
  const timeline = useWorkflowStore(state => state.timeline);
  const nodes = useWorkflowStore(state => state.nodes);
  const node = nodeId ? nodes.find(item => item.id === nodeId)?.data : undefined;
  const summaries: Record<string, string> = {
    "/workflow/assets": `${node?.dishName || "未选择菜品"} · 素材待确认`,
    "/workflow/prompts": `已选择 ${node?.promptL0?.length ?? 0} 个 L0 画面元素`,
    "/workflow/sound": `${node?.voiceName || "未配置音色"} · ${node?.overlayMain || "未配置画面文字"}`,
    "/workflow/output": `${timeline.length} 个片段 · ${totalTimelineDuration(timeline).toFixed(1)}s 时间线`,
  };
  return <div className="step-summary"><span className="panel-label">CURRENT DATA</span><strong>{summaries[route] || "当前草稿"}</strong><p>本页修改会自动保存到同一份画布草稿。</p></div>;
}

function StepNext({ route }: { route: WorkflowRoute }) {
  const next: Record<string, { path: WorkflowRoute; label: string }> = {
    "/workflow/assets": { path: "/workflow/prompts", label: "下一步：提示词装配" },
    "/workflow/prompts": { path: "/workflow/generator", label: "下一步：生成片段" },
    "/workflow/sound": { path: "/workflow/output", label: "查看成片结果" },
  };
  const item = next[route];
  if (!item) return null;
  return <button type="button" className="btn btn-primary step-next" onClick={() => navigate(item.path)}>{item.label}</button>;
}

export function GeneratorPage({ onToast }: StepPageProps) {
  const timeline = useWorkflowStore(state => state.timeline);
  const nodes = useWorkflowStore(state => state.nodes);
  const selectedNodeId = useWorkflowStore(state => state.selectedNodeId);
  const availableClips = useWorkflowStore(state => state.availableClips);
  const loadClipLibrary = useWorkflowStore(state => state.loadClipLibrary);
  const updateTimelineClip = useWorkflowStore(state => state.updateTimelineClip);
  const setSelection = useWorkflowStore(state => state.setSelection);
  const [busy, setBusy] = useState(false);
  const nodeId = resolveStepNodeId("generator", nodes, selectedNodeId);
  useEffect(() => setSelection(nodeId), [nodeId, setSelection]);

  const refresh = async () => {
    setBusy(true);
    try {
      await loadClipLibrary();
      onToast("已刷新本地真实片段库");
    } catch (error) {
      onToast(`片段库加载失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setBusy(false);
    }
  };

  return <StepFrame route="/workflow/generator" title="生成视频片段" description="每个时间线片段独立生成，生成后作为多个输入流向排序和合成页面。" onToast={onToast}>
    <div className="step-page-grid"><div className="step-page-main"><NodeManager kind="generator" onToast={onToast} /><div className="step-panel"><div className="panel-section-head"><div><span className="panel-label">CLIP INPUTS</span><h2>{timeline.length} 个片段输入</h2></div><div className="panel-actions"><span className="muted">3s · 1080p · 9:16 · 无声</span><button type="button" className="btn" disabled={busy} onClick={refresh}>{busy ? "刷新中..." : "刷新本地片段"}</button></div></div><div className="clip-input-grid">{timeline.map((clip, index) => <article className="clip-input-card" key={clip.id}><div className="clip-index">{String(index + 1).padStart(2, "0")}</div>{clip.sourceUrl ? <video className="clip-thumb" controls preload="metadata" src={clip.sourceUrl} /> : null}<div className="clip-input-copy"><strong>{clip.dish}</strong><span>{clip.label} · {clip.timelineDuration.toFixed(1)}s</span><small className={clip.sourcePath ? "source-ready" : "source-pending"}>{clip.sourcePath ? `已关联真实文件：${clip.filename || "MP4"}` : "待生成或关联真实文件"}</small></div></article>)}</div><div className="step-callout">这里展示的是本机输出目录中的真实 MP4。Kling 生成任务仍由现有批处理流程负责；刷新后新片段会进入“片段排序”，不会把演示状态当成真实生成结果。</div><button type="button" className="btn" onClick={() => navigate("/workflow/timeline")}>进入片段排序</button><div className="muted clip-library-count">当前发现 {availableClips.length} 个本地片段</div></div></div><Inspector onToast={onToast} /></div>
  </StepFrame>;
}

export function TimelinePage({ onToast }: StepPageProps) {
  const timeline = useWorkflowStore(state => state.timeline);
  const reorderTimeline = useWorkflowStore(state => state.reorderTimeline);
  const removeTimelineClip = useWorkflowStore(state => state.removeTimelineClip);
  const toggleClip = useWorkflowStore(state => state.toggleClip);
  const availableClips = useWorkflowStore(state => state.availableClips);
  const [dragging, setDragging] = useState<string | null>(null);
  return <StepFrame route="/workflow/timeline" title="片段排序" description="选择要进入成片的片段，并通过拖拽确定最终展示顺序。" onToast={onToast}>
    <div className="step-panel"><div className="panel-section-head"><div><span className="panel-label">SELECTED CLIPS</span><h2>{timeline.length} 个片段 · {totalTimelineDuration(timeline).toFixed(1)}s</h2></div><button type="button" className="btn btn-primary" onClick={() => navigate("/workflow/compose")}>进入成片合成</button></div><div className="ordered-clip-list">{timeline.map((clip, index) => <div className="ordered-clip" key={clip.id} draggable onDragStart={() => setDragging(clip.id)} onDragOver={event => event.preventDefault()} onDrop={() => { if (dragging) reorderTimeline(dragging, clip.id); setDragging(null); }}><span className="drag-handle">⠿</span><span className="order-number">{index + 1}</span>{clip.sourceUrl ? <video className="clip-list-thumb" preload="metadata" src={clip.sourceUrl} /> : null}<div><strong>{clip.dish}</strong><small>{clip.label} · {clip.timelineDuration.toFixed(1)}s · {clip.sourcePath ? "已关联真实文件" : "等待真实文件"}</small></div><button type="button" className="clip-remove" aria-label={`移除${clip.dish}`} onClick={() => removeTimelineClip(clip.id)}>×</button></div>)}</div><div className="clip-pool-page"><h3>可选视频片段</h3><div className="pool-grid">{(availableClips.length ? availableClips : clips).map(clip => { const selected = timeline.some(item => item.id === clip.id); return <button type="button" key={clip.id} className={`pool-card ${selected ? "selected" : ""}`} onClick={() => toggleClip(clip.id)}><span>{clip.dish} · {clip.label}</span><small>{selected ? "已加入时间线" : `${clip.timelineDuration}s · 点击加入时间线`}</small></button>; })}</div></div></div>
  </StepFrame>;
}

export function ComposePage({ onToast }: StepPageProps) {
  const draftId = useWorkflowStore(state => state.draftId);
  const timeline = useWorkflowStore(state => state.timeline);
  const reorderTimeline = useWorkflowStore(state => state.reorderTimeline);
  const composeJob = useWorkflowStore(state => state.composeJob);
  const setComposeJob = useWorkflowStore(state => state.setComposeJob);
  const [dragging, setDragging] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);
  const compose = async () => {
    setComposing(true);
    try {
      let job = await startCanvasCompose(draftId);
      setComposeJob(job);
      while (job.status === "running") {
        await new Promise(resolve => window.setTimeout(resolve, 800));
        job = await getCanvasComposeStatus(draftId, job.job_id);
        setComposeJob(job);
      }
      onToast(job.status === "done" ? "无声成片已生成" : `合成失败：${job.error || "未知错误"}`);
    } catch (error) {
      onToast(`合成失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setComposing(false);
    }
  };
  return <StepFrame route="/workflow/compose" title="成片合成" description="这里接收多个已排序的视频片段，统一裁切、拼接并生成无声成片。" onToast={onToast}>
    <div className="compose-page-grid"><div className="step-panel"><div className="panel-section-head"><div><span className="panel-label">MULTI-CLIP INPUT</span><h2>{timeline.length} 个片段输入</h2></div><span className="muted">顺序即最终展示顺序</span></div><div className="ordered-clip-list">{timeline.map((clip, index) => <div className="ordered-clip" key={clip.id} draggable onDragStart={() => setDragging(clip.id)} onDragOver={event => event.preventDefault()} onDrop={() => { if (dragging) reorderTimeline(dragging, clip.id); setDragging(null); }}><span className="drag-handle">⠿</span><span className="order-number">{index + 1}</span>{clip.sourceUrl ? <video className="clip-list-thumb" preload="metadata" src={clip.sourceUrl} /> : null}<div><strong>{clip.dish}</strong><small>{clip.label} · {clip.timelineDuration.toFixed(1)}s</small></div><span className={`source-status ${clip.sourcePath ? "ready" : "pending"}`}>{clip.sourcePath ? "已关联真实文件" : "待关联文件"}</span></div>)}</div><div className="compose-actions"><button type="button" className="btn btn-primary" disabled={composing || timeline.length === 0 || timeline.some(clip => !clip.sourcePath)} onClick={compose}>{composing ? "合成中..." : "开始合成无声成片"}</button><button type="button" className="btn" onClick={() => navigate("/workflow/sound")}>合成后配置声音文字</button></div>{timeline.some(clip => !clip.sourcePath) ? <div className="step-callout">仍有片段没有关联真实 MP4，请先到“生成片段”刷新本地片段，或从“片段排序”加入已有片段。</div> : null}</div><ComposeResult job={composeJob} /></div>
  </StepFrame>;
}

export function OutputPage({ onToast }: StepPageProps) {
  const composeJob = useWorkflowStore(state => state.composeJob);
  return <StepFrame route="/workflow/output" title="成片结果" description="查看当前草稿最近一次合成结果，并继续进入声音与文字配置。" onToast={onToast}><div className="step-page-grid"><div className="step-page-main"><NodeManager kind="output" onToast={onToast} /><ComposeResult job={composeJob} /></div><Inspector onToast={onToast} /></div></StepFrame>;
}

function ComposeResult({ job }: { job: ComposeJob | null }) {
  if (!job) return <div className="step-panel empty-panel"><span className="panel-label">OUTPUT</span><h2>尚未开始合成</h2><p>合成完成后，这里会显示视频预览，并流向声音与文字页面。</p></div>;
  if (job.status === "running") return <div className="step-panel empty-panel"><span className="panel-label">OUTPUT</span><h2>合成中</h2><p>后台正在执行 ffmpeg，请稍候。</p></div>;
  if (job.status === "error") return <div className="step-panel empty-panel error-panel"><span className="panel-label">OUTPUT ERROR</span><h2>合成失败</h2><p>{job.error}</p></div>;
  return <div className="step-panel result-panel"><span className="panel-label">OUTPUT READY</span><h2>无声成片已生成</h2><video controls preload="metadata" src={job.output_url || undefined} /><button type="button" className="btn btn-primary" onClick={() => navigate("/workflow/sound")}>进入声音与文字</button></div>;
}

function StepFrame({ route, title, description, children }: StepPageProps & { route: WorkflowRoute; title: string; description: string; children: ReactNode }) {
  return <main className="step-main"><div className="step-breadcrumb"><button type="button" className="link-button" onClick={() => navigate("/canvas-mvp")}>流程画布</button><span>/</span><strong>{title}</strong></div><div className="step-header"><div><span className="panel-label">WORKFLOW STEP</span><h1>{title}</h1><p>{description}</p></div></div>{children}</main>;
}
