import { useState } from "react";
import { clips, totalTimelineDuration } from "../model";
import { getCanvasComposeStatus, startCanvasCompose, uploadDraftFile } from "../api";
import { useWorkflowStore } from "../workflowStore";

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
  const total = totalTimelineDuration(timeline);
  const [dragging, setDragging] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);
  const [composeResultUrl, setComposeResultUrl] = useState<string | null>(null);
  const start = Number.parseFloat(sound?.overlayStart ?? "0") || 0;
  const end = Number.parseFloat(sound?.overlayEnd ?? "2.5") || 2.5;
  const textLeft = Math.min(100, (start / Math.max(total, 0.1)) * 100);
  const textWidth = Math.min(Math.max(8, ((Math.max(end - start, 0.1)) / Math.max(total, 0.1)) * 100), Math.max(8, 100 - textLeft));
  const voiceLabel = `${sound?.voiceText || "引流文案配音"} · ${(sound?.voiceName || "女声").split(" · ")[0]}`;
  const textLabel = [sound?.overlayMain || "本周限定", sound?.overlayCta || "到店有礼"].join(" · ");
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
  return <section className="timeline"><div className="timeline-head"><div><h2>成片草稿 · 主时间线</h2><p>{timeline.length} 个片段 · 剪辑后 {total.toFixed(1)}s · 可拖动排序</p></div><button type="button" className="btn btn-primary" disabled={composing} onClick={compose}>{composing ? "合成中..." : "进入合成"}</button></div><div className="tracks">
    <Track label="视频"><div className="video-track">{timeline.map(clip => <div key={clip.id} className="clip-block" draggable onDragStart={() => setDragging(clip.id)} onDragOver={event => event.preventDefault()} onDrop={() => { if (dragging) reorderTimeline(dragging, clip.id); setDragging(null); }}><span>⠿</span><span className="clip-label">{clip.dish}<small> · {clip.timelineDuration.toFixed(1)}s</small></span><button type="button" aria-label={`移除${clip.dish}`} className="clip-remove" onClick={() => removeTimelineClip(clip.id)}>×</button></div>)}</div></Track>
    <Track label="BGM"><div className="track-content"><div className="audio-block timeline-content-block" title={bgmName || "BGM"}>{bgmName || "未上传 BGM"}{bgmName ? <button type="button" aria-label="移除 BGM" className="clip-remove audio-remove" onClick={event => { event.stopPropagation(); clearBgm(); onToast("BGM 已移除"); }}>×</button> : null}</div><label className="btn upload-button">上传 BGM<input type="file" accept="audio/*,.mp3,.wav,.m4a,.aac" onChange={event => { const file = event.target.files?.[0]; if (!file) return; setBgm(file.name, ""); uploadDraftFile(draftId, file, "audio").then(result => { setBgm(file.name, result.url); onToast(`BGM 已持久化：${file.name}`); }).catch(() => onToast("BGM 上传失败")); }} /></label></div></Track>
    <Track label="人声"><div className="track-content"><button type="button" className="voice-block timeline-content-block timeline-selectable" title={voiceLabel} onClick={() => { setSelection("sound"); setActivePanel("voice"); }}>{voiceLabel}</button></div></Track>
    <Track label="文字"><div className="track-content"><button type="button" className="text-block timeline-content-block timeline-selectable" style={{ marginLeft: `${textLeft}%`, width: `${textWidth}%`, flex: `0 0 ${textWidth}%` }} title={textLabel} onClick={() => { setSelection("sound"); setActivePanel("overlay"); }}>{textLabel}</button></div></Track>
  </div>{composeResultUrl && <div className="compose-result"><div><strong>无声成片</strong><span>已按当前时间线顺序生成</span></div><video controls preload="metadata" src={composeResultUrl} /></div>}<div className="clip-pool"><div className="pool-title">可选视频片段</div><div className="pool-grid">{clips.map(clip => { const selected = timeline.some(item => item.id === clip.id); return <button type="button" key={clip.id} className={`pool-card ${selected ? "selected" : ""}`} onClick={() => toggleClip(clip.id)}><span>{clip.dish} · {clip.label}</span><small>{clip.timelineDuration}s 源片段 · {selected ? "已加入时间线" : "点击加入"}</small></button>; })}</div></div></section>;
}

function Track({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="track"><span className="track-label">{label}</span><div className="track-lane">{children}</div></div>;
}
