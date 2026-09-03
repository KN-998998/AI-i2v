import { useEffect, useState, type ReactNode } from "react";
import { getCanvasComposeStatus, runCanvasPreflight, startCanvasCompose, type PreflightReport } from "../api";
import { captionSegmentsFromData, captionSegmentsPatch, captionSegmentsWithTimings, nodeCatalog, totalTimelineDuration, type ComposeJob, type NodeKind, type TimelineClip, type WorkflowNode } from "../model";
import { useWorkflowStore } from "../workflowStore";
import { Inspector } from "./Inspector";
import { navigate, type WorkflowRoute } from "../router";
import { StoryboardTimeline } from "./StoryboardTimeline";
import { AssetLibraryBatchPanel } from "./AssetLibraryBatchPanel";

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
    <div className="step-page-grid"><div className="step-page-main">{kind && <NodeManager kind={kind} onToast={onToast} />}{route === "/workflow/assets" && <AssetLibraryBatchPanel onToast={onToast} />}{route === "/workflow/sound" && <><SoundTextPreview /><SoundComposePanel onToast={onToast} /></>}<div className="step-context"><StepSummary route={route} nodeId={nodeId} /><StepNext route={route} /></div></div><Inspector onToast={onToast} /></div>
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
  const activeWorkspace = useWorkflowStore(state => state.composeWorkspaces.find(workspace => workspace.id === state.activeComposeWorkspaceId));
  const legacyBgmName = useWorkflowStore(state => state.bgmName);
  const bgmName = activeWorkspace?.soundConfig?.bgmName ?? legacyBgmName;
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
  if (kind === "output") return null;
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
  const generateNode = useWorkflowStore(state => state.generateNode);

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
  const generate = async (node: WorkflowNode) => {
    setSelection(node.id);
    try {
      await generateNode(node.id);
      onToast(`已完成生成并下载：${node.data.title}`);
    } catch (error) {
      onToast(`生成失败：${error instanceof Error ? error.message : "未知错误"}`);
    }
  };

  return <section className="node-manager">
    <div className="panel-section-head"><div><span className="panel-label">GENERATION NODES</span><h2>{nodeCatalog.generator.title} · {nodes.length} 个生成节点</h2><p className="muted">每个生成节点对应一个片段输出槽位。请先编辑节点，再点击对应卡片的生成按钮。</p></div><button type="button" className="btn btn-primary" onClick={add}>＋ 新增生成节点</button></div>
    <div className="node-record-grid">{nodes.map((node, index) => {
      const selected = selectedNodeId === node.id;
      const protectedNode = ["assets", "prompt", "clips", "output", "sound"].includes(node.id);
      const generated = node.data.status === "已生成";
      const generating = node.data.status === "生成中";
      const failed = node.data.status === "生成失败";
      return <article className={`node-record ${selected ? "selected" : ""}`} key={node.id} onClick={() => setSelection(node.id)}>
        <div className="node-record-head"><span className="node-record-index">{String(index + 1).padStart(2, "0")}</span><div><strong>{node.data.title}</strong><small>{node.id}</small></div><span className="node-status">{node.data.status}</span></div>
        <div className="node-record-body"><span>规格：{node.data.duration || "3s"} · {node.data.resolution || "1080p"}</span><span>音频：{node.data.audio || "无声"}</span></div>
        <div className="node-record-actions"><button type="button" disabled={generating} className={`btn ${generated || failed ? "" : "btn-primary"}`} onClick={event => { event.stopPropagation(); void generate(node); }}>{generating ? "生成中..." : failed ? "重试生成" : generated ? "再次生成" : "生成片段"}</button><button type="button" className="btn" onClick={event => { event.stopPropagation(); setSelection(node.id); }}>编辑</button><button type="button" className="btn" onClick={event => { event.stopPropagation(); duplicate(node); }}>复制</button><button type="button" className="btn btn-danger" disabled={protectedNode} onClick={event => { event.stopPropagation(); remove(node); }}>{protectedNode ? "核心节点" : "删除"}</button></div>
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
  const workspaces = useWorkflowStore(state => state.composeWorkspaces);
  const activeWorkspaceId = useWorkflowStore(state => state.activeComposeWorkspaceId);
  const setActiveWorkspace = useWorkflowStore(state => state.setActiveComposeWorkspace);
  const timeline = useWorkflowStore(state => state.composeWorkspaces.find(workspace => workspace.id === state.activeComposeWorkspaceId)?.clips ?? state.timeline);
  const soundNode = useWorkflowStore(state => state.nodes.find(node => node.data.kind === "sound"));
  const activeWorkspace = useWorkflowStore(state => state.composeWorkspaces.find(workspace => workspace.id === state.activeComposeWorkspaceId));
  const legacyBgmName = useWorkflowStore(state => state.bgmName);
  const sound = soundNode ? { ...soundNode.data, ...(activeWorkspace?.soundConfig ?? {}) } : undefined;
  const bgmName = activeWorkspace?.soundConfig?.bgmName ?? legacyBgmName;
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const setActivePanel = useWorkflowStore(state => state.setActivePanel);
  const clearBgm = useWorkflowStore(state => state.clearBgm);
  const captionSegments = captionSegmentsFromData(sound ?? {});
  const allOverlayItems = captionSegments.map(segment => segment.overlay);
  const allVoiceItems = captionSegments.map(segment => segment.voice);
  const overlayItems = allOverlayItems.filter(item => item.enabled !== false);
  const voiceItems = allVoiceItems.filter(item => item.enabled !== false);
  const updateOverlayTimeline = (id: string, patch: Partial<(typeof overlayItems)[number]>) => {
    if (!soundNode) return;
    const next = allOverlayItems.map(item => item.id === id ? { ...item, ...patch } : item);
    const visible = next.filter(item => item.enabled !== false);
    const first = visible[0];
    const cta = visible.find(item => item.id === "overlay_cta") ?? visible.at(-1);
    updateNodeData(soundNode.id, {
      overlayItems: next,
      voiceItems: allVoiceItems,
      overlayMain: first?.text ?? "",
      overlayCta: cta?.text ?? "",
      overlayPosition: first ? (first.position === "top" ? "上方品牌区" : first.position === "upper" ? "中上钩子区" : first.position === "center" ? "画面中央" : first.position === "bottom" ? "底部安全区" : "自定义位置") : "中上钩子区",
      overlayStart: first ? String(first.startSeconds) + "s" : "0s",
      overlayEnd: first ? String(first.endSeconds) + "s" : "2.5s",
    });
  };
  const updateVoiceTimeline = (id: string, patch: Partial<(typeof voiceItems)[number]>) => {
    if (!soundNode) return;
    const next = allVoiceItems.map(item => item.id === id ? { ...item, ...patch } : item);
    const enabled = next.filter(item => item.enabled !== false);
    const first = enabled[0];
    updateNodeData(soundNode.id, {
      voiceItems: next,
      overlayItems: allOverlayItems,
      voiceText: first?.text ?? "",
      voiceName: first?.voiceName ?? "女声 · 温暖自然",
      voiceVolume: String(first?.volume ?? 85),
    });
  };
  const removeOverlayTimeline = (id: string) => {
    if (!soundNode) return;
    const next = allOverlayItems.filter(item => item.id !== id);
    const visible = next.filter(item => item.enabled !== false);
    const first = visible[0];
    const cta = visible.find(item => item.id === "overlay_cta") ?? visible.at(-1);
    updateNodeData(soundNode.id, {
      overlayItems: next,
      voiceItems: allVoiceItems,
      overlayMain: first?.text ?? "",
      overlayCta: cta?.text ?? "",
      overlayPosition: first ? (first.position === "top" ? "上方品牌区" : first.position === "upper" ? "中上钩子区" : first.position === "center" ? "画面中央" : first.position === "bottom" ? "底部安全区" : "自定义位置") : "中上钩子区",
      overlayStart: first ? `${first.startSeconds}s` : "0s",
      overlayEnd: first ? `${first.endSeconds}s` : "2.5s",
    });
  };
  const removeVoiceTimeline = (id: string) => {
    if (!soundNode) return;
    const next = allVoiceItems.filter(item => item.id !== id);
    const enabled = next.filter(item => item.enabled !== false);
    const first = enabled[0];
    updateNodeData(soundNode.id, {
      voiceItems: next,
      overlayItems: allOverlayItems,
      voiceText: first?.text ?? "",
      voiceName: first?.voiceName ?? "女声 · 温暖自然",
      voiceVolume: String(first?.volume ?? 85),
    });
  };

  return <>
    <div className="workspace-picker" role="group" aria-label="选择要配置声音与文字的成片">
      <span className="panel-label">TARGET COMPOSITION</span>
      <div className="workspace-picker-list">{workspaces.map(workspace => <button type="button" key={workspace.id} className={`workspace-chip ${workspace.id === activeWorkspaceId ? "active" : ""}`} onClick={() => setActiveWorkspace(workspace.id)}>{workspace.title}<small>{workspace.clips.length} 段 · {workspace.finalJob?.status === "done" ? "有声完成" : workspace.job?.status === "done" ? "无声完成" : "未合成"}</small></button>)}</div>
    </div>
    <div className="sound-text-explainer">
      <div><span className="panel-label">TEXT OVERLAY LOGIC</span><strong>文字 1、文字 2 是同一个声音与文字节点里的多条文字轨道</strong></div>
      <p>每条文字单独设置文案、开始秒数、结束秒数和画面位置；它只会在自己的时间段出现，不会新增流程节点。拖动下方播放指针，查看它对应哪一个视频片段。</p>
      <div className="sound-text-legend"><span><i className="legend-dot legend-top" />上方品牌区</span><span><i className="legend-dot legend-upper" />中上钩子区</span><span><i className="legend-dot legend-center" />画面中央</span><span><i className="legend-dot legend-bottom" />底部安全区</span></div>
    </div>
    <StoryboardTimeline clips={timeline} overlayItems={overlayItems} voiceItems={voiceItems} bgmName={bgmName} onRemoveBgm={clearBgm} onUpdateOverlay={updateOverlayTimeline} onRemoveOverlay={removeOverlayTimeline} onUpdateVoice={updateVoiceTimeline} onRemoveVoice={removeVoiceTimeline} onVoiceFocus={() => setActivePanel("voice")} onOverlayFocus={() => setActivePanel("overlay")} />
  </>;
}

function SoundComposePanel({ onToast }: StepPageProps) {
  const draftId = useWorkflowStore(state => state.draftId);
  const activeWorkspaceId = useWorkflowStore(state => state.activeComposeWorkspaceId);
  const workspace = useWorkflowStore(state => state.composeWorkspaces.find(item => item.id === state.activeComposeWorkspaceId));
  const composeJob = workspace?.finalJob ?? null;
  const soundNode = useWorkflowStore(state => state.nodes.find(node => node.data.kind === "sound"));
  const saveDraft = useWorkflowStore(state => state.saveDraft);
  const setWorkspaceJob = useWorkflowStore(state => state.setWorkspaceJob);
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const [busy, setBusy] = useState(false);
  const [preflight, setPreflight] = useState<PreflightReport | null>(null);
  const compose = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await saveDraft();
      const report = await runCanvasPreflight(draftId, activeWorkspaceId ?? undefined, true);
      setPreflight(report);
      if (!report.ok) throw new Error(report.errors.map(item => item.message).join("；"));
      let job = await startCanvasCompose(draftId, activeWorkspaceId ?? undefined, true);
      setWorkspaceJob(activeWorkspaceId ?? "compose_1", job);
      while (job.status === "running") {
        await new Promise(resolve => window.setTimeout(resolve, 800));
        job = await getCanvasComposeStatus(draftId, job.job_id);
        setWorkspaceJob(activeWorkspaceId ?? "compose_1", job);
      }
      if (job.status === "error") throw new Error(job.error || "合成失败");
      if (soundNode && job.voice_timings) {
        const synced = captionSegmentsWithTimings(captionSegmentsFromData(soundNode.data), job.voice_timings);
        updateNodeData(soundNode.id, captionSegmentsPatch(synced));
        await saveDraft();
      }
      onToast("最终有声成片已生成");
    } catch (error) {
      onToast(`最终成片生成失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setBusy(false);
    }
  };
  return <section className="step-panel sound-compose-panel"><div className="panel-section-head"><div><span className="panel-label">FINAL RENDER</span><h2>应用声音与文字</h2><p className="muted">当前配置将应用到所选成片方案：{workspace?.title ?? "未选择方案"}。</p></div><button type="button" className="btn btn-primary" disabled={busy || workspace?.job?.status !== "done"} onClick={compose}>{busy ? "生成最终成片中..." : "生成最终有声成片"}</button></div>{workspace?.job?.status !== "done" && <div className="step-callout"><strong>请先完成无声成片</strong><span>在第 5 步合成当前方案后，才能生成最终有声成片。</span></div>}{preflight && <div className={`step-callout ${preflight.ok ? "" : "error-panel"}`}><strong>{preflight.ok ? "成片预检通过" : "成片预检未通过"}</strong><span>{preflight.ok ? `片段 ${preflight.summary.clipCount} 个 · 预计 ${preflight.summary.totalDurationSeconds.toFixed(1)}s · 文字 ${preflight.summary.overlayCount} 段 · 人声 ${preflight.summary.voiceCount} 段` : preflight.errors.map(item => item.message).join("；")}</span>{preflight.warnings.map(item => <small key={item.code}>提示：{item.message}</small>)}</div>}{composeJob?.status === "running" && <div className="step-callout"><strong>正在合成</strong><span>后台正在执行文字渲染、TTS 和音频混音，请稍候。</span></div>}{composeJob?.status === "error" && <div className="step-callout error-panel"><strong>上次生成失败</strong><span>{composeJob.error}</span></div>}{composeJob?.status === "done" && composeJob.output_url && <div className="compose-result"><div><strong>最终有声成片</strong><span>已应用当前人声、BGM 和多段画面文字</span></div><video controls preload="metadata" src={composeJob.output_url} /></div>}</section>;
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
  const selectGeneratorClip = useWorkflowStore(state => state.selectGeneratorClip);
  const setSelection = useWorkflowStore(state => state.setSelection);
  const [busy, setBusy] = useState(false);
  const nodeId = resolveStepNodeId("generator", nodes, selectedNodeId);
  const generatorCount = nodes.filter(node => node.data.kind === "generator").length;
  const readyClipCount = timeline.filter(clip => Boolean(clip.sourcePath) && clip.isSelected !== false).length;
  const pendingClipCount = timeline.filter(clip => clip.status === "pending" || !clip.sourcePath).length;
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
    <div className="step-page-grid"><div className="step-page-main"><section className="generator-status-strip"><div><span className="panel-label">CURRENT STATUS</span><strong>{generatorCount} 个生成节点</strong></div><div><span className="panel-label">READY CLIPS</span><strong className="source-ready">{readyClipCount} 个当前版本</strong></div><div><span className="panel-label">PENDING TASKS</span><strong className={pendingClipCount ? "source-pending" : "source-ready"}>{pendingClipCount} 个待关联</strong></div></section><NodeManager kind="generator" onToast={onToast} /><div className="step-panel"><div className="panel-section-head"><div><span className="panel-label">CLIP RESULTS</span><h2>按素材查看生成版本 · {timeline.filter(clip => clip.sourcePath).length} 个</h2><p className="muted">每张图片对应一个生成节点。再次生成会保留旧版本，只有“当前使用”版本会进入成片合成候选池。</p></div><div className="panel-actions"><span className="muted">3s · 1080p · 9:16 · 无声</span><button type="button" className="btn" disabled={busy} onClick={refresh}>{busy ? "刷新中..." : "扫描本地 MP4"}</button></div></div><div className="generator-version-list">{nodes.filter(node => node.data.kind === "generator").map(node => <GeneratorVersionGroup key={node.id} node={node} clips={timeline.filter(clip => clip.generatorNodeId === node.id)} selectedClipId={node.data.selectedClipId} onSelect={clipId => selectGeneratorClip(node.id, clipId)} />)}</div>{timeline.filter(clip => !clip.generatorNodeId).length > 0 && <div className="clip-input-grid">{timeline.filter(clip => !clip.generatorNodeId).map((clip, index) => <GeneratorVersionCard key={clip.id} clip={clip} index={index + 1} selected={clip.isSelected !== false} onSelect={() => {}} />)}</div>}<div className="step-callout"><strong>版本与合成关系</strong><span>同一张图片可以生成多次。点击“设为当前版本”后，画布节点、候选池和成片合成会同步使用该版本；旧版本仍保留在这里，方便回退。</span></div><button type="button" className="btn btn-primary" onClick={() => navigate("/workflow/compose")}>进入成片合成</button><div className="clip-library-status"><span className="muted">本地片段库发现 {availableClips.length} 个 MP4 · 自动扫描每 30 秒 · 最近扫描 {syncTime}</span>{clipsLoadError && <span className="clip-sync-error">扫描失败：{clipsLoadError}</span>}</div></div></div><Inspector onToast={onToast} /></div>
  </StepFrame>;
}

function GeneratorVersionGroup({ node, clips, selectedClipId, onSelect }: { node: WorkflowNode; clips: TimelineClip[]; selectedClipId?: string; onSelect: (clipId: string) => void }) {
  const selected = selectedClipId ? clips.find(clip => clip.id === selectedClipId) : clips.find(clip => clip.isSelected !== false && clip.sourcePath);
  return <section className="generator-version-group"><div className="generator-version-group-head"><div><span className="panel-label">{node.id}</span><h3>{node.data.title}</h3><p className="muted">素材标识：{node.data.assetId || "未设置"} · {clips.length} 个版本</p></div><span className={`source-status ${selected?.sourcePath ? "ready" : "pending"}`}>{selected?.sourcePath ? "当前版本已就绪" : "等待生成"}</span></div>{clips.length === 0 ? <div className="clip-input-card clip-pending"><div className="clip-thumb clip-thumb-placeholder">待生成</div><div className="clip-input-copy"><strong>尚未生成视频片段</strong><span>请在上方节点卡片点击“生成片段”</span></div></div> : <div className="clip-input-grid">{clips.map((clip, index) => <GeneratorVersionCard key={clip.id} clip={clip} index={index + 1} selected={clip.id === selected?.id} onSelect={() => onSelect(clip.id)} />)}</div>}</section>;
}

function GeneratorVersionCard({ clip, index, selected, onSelect }: { clip: TimelineClip; index: number; selected: boolean; onSelect: () => void }) {
  return <article className={`clip-input-card ${clip.sourcePath ? "clip-ready" : "clip-pending"} ${selected ? "is-selected" : ""}`}><div className="clip-index">V{clip.clipVersion ?? index}</div>{clip.sourceUrl ? <video className="clip-thumb" controls preload="metadata" src={clip.previewUrl ?? clip.sourceUrl} /> : <div className="clip-thumb clip-thumb-placeholder">待下载</div>}<div className="clip-input-copy"><strong>{clip.dish}</strong><span>{clip.label} · {clip.timelineDuration.toFixed(1)}s</span><small className={clip.sourcePath ? "source-ready" : "source-pending"}>{clip.sourcePath ? `版本 ${clip.clipVersion ?? index} · ${clip.filename || "MP4"}` : "已记录生成任务，等待真实 MP4"}</small></div><span className={`clip-result-badge ${clip.sourcePath ? "ready" : "pending"}`}>{clip.sourcePath ? selected ? "当前使用" : "历史版本" : "待下载"}</span>{clip.sourcePath && <button type="button" className="btn" disabled={selected} onClick={event => { event.stopPropagation(); onSelect(); }}>{selected ? "当前版本" : "设为当前版本"}</button>}</article>;
}

export function OutputPage({ onToast }: StepPageProps) {
  const storedWorkspaces = useWorkflowStore(state => state.composeWorkspaces);
  const composeJob = useWorkflowStore(state => state.composeJob);
  const workspaces = storedWorkspaces.map(workspace => ({
    ...workspace,
    finalJob: workspace.finalJob ?? (
      composeJob?.include_sound && composeJob.workspace_id === workspace.id ? composeJob : null
    ),
  }));
  const setActiveWorkspace = useWorkflowStore(state => state.setActiveComposeWorkspace);
  return <StepFrame route="/workflow/output" title="成片结果" description="查看每个成片方案的无声与有声结果，并继续完成声音与文字配置。" onToast={onToast}><div className="step-page-grid"><div className="step-page-main"><NodeManager kind="output" onToast={onToast} /><div className="output-workspace-list">{workspaces.map(workspace => <section className="step-panel output-workspace" key={workspace.id}><div className="panel-section-head"><div><span className="panel-label">{workspace.id.toUpperCase()}</span><h2>{workspace.title}</h2><p className="muted">{workspace.clips.length} 个片段 · 无声：{workspace.job?.status === "done" ? "已生成" : workspace.job?.status === "error" ? "失败" : "未生成"} · 有声：{workspace.finalJob?.status === "done" ? "已生成" : workspace.finalJob?.status === "error" ? "失败" : "未生成"}</p></div><button type="button" className="btn" onClick={() => { setActiveWorkspace(workspace.id); navigate("/workflow/sound"); }}>配置声音文字</button></div>{workspace.job?.output_url && <div className="result-version"><span>无声成片</span><video controls preload="metadata" src={workspace.job.output_url} /></div>}{workspace.finalJob?.output_url && <div className="result-version"><span>最终有声成片</span><video controls preload="metadata" src={workspace.finalJob.output_url} /></div>}{!workspace.job?.output_url && !workspace.finalJob?.output_url && <p className="muted">尚未生成该方案的视频结果。</p>}</section>)}</div></div><Inspector onToast={onToast} /></div></StepFrame>;
}

function StepFrame({ route, title, description, children }: StepPageProps & { route: WorkflowRoute; title: string; description: string; children: ReactNode }) {
  return <main className="step-main"><div className="step-breadcrumb"><button type="button" className="link-button" onClick={() => navigate("/canvas-mvp")}>流程画布</button><span>/</span><strong>{title}</strong></div><div className="step-header"><div><span className="panel-label">WORKFLOW STEP</span><h1>{title}</h1><p>{description}</p></div></div>{children}</main>;
}
