import { useEffect, useRef, useState } from "react";
import { clips, overlayItemsFromData, totalTimelineDuration, type OverlayItem, type TimelineClip } from "../model";
import { getCanvasComposeStatus, startCanvasCompose, uploadDraftFile } from "../api";
import { useWorkflowStore } from "../workflowStore";

type PositionedClip = { clip: TimelineClip; start: number; end: number };

function formatSeconds(value: number) {
  return `${value.toFixed(1)}s`;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function positionStyle(start: number, end: number, total: number) {
  const safeTotal = Math.max(total, 0.1);
  const left = clamp((start / safeTotal) * 100, 0, 100);
  const width = clamp(((Math.max(end, start + 0.1) - start) / safeTotal) * 100, 0, 100 - left);
  return { left: `${left}%`, width: `${width}%` };
}

export function Timeline({ onToast }: { onToast: (message: string) => void }) {
  const timeline = useWorkflowStore(state => state.timeline);
  const bgmName = useWorkflowStore(state => state.bgmName);
  const nodes = useWorkflowStore(state => state.nodes);
  const reorderTimeline = useWorkflowStore(state => state.reorderTimeline);
  const removeTimelineClip = useWorkflowStore(state => state.removeTimelineClip);
  const toggleClip = useWorkflowStore(state => state.toggleClip);
  const draftId = useWorkflowStore(state => state.draftId);
  const setBgm = useWorkflowStore(state => state.setBgm);
  const clearBgm = useWorkflowStore(state => state.clearBgm);
  const setSelection = useWorkflowStore(state => state.setSelection);
  const setActivePanel = useWorkflowStore(state => state.setActivePanel);
  const saveDraft = useWorkflowStore(state => state.saveDraft);
  const sound = nodes.find(node => node.data.kind === "sound")?.data;
  const overlayItems = overlayItemsFromData(sound ?? {});
  const total = totalTimelineDuration(timeline);
  const [dragging, setDragging] = useState<string | null>(null);
  const [playhead, setPlayhead] = useState(0);
  const [composing, setComposing] = useState(false);
  const [composeResultUrl, setComposeResultUrl] = useState<string | null>(null);
  const previewVideoRef = useRef<HTMLVideoElement>(null);
  const positionedClips: PositionedClip[] = [];
  let cursor = 0;
  timeline.forEach(clip => {
    const start = cursor;
    cursor += Math.max(0.1, clip.timelineDuration);
    positionedClips.push({ clip, start, end: cursor });
  });
  const activeClip = positionedClips.find(item => playhead >= item.start && playhead < item.end) ?? positionedClips.at(-1);
  const activeOverlays = overlayItems.filter(item => playhead >= item.startSeconds && playhead < item.endSeconds);
  const outOfRangeOverlays = overlayItems.filter(item => item.startSeconds >= total || item.endSeconds > total);
  const voiceLabel = `${sound?.voiceText || "引流文案配音"} · ${(sound?.voiceName || "女声").split(" · ")[0]}`;
  const trackWidth = Math.max(720, total * 100);
  const playheadRatio = clamp(playhead / Math.max(total, 0.1), 0, 1);
  const playheadLeft = `calc(${playheadRatio * 100}% + ${60 * (1 - playheadRatio)}px)`;

  useEffect(() => {
    setPlayhead(value => clamp(value, 0, Math.max(total, 0)));
  }, [total]);

  useEffect(() => {
    const video = previewVideoRef.current;
    if (!video || !activeClip?.clip.sourceUrl) return;
    const localTime = clamp(playhead - activeClip.start + 0.5, 0, Math.max(activeClip.clip.timelineDuration, 0.1));
    const seek = () => {
      try { video.currentTime = localTime; } catch { /* The browser may not have metadata yet. */ }
    };
    if (video.readyState >= 1) seek();
    else video.addEventListener("loadedmetadata", seek, { once: true });
    void video.play().catch(() => undefined);
    return () => video.removeEventListener("loadedmetadata", seek);
  }, [activeClip?.clip.id, activeClip?.clip.sourceUrl, activeClip?.start, playhead]);

  const compose = async () => {
    if (composing) return;
    setComposing(true);
    setComposeResultUrl(null);
    try {
      await saveDraft();
      const started = await startCanvasCompose(draftId);
      let current = started;
      for (let attempt = 0; attempt < 150 && current.status === "running"; attempt += 1) {
        await new Promise(resolve => window.setTimeout(resolve, 800));
        current = await getCanvasComposeStatus(draftId, started.job_id);
      }
      if (current.status === "done" && current.output_url) {
        setComposeResultUrl(current.output_url);
        onToast("无声成片已生成");
      } else if (current.status === "error") {
        throw new Error(current.error || "合成失败");
      } else {
        throw new Error("合成超时，请检查后端日志");
      }
    } catch (error) {
      onToast(`合成失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setComposing(false);
    }
  };

  return <section className="timeline">
    <div className="timeline-head"><div><h2>成片草稿 · 主时间线</h2><p>{timeline.length} 个片段 · 剪辑后 {total.toFixed(1)}s · 可拖动排序</p></div><button type="button" className="btn btn-primary" disabled={composing} onClick={compose}>{composing ? "合成中..." : "进入合成"}</button></div>
    <section className="storyboard-editor">
      <div className="storyboard-head"><div><span className="panel-label">STORYBOARD TIMELINE</span><strong>视频分镜与文字对齐</strong><p>同一条秒数坐标下检查菜品切换和画面文字，拖动下方指针预览当前画面。</p></div><span className="storyboard-current">当前 {formatSeconds(playhead)} / {formatSeconds(total)}</span></div>
      {outOfRangeOverlays.length > 0 && <div className="timeline-warning">有 {outOfRangeOverlays.length} 条文字超出当前成片 {formatSeconds(total)} 的范围，请调整结束时间或增加视频片段。</div>}
      <div className="storyboard-scroll"><div className="storyboard-track-stack" style={{ minWidth: `${trackWidth}px` }}>
        <TimeRuler total={total} />
        <StoryboardTrack label="视频"><div className="storyboard-video-row">{positionedClips.map(item => <div className="storyboard-clip" key={item.clip.id} style={positionStyle(item.start, item.end, total)} draggable onClick={() => setPlayhead(item.start)} onDragStart={() => setDragging(item.clip.id)} onDragOver={event => event.preventDefault()} onDrop={() => { if (dragging) reorderTimeline(dragging, item.clip.id); setDragging(null); }}><div className="storyboard-thumb">{item.clip.sourceUrl ? <video muted loop autoPlay playsInline preload="metadata" src={item.clip.sourceUrl} /> : <span className="storyboard-thumb-placeholder">待下载</span>}</div><div className="storyboard-clip-label"><strong>{item.clip.dish}</strong><small>{formatSeconds(item.start)} - {formatSeconds(item.end)}</small></div><button type="button" aria-label={`移除${item.clip.dish}`} className="clip-remove storyboard-remove" onClick={event => { event.stopPropagation(); removeTimelineClip(item.clip.id); }}>×</button></div>)}</div></StoryboardTrack>
        <StoryboardTrack label="文字"><div className="storyboard-overlay-row">{overlayItems.map(item => <button type="button" className={`storyboard-overlay-item overlay-${item.position}`} key={item.id} style={positionStyle(item.startSeconds, item.endSeconds, total)} title={`${item.text} · ${formatSeconds(item.startSeconds)} - ${formatSeconds(item.endSeconds)}`} onClick={() => { setPlayhead(clamp(item.startSeconds, 0, total)); setSelection("sound"); setActivePanel("overlay"); }}>{item.text || "未填写文字"}</button>)}</div></StoryboardTrack>
        <div className="storyboard-playhead" style={{ left: playheadLeft }} aria-hidden="true" />
      </div></div>
      <label className="storyboard-scrubber"><span>播放指针</span><input aria-label="时间线播放指针" type="range" min="0" max={Math.max(total, 0)} step="0.1" value={playhead} onChange={event => setPlayhead(Number(event.target.value))} /><output>{formatSeconds(playhead)}</output></label>
      <div className="storyboard-preview"><div className="storyboard-preview-media">{activeClip?.clip.sourceUrl ? <video ref={previewVideoRef} muted playsInline preload="metadata" src={activeClip.clip.sourceUrl} /> : <div className="storyboard-preview-placeholder">当前片段暂无本地视频</div>}{activeOverlays.length > 0 && <div className="storyboard-preview-overlays">{activeOverlays.map(item => <span className={`preview-overlay preview-${item.position}`} key={item.id}>{item.text}</span>)}</div>}</div><div className="storyboard-preview-meta"><strong>{activeClip?.clip.dish || "暂无片段"}</strong><span>{activeClip ? `${formatSeconds(activeClip.start)} - ${formatSeconds(activeClip.end)} · ${activeOverlays.length ? `当前文字：${activeOverlays.map(item => item.text).join(" / ")}` : "当前时间无画面文字"}` : "先加入视频片段"}</span></div></div>
    </section>
    <div className="tracks">
      <Track label="BGM"><div className="track-content"><div className="audio-block timeline-content-block" title={bgmName || "BGM"}>{bgmName || "未上传 BGM"}{bgmName ? <button type="button" aria-label="移除 BGM" className="clip-remove audio-remove" onClick={event => { event.stopPropagation(); clearBgm(); onToast("BGM 已移除"); }}>×</button> : null}</div><label className="btn upload-button">上传 BGM<input type="file" accept="audio/*,.mp3,.wav,.m4a,.aac" onChange={event => { const file = event.target.files?.[0]; if (!file) return; setBgm(file.name, ""); uploadDraftFile(draftId, file, "audio").then(result => { setBgm(file.name, result.url); onToast(`BGM 已持久化：${file.name}`); }).catch(() => onToast("BGM 上传失败")); }} /></label></div></Track>
      <Track label="人声"><div className="track-content"><button type="button" className="voice-block timeline-content-block timeline-selectable" title={voiceLabel} onClick={() => { setSelection("sound"); setActivePanel("voice"); }}>{voiceLabel}</button></div></Track>
    </div>
    {composeResultUrl && <div className="compose-result"><div><strong>无声成片</strong><span>已按当前时间线顺序生成</span></div><video controls preload="metadata" src={composeResultUrl} /></div>}
    <div className="clip-pool"><div className="pool-title">可选视频片段</div><div className="pool-grid">{clips.map(clip => { const selected = timeline.some(item => item.id === clip.id); return <button type="button" key={clip.id} className={`pool-card ${selected ? "selected" : ""}`} onClick={() => toggleClip(clip.id)}><span>{clip.dish} · {clip.label}</span><small>{clip.timelineDuration}s 源片段 · {selected ? "已加入时间线" : "点击加入"}</small></button>; })}</div></div>
  </section>;
}

function TimeRuler({ total }: { total: number }) {
  const ticks = Array.from({ length: Math.max(1, Math.ceil(total) + 1) }, (_, index) => index);
  return <div className="storyboard-ruler">{ticks.map(tick => <span key={tick} style={{ left: `${clamp((tick / Math.max(total, 0.1)) * 100, 0, 100)}%` }}>{tick}s</span>)}</div>;
}

function StoryboardTrack({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="storyboard-track"><span className="storyboard-track-label">{label}</span><div className="storyboard-track-lane">{children}</div></div>;
}

function Track({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="track"><span className="track-label">{label}</span><div className="track-lane">{children}</div></div>;
}
