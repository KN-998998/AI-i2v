import { useEffect, useState, type ReactNode } from "react";
import { getCanvasComposeStatus, startCanvasCompose } from "../api";
import { nodeCatalog, overlayItemsFromData, totalTimelineDuration, type ComposeJob, type NodeKind, type WorkflowNode } from "../model";
import { useWorkflowStore } from "../workflowStore";
import { Inspector } from "./Inspector";
import { navigate, type WorkflowRoute } from "../router";
import { StoryboardTimeline } from "./StoryboardTimeline";

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
    <div className="step-page-grid"><div className="step-page-main">{kind && <NodeManager kind={kind} onToast={onToast} />}{route === "/workflow/sound" && <><SoundTextPreview /><SoundComposePanel onToast={onToast} /></>}<div className="step-context"><StepSummary route={route} nodeId={nodeId} /><StepNext route={route} /></div></div><Inspector onToast={onToast} /></div>
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

function LegacyNodeManager({ kind, onToast }: { kind: ManagedNodeKind; onToast: (message: string) => void }) {
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
  return <section className="node-manager"><div className="panel-section-head"><div><span className="panel-label">GENERATION NODES</span><h2>{nodeCatalog[kind].title} · {nodes.length} 个生成节点</h2><p className="muted">每个生成节点对应一个片段输出槽位，可在画布或这里编辑。</p></div><button type="button" className="btn btn-primary" onClick={add}>＋ 新增生成节点</button></div><div className="node-record-grid">{nodes.map((node, index) => { const selected = selectedNodeId === node.id; const protectedNode = ["assets", "prompt", "clips", "output", "sound"].includes(node.id); return <article className={`node-record ${selected ? "selected" : ""}`} key={node.id} onClick={() => setSelection(node.id)}><div className="node-record-head"><span className="node-record-index">{String(index + 1).padStart(2, "0")}</span><div><strong>{node.data.title}</strong><small>{node.id}</small></div><span className="node-status">{node.data.status}</span></div><div className="node-record-body">{node.data.kind === "input" && <><span>菜品：{node.data.dishName || "未设置"}</span><span>素材：{node.data.imageName || "未上传"}</span></>}{node.data.kind === "prompt" && <><span>L0：{node.data.promptL0?.length ?? 0} 个画面元素</span><span>运动：{node.data.promptMotion || "未设置"}</span></>}{node.data.kind === "generator" && <><span>规格：{node.data.duration || "3s"} · {node.data.resolution || "1080p"}</span><span>音频：{node.data.audio || "无声"}</span></>}{node.data.kind === "output" && <><span>目标：{node.data.outputTarget || "未设置"}</span><span>画幅：{node.data.outputAspect || "9:16"}</span></>}{node.data.kind === "sound" && <><span>BGM：{bgmName || "未上传"}</span><span>文字：{node.data.overlayMain || "未设置"}</span></>}</div><div className="node-record-actions"><button type="button" className="btn" onClick={event => { event.stopPropagation(); setSelection(node.id); }}>编辑</button><button type="button" className="btn" onClick={event => { event.stopPropagation(); duplicate(node); }}>复制</button><button type="button" className="btn btn-danger" disabled={protectedNode} onClick={event => { event.stopPropagation(); remove(node); }}>{protectedNode ? "核心节点" : "删除"}</button></div></article>; })}</div></section>;
}

function NodeManager({ kind, onToast }: { kind: ManagedNodeKind; onToast: (message: string) => void }) {
  return kind === "generator"
    ? <GeneratorNodeManager onToast={onToast} />
    : <LegacyNodeManager kind={kind} onToast={onToast} />;
}

function GeneratorNodeManager({ onToast }: { onToast: (message: string) => void }) {
  const nodes = useWorkflowStore(state => state.nodes).filter(node => node.data.kind === "generator");
  const selectedNodeId = useWorkflowStore(state => state.selectedNodeId);
  const setSelection = useWorkflowStore(state => state.setSelection);
  const addNode = useWorkflowStore(state => state.addNode);
  const deleteNode = useWorkflowStore(state => state.deleteNode);
  const duplicateNode = useWorkflowStore(state => state.duplicateNode);
  const registerGeneratorClip = useWorkflowStore(state => state.registerGeneratorClip);
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);

  const add = () => {
    addNode("generator");
    onToast("已新增生成视频片段节点，请编辑后点击生成片段");
  };
  const duplicate = (node: WorkflowNode) => {
    duplicateNode(node.id);
    onToast(`已复制${node.data.title}，请重新点击生成片段`);
  };
  const remove = (node: WorkflowNode) => {
    if (["assets", "prompt", "clips", "output", "sound"].includes(node.id)) {
      onToast("流程核心节点不能删除");
      return;
    }
    deleteNode(node.id);
    onToast(`已删除${node.data.title}`);
  };
  const generate = (node: WorkflowNode) => {
    setSelection(node.id);
    registerGeneratorClip(node.id);
    updateNodeData(node.id, { status: "已进行生成" });
    onToast(`已进行生成：${node.data.title}`);
  };

  return <section className="node-manager">
    <div className="panel-section-head"><div><span className="panel-label">GENERATION NODES</span><h2>{nodeCatalog.generator.title} · {nodes.length} 个生成节点</h2><p className="muted">每个生成节点对应一个片段输出槽位。请先编辑节点，再点击对应卡片的生成按钮。</p></div><button type="button" className="btn btn-primary" onClick={add}>＋ 新增生成节点</button></div>
    <div className="node-record-grid">{nodes.map((node, index) => {
      const selected = selectedNodeId === node.id;
      const protectedNode = ["assets", "prompt", "clips", "output", "sound"].includes(node.id);
      const generated = node.data.status !== nodeCatalog.generator.status;
      return <article className={`node-record ${selected ? "selected" : ""}`} key={node.id} onClick={() => setSelection(node.id)}>
        <div className="node-record-head"><span className="node-record-index">{String(index + 1).padStart(2, "0")}</span><div><strong>{node.data.title}</strong><small>{node.id}</small></div><span className="node-status">{node.data.status}</span></div>
        <div className="node-record-body"><span>规格：{node.data.duration || "3s"} · {node.data.resolution || "1080p"}</span><span>音频：{node.data.audio || "无声"}</span></div>
        <div className="node-record-actions"><button type="button" className={`btn ${generated ? "" : "btn-primary"}`} onClick={event => { event.stopPropagation(); generate(node); }}>{generated ? "再次生成" : "生成片段"}</button><button type="button" className="btn" onClick={event => { event.stopPropagation(); setSelection(node.id); }}>编辑</button><button type="button" className="btn" onClick={event => { event.stopPropagation(); duplicate(node); }}>复制</button><button type="button" className="btn btn-danger" disabled={protectedNode} onClick={event => { event.stopPropagation(); remove(node); }}>{protectedNode ? "核心节点" : "删除"}</button></div>
      </article>;
    })}</div>
  </section>;
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

function SoundTextPreview() {
  const timeline = useWorkflowStore(state => state.timeline);
  const sound = useWorkflowStore(state => state.nodes.find(node => node.data.kind === "sound")?.data);
  const setActivePanel = useWorkflowStore(state => state.setActivePanel);
  const overlayItems = overlayItemsFromData(sound ?? {});

  return <>
    <div className="sound-text-explainer">
      <div><span className="panel-label">TEXT OVERLAY LOGIC</span><strong>文字 1、文字 2 是同一个声音与文字节点里的多条文字轨道</strong></div>
      <p>每条文字单独设置文案、开始秒数、结束秒数和画面位置；它只会在自己的时间段出现，不会新增流程节点。拖动下方播放指针，查看它对应哪一个视频片段。</p>
      <div className="sound-text-legend"><span><i className="legend-dot legend-top" />上方品牌区</span><span><i className="legend-dot legend-upper" />中上钩子区</span><span><i className="legend-dot legend-center" />画面中央</span><span><i className="legend-dot legend-bottom" />底部安全区</span></div>
    </div>
    <StoryboardTimeline clips={timeline} overlayItems={overlayItems} onOverlayFocus={() => setActivePanel("overlay")} />
  </>;
}

function SoundComposePanel({ onToast }: StepPageProps) {
  const draftId = useWorkflowStore(state => state.draftId);
  const composeJob = useWorkflowStore(state => state.composeJob);
  const saveDraft = useWorkflowStore(state => state.saveDraft);
  const setComposeJob = useWorkflowStore(state => state.setComposeJob);
  const [busy, setBusy] = useState(false);
  const compose = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await saveDraft();
      let job = await startCanvasCompose(draftId, undefined, true);
      setComposeJob(job);
      while (job.status === "running") {
        await new Promise(resolve => window.setTimeout(resolve, 800));
        job = await getCanvasComposeStatus(draftId, job.job_id);
        setComposeJob(job);
      }
      if (job.status === "error") throw new Error(job.error || "合成失败");
      onToast("最终有声成片已生成");
    } catch (error) {
      onToast(`最终成片生成失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setBusy(false);
    }
  };
  return <section className="step-panel sound-compose-panel"><div className="panel-section-head"><div><span className="panel-label">FINAL RENDER</span><h2>应用声音与文字</h2><p className="muted">文字按各自时间段叠加到视频上方；人声和 BGM 会在这里混音并生成最终成片。</p></div><button type="button" className="btn btn-primary" disabled={busy} onClick={compose}>{busy ? "生成最终成片中..." : "生成最终有声成片"}</button></div>{composeJob?.status === "running" && <div className="step-callout"><strong>正在合成</strong><span>后台正在执行文字渲染、TTS 和音频混音，请稍候。</span></div>}{composeJob?.status === "error" && <div className="step-callout error-panel"><strong>上次生成失败</strong><span>{composeJob.error}</span></div>}{composeJob?.status === "done" && composeJob.output_url && <div className="compose-result"><div><strong>最终有声成片</strong><span>已应用当前人声、BGM 和多段画面文字</span></div><video controls preload="metadata" src={composeJob.output_url} /></div>}</section>;
}

export function GeneratorPage({ onToast }: StepPageProps) {
  const timeline = useWorkflowStore(state => state.candidateClips);
  const nodes = useWorkflowStore(state => state.nodes);
  const selectedNodeId = useWorkflowStore(state => state.selectedNodeId);
  const availableClips = useWorkflowStore(state => state.availableClips);
  const clipsLastLoadedAt = useWorkflowStore(state => state.clipsLastLoadedAt);
  const clipsLoadError = useWorkflowStore(state => state.clipsLoadError);
  const loadClipLibrary = useWorkflowStore(state => state.loadClipLibrary);
  const updateTimelineClip = useWorkflowStore(state => state.updateTimelineClip);
  const setSelection = useWorkflowStore(state => state.setSelection);
  const [busy, setBusy] = useState(false);
  const nodeId = resolveStepNodeId("generator", nodes, selectedNodeId);
  const generatorCount = nodes.filter(node => node.data.kind === "generator").length;
  const readyClipCount = timeline.filter(clip => Boolean(clip.sourcePath)).length;
  const pendingClipCount = timeline.length - readyClipCount;
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

  const syncTime = clipsLastLoadedAt ? new Date(clipsLastLoadedAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "尚未扫描";
  return <StepFrame route="/workflow/generator" title="生成视频片段" description="先管理生成节点，再查看每个节点对应的片段结果。只有已经关联真实 MP4 的片段，才能进入成片合成。" onToast={onToast}>
    <div className="step-page-grid"><div className="step-page-main"><section className="generator-status-strip"><div><span className="panel-label">CURRENT STATUS</span><strong>{generatorCount} 个生成节点</strong></div><div><span className="panel-label">READY CLIPS</span><strong className="source-ready">{readyClipCount} 个可合成</strong></div><div><span className="panel-label">PENDING TASKS</span><strong className={pendingClipCount ? "source-pending" : "source-ready"}>{pendingClipCount} 个待关联</strong></div></section><NodeManager kind="generator" onToast={onToast} /><div className="step-panel"><div className="panel-section-head"><div><span className="panel-label">CLIP RESULTS</span><h2>候选片段 · {timeline.length} 个</h2><p className="muted">绿色表示本地已有 MP4；黄色表示只有生成任务记录，还不能合成。</p></div><div className="panel-actions"><span className="muted">3s · 1080p · 9:16 · 无声</span><button type="button" className="btn" disabled={busy} onClick={refresh}>{busy ? "刷新中..." : "扫描本地 MP4"}</button></div></div><div className="clip-input-grid">{timeline.map((clip, index) => <article className={`clip-input-card ${clip.sourcePath ? "clip-ready" : "clip-pending"}`} key={clip.id}><div className="clip-index">{String(index + 1).padStart(2, "0")}</div>{clip.sourceUrl ? <video className="clip-thumb" controls preload="metadata" src={clip.sourceUrl} /> : <div className="clip-thumb clip-thumb-placeholder">待下载</div>}<div className="clip-input-copy"><strong>{clip.dish}</strong><span>{clip.label} · {clip.timelineDuration.toFixed(1)}s</span><small className={clip.sourcePath ? "source-ready" : "source-pending"}>{clip.sourcePath ? `已关联真实文件：${clip.filename || "MP4"}` : "已记录生成任务，等待真实 MP4"}</small></div><span className={`clip-result-badge ${clip.sourcePath ? "ready" : "pending"}`}>{clip.sourcePath ? "可合成" : "待下载"}</span></article>)}</div><div className="step-callout"><strong>这里怎么判断？</strong><span>“待下载”只代表任务记录已经保存，视频文件还没有进入本地片段库。刷新只会扫描已经下载到本地的 MP4，不会替代 Kling 生成、轮询和下载。</span></div><button type="button" className="btn btn-primary" onClick={() => navigate("/workflow/compose")}>进入成片合成</button><div className="clip-library-status"><span className="muted">本地片段库发现 {availableClips.length} 个 MP4 · 自动扫描每 30 秒 · 最近扫描 {syncTime}</span>{clipsLoadError && <span className="clip-sync-error">扫描失败：{clipsLoadError}</span>}</div></div></div><Inspector onToast={onToast} /></div>
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
