import { useState } from "react";
import { getCanvasComposeStatus, runCanvasPreflight, startCanvasCompose, type PreflightReport } from "../api";
import { overlayItemsFromData, resolveDishCategory, voiceItemsFromData, type ComposeWorkspace, type TimelineClip } from "../model";
import { useWorkflowStore } from "../workflowStore";
import { navigate } from "../router";
import { StoryboardTimeline } from "./StoryboardTimeline";

type Props = { onToast: (message: string) => void };

export function BatchComposePage({ onToast }: Props) {
  const draftId = useWorkflowStore(state => state.draftId);
  const saveDraft = useWorkflowStore(state => state.saveDraft);
  const candidates = useWorkflowStore(state => state.candidateClips);
  const clipsLastLoadedAt = useWorkflowStore(state => state.clipsLastLoadedAt);
  const clipsLoadError = useWorkflowStore(state => state.clipsLoadError);
  const workspaces = useWorkflowStore(state => state.composeWorkspaces);
  const batchCount = useWorkflowStore(state => state.composeBatchCount);
  const clipCount = useWorkflowStore(state => state.composeClipCount);
  const setBatchCount = useWorkflowStore(state => state.setComposeBatchCount);
  const setClipCount = useWorkflowStore(state => state.setComposeClipCount);
  const randomize = useWorkflowStore(state => state.randomizeComposeWorkspaces);
  const recommend = useWorkflowStore(state => state.recommendComposeWorkspaces);
  const reorderWorkspace = useWorkflowStore(state => state.reorderWorkspace);
  const removeWorkspaceClip = useWorkflowStore(state => state.removeWorkspaceClip);
  const addWorkspaceClip = useWorkflowStore(state => state.addWorkspaceClip);
  const updateWorkspaceClip = useWorkflowStore(state => state.updateWorkspaceClip);
  const setWorkspaceJob = useWorkflowStore(state => state.setWorkspaceJob);
  const [dragging, setDragging] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [preflightReports, setPreflightReports] = useState<Record<string, PreflightReport | null>>({});
  const [preflightBusy, setPreflightBusy] = useState<string | null>(null);
  const syncTime = clipsLastLoadedAt ? new Date(clipsLastLoadedAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "尚未扫描";

  const checkWorkspace = async (workspaceId: string) => {
    setPreflightBusy(workspaceId);
    try {
      await saveDraft();
      const report = await runCanvasPreflight(draftId, workspaceId, false);
      setPreflightReports(current => ({ ...current, [workspaceId]: report }));
      onToast(report.ok ? "预检通过，可以合成" : `预检发现 ${report.errors.length} 个错误`);
      return report;
    } catch (error) {
      onToast(`预检失败：${error instanceof Error ? error.message : "未知错误"}`);
      return null;
    } finally {
      setPreflightBusy(current => current === workspaceId ? null : current);
    }
  };

  const composeWorkspace = async (workspaceId: string) => {
    await saveDraft();
    const report = await runCanvasPreflight(draftId, workspaceId, false);
    setPreflightReports(current => ({ ...current, [workspaceId]: report }));
    if (!report.ok) throw new Error(report.errors.map(item => item.message).join("；"));
    let job = await startCanvasCompose(draftId, workspaceId);
    setWorkspaceJob(workspaceId, job);
    while (job.status === "running") {
      await new Promise(resolve => window.setTimeout(resolve, 800));
      job = await getCanvasComposeStatus(draftId, job.job_id);
      setWorkspaceJob(workspaceId, job);
    }
    return job;
  };

  const composeAll = async () => {
    setBusy(true);
    try {
      const invalid = workspaces.find(item => item.clips.length === 0 || item.clips.some(clip => !clip.sourcePath));
      if (invalid) throw new Error(`${invalid.title} 仍有空槽位或未关联真实 MP4`);
      for (const workspace of workspaces) {
        const job = await composeWorkspace(workspace.id);
        if (job.status === "error") throw new Error(`${workspace.title}：${job.error || "合成失败"}`);
      }
      onToast(`已完成 ${workspaces.length} 条成片合成`);
    } catch (error) {
      onToast(`批量合成失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setBusy(false);
    }
  };

  return <main className="step-main"><div className="step-breadcrumb"><button type="button" className="link-button" onClick={() => navigate("/canvas-mvp")}>流程画布</button><span>/</span><strong>成片合成</strong></div><div className="step-header"><div><span className="panel-label">WORKFLOW STEP</span><h1>成片合成</h1><p>从前面生成节点汇入的候选片段池中，批量生成多套可人工调整顺序和入出点的成片方案。</p></div></div><section className="step-panel batch-compose-controls"><div><span className="panel-label">BATCH COMPOSE</span><h2>{batchCount} 条成片 · 每条 {clipCount} 个片段</h2><p className="muted">候选片段 {candidates.length} 个；智能推荐按质量分和菜品多样性选取。甜品或水果最多一段，并自动放在每条成片最后。</p><div className="clip-library-status"><span className="muted">自动检查每 30 秒 · 最近扫描 {syncTime}</span>{clipsLoadError && <span className="clip-sync-error">扫描失败：{clipsLoadError}</span>}</div></div><div className="batch-control-grid"><label className="field"><span>批量合成数量</span><input className="input" type="number" min="1" max="20" value={batchCount} onChange={event => setBatchCount(Number(event.target.value))} /></label><label className="field"><span>每条片段数量</span><input className="input" type="number" min="1" max="20" value={clipCount} onChange={event => setClipCount(Number(event.target.value))} /></label><button type="button" className="btn btn-primary" onClick={recommend} disabled={candidates.filter(clip => clip.sourcePath).length === 0}>智能推荐方案</button><button type="button" className="btn" onClick={randomize} disabled={candidates.filter(clip => clip.sourcePath).length === 0}>随机生成方案</button><button type="button" className="btn" onClick={composeAll} disabled={busy}>{busy ? "批量合成中..." : "批量开始合成"}</button></div></section><div className="compose-workspace-list">{workspaces.map(workspace => <WorkspaceCard key={workspace.id} workspace={workspace} candidates={candidates} dragging={dragging} setDragging={setDragging} reorderWorkspace={reorderWorkspace} removeWorkspaceClip={removeWorkspaceClip} addWorkspaceClip={addWorkspaceClip} updateWorkspaceClip={updateWorkspaceClip} preflight={preflightReports[workspace.id] ?? null} preflightBusy={preflightBusy === workspace.id} onPreflight={() => { void checkWorkspace(workspace.id); }} compose={async () => { setBusy(true); try { await composeWorkspace(workspace.id); onToast(`${workspace.title} 已完成`); } catch (error) { onToast(`合成失败：${error instanceof Error ? error.message : "未知错误"}`); } finally { setBusy(false); } }} busy={busy} />)}</div><div className="compose-actions"><button type="button" className="btn" onClick={() => navigate("/workflow/sound")}>合成后配置声音文字</button></div></main>;
}

function WorkspaceCard({ workspace, candidates, dragging, setDragging, reorderWorkspace, removeWorkspaceClip, addWorkspaceClip, updateWorkspaceClip, preflight, preflightBusy, onPreflight, compose, busy }: { workspace: ComposeWorkspace; candidates: TimelineClip[]; dragging: string | null; setDragging: (id: string | null) => void; reorderWorkspace: (workspaceId: string, sourceId: string, targetId: string) => void; removeWorkspaceClip: (workspaceId: string, clipId: string) => void; addWorkspaceClip: (workspaceId: string, clipId: string) => void; updateWorkspaceClip: (workspaceId: string, clipId: string, patch: Partial<TimelineClip>) => void; preflight: PreflightReport | null; preflightBusy: boolean; onPreflight: () => void; compose: () => Promise<void>; busy: boolean }) {
  const missing = workspace.clips.length === 0 || workspace.clips.some(clip => !clip.sourcePath);
  const soundNode = useWorkflowStore(state => state.nodes.find(node => node.data.kind === "sound"));
  const sound = soundNode?.data;
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const bgmName = useWorkflowStore(state => state.bgmName);
  const overlayItems = overlayItemsFromData(sound ?? {});
  const voiceItems = voiceItemsFromData(sound ?? {});
  const updateOverlayTimeline = (id: string, patch: Partial<(typeof overlayItems)[number]>) => {
    if (!soundNode) return;
    const next = overlayItems.map(item => item.id === id ? { ...item, ...patch } : item);
    const first = next[0];
    const cta = next.find(item => item.id === "overlay_cta") ?? next[next.length - 1];
    updateNodeData(soundNode.id, { overlayItems: next, overlayMain: first?.text ?? "", overlayCta: cta?.text ?? "", overlayStart: first ? String(first.startSeconds) + "s" : "0s", overlayEnd: first ? String(first.endSeconds) + "s" : "2.5s" });
  };
  const updateVoiceTimeline = (id: string, patch: Partial<(typeof voiceItems)[number]>) => {
    if (!soundNode) return;
    const next = voiceItems.map(item => item.id === id ? { ...item, ...patch } : item);
    const first = next[0];
    updateNodeData(soundNode.id, { voiceItems: next, voiceText: first?.text ?? "", voiceName: first?.voiceName ?? "voice", voiceVolume: String(first?.volume ?? 85) });
  };
  const removeOverlayTimeline = (id: string) => {
    if (!soundNode) return;
    const next = overlayItems.filter(item => item.id !== id);
    const first = next[0];
    const cta = next.find(item => item.id === "overlay_cta") ?? next[next.length - 1];
    updateNodeData(soundNode.id, {
      overlayItems: next,
      overlayMain: first?.text ?? "",
      overlayCta: cta?.text ?? "",
      overlayPosition: first ? (first.position === "top" ? "上方品牌区" : first.position === "upper" ? "中上钩子区" : first.position === "center" ? "画面中央" : first.position === "bottom" ? "底部安全区" : "自定义位置") : "中上钩子区",
      overlayStart: first ? `${first.startSeconds}s` : "0s",
      overlayEnd: first ? `${first.endSeconds}s` : "2.5s",
    });
  };
  const removeVoiceTimeline = (id: string) => {
    if (!soundNode) return;
    const next = voiceItems.filter(item => item.id !== id);
    const first = next[0];
    updateNodeData(soundNode.id, {
      voiceItems: next,
      voiceText: first?.text ?? "",
      voiceName: first?.voiceName ?? "voice",
      voiceVolume: String(first?.volume ?? 85),
    });
  };
  return <section className="step-panel compose-workspace-card">
    <div className="panel-section-head"><div><span className="panel-label">{workspace.id.toUpperCase()}</span><h2>{workspace.title} · {workspace.clips.length} 个片段</h2></div><span className={`source-status ${missing ? "pending" : "ready"}`}>{missing ? "待补齐" : "可合成"}</span></div>
    <StoryboardTimeline clips={workspace.clips} overlayItems={overlayItems} voiceItems={voiceItems} onUpdateOverlay={updateOverlayTimeline} onRemoveOverlay={removeOverlayTimeline} onUpdateVoice={updateVoiceTimeline} onRemoveVoice={removeVoiceTimeline} bgmName={bgmName} onUpdateClip={(clipId, patch) => updateWorkspaceClip(workspace.id, clipId, patch)} />
    <div className="ordered-clip-list">{workspace.clips.map((clip, index) => <div className="ordered-clip" key={clip.id} draggable onDragStart={() => setDragging(`${workspace.id}:${clip.id}`)} onDragOver={event => event.preventDefault()} onDrop={() => { if (dragging?.startsWith(`${workspace.id}:`)) reorderWorkspace(workspace.id, dragging.slice(workspace.id.length + 1), clip.id); setDragging(null); }}><span className="drag-handle">⠿</span><span className="order-number">{index + 1}</span>{clip.sourceUrl ? <video className="clip-list-thumb" preload="metadata" src={clip.previewUrl ?? clip.sourceUrl} /> : null}<div><strong>{clip.dish}</strong><small>{clip.label} · {resolveDishCategory(clip)} · 质量 {clip.qualityScore ?? "-"}/100 · {clip.timelineDuration.toFixed(1)}s · 源 {Number(clip.sourceStartSeconds ?? 0).toFixed(1)}-{Number(clip.sourceEndSeconds ?? clip.sourceDurationSeconds ?? clip.timelineDuration).toFixed(1)}s · {clip.sourcePath ? "已关联真实文件" : "待生成"}</small></div><button type="button" className="clip-remove" aria-label={`移除${clip.dish}`} onClick={() => removeWorkspaceClip(workspace.id, clip.id)}>×</button></div>)}</div>
    <div className="compose-pool"><span className="muted">补入候选片段</span><div className="pool-grid">{candidates.filter(clip => !workspace.clips.some(item => item.id === clip.id)).map(clip => <button type="button" className="pool-card" key={clip.id} onClick={() => addWorkspaceClip(workspace.id, clip.id)}><span>{clip.dish} · {resolveDishCategory(clip)} · {clip.label}</span><small>{clip.sourcePath ? `质量 ${clip.qualityScore ?? "-"}/100 · 加入此方案${clip.qualityWarnings?.length ? ` · ${clip.qualityWarnings.length} 条质量提示` : ""}` : "待生成，暂不可合成"}</small></button>)}</div></div>
    {preflight && <div className={`step-callout ${preflight.ok ? "" : "error-panel"}`}><strong>{preflight.ok ? "预检通过" : "预检未通过"}</strong><span>{preflight.ok ? `片段 ${preflight.summary.clipCount} 个 · 预计 ${preflight.summary.totalDurationSeconds.toFixed(1)}s` : preflight.errors.map(item => item.message).join("；")}</span>{preflight.warnings.map(item => <small key={item.code}>提示：{item.message}</small>)}</div>}
    <div className="compose-actions"><button type="button" className="btn" disabled={preflightBusy || busy} onClick={onPreflight}>{preflightBusy ? "预检中..." : "运行预检"}</button><button type="button" className="btn btn-primary" disabled={busy || missing} onClick={compose}>合成此条</button>{workspace.job ? <span className="muted">{workspace.job.status === "running" ? "合成中..." : workspace.job.status === "done" ? "已完成" : workspace.job.error}</span> : null}</div>{workspace.job?.output_url ? <video className="workspace-result-video" controls preload="metadata" src={workspace.job.output_url} /> : null}
  </section>;
}
