import { useEffect, useRef, useState, type ReactNode } from "react";
import { type OverlayItem, type TimelineClip } from "../model";

type PositionedClip = { clip: TimelineClip; start: number; end: number };

export function StoryboardTimeline({ clips, overlayItems, onOverlayFocus }: { clips: TimelineClip[]; overlayItems: OverlayItem[]; onOverlayFocus?: (overlayId: string) => void }) {
  const total = clips.reduce((sum, clip) => sum + Math.max(0.1, clip.timelineDuration), 0);
  const [playhead, setPlayhead] = useState(0);
  const previewVideoRef = useRef<HTMLVideoElement>(null);
  const positionedClips: PositionedClip[] = [];
  let cursor = 0;
  clips.forEach(clip => {
    const start = cursor;
    cursor += Math.max(0.1, clip.timelineDuration);
    positionedClips.push({ clip, start, end: cursor });
  });
  const activeClip = positionedClips.find(item => playhead >= item.start && playhead < item.end) ?? positionedClips.at(-1);
  const activeOverlays = overlayItems.filter(item => playhead >= item.startSeconds && playhead < item.endSeconds);
  const outOfRangeOverlays = total > 0 ? overlayItems.filter(item => item.startSeconds >= total || item.endSeconds > total) : [];
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
      try { video.currentTime = localTime; } catch { /* Metadata may not be available yet. */ }
    };
    if (video.readyState >= 1) seek();
    else video.addEventListener("loadedmetadata", seek, { once: true });
    void video.play().catch(() => undefined);
    return () => video.removeEventListener("loadedmetadata", seek);
  }, [activeClip?.clip.id, activeClip?.clip.sourceUrl, activeClip?.start, playhead]);

  return <section className="storyboard-editor">
    <div className="storyboard-head"><div><span className="panel-label">STORYBOARD TIMELINE</span><strong>视频分镜与文字对齐</strong><p>按秒检查菜品切换点和当前画面文字。</p></div><span className="storyboard-current">当前 {formatSeconds(playhead)} / {formatSeconds(total)}</span></div>
    {outOfRangeOverlays.length > 0 && <div className="timeline-warning">有 {outOfRangeOverlays.length} 条文字超出当前成片时长，当前预览不会显示它们。</div>}
    <div className="storyboard-scroll"><div className="storyboard-track-stack" style={{ minWidth: `${trackWidth}px` }}>
      <TimeRuler total={total} />
      <StoryboardTrack label="视频"><div className="storyboard-video-row">{positionedClips.map(item => <div className="storyboard-clip" key={item.clip.id} style={positionStyle(item.start, item.end, total)} onClick={() => setPlayhead(item.start)}><div className="storyboard-thumb">{item.clip.sourceUrl ? <video muted loop autoPlay playsInline preload="metadata" src={item.clip.sourceUrl} /> : <span className="storyboard-thumb-placeholder">待下载</span>}</div><div className="storyboard-clip-label"><strong>{item.clip.dish}</strong><small>{formatSeconds(item.start)} - {formatSeconds(item.end)}</small></div></div>)}</div></StoryboardTrack>
      <StoryboardTrack label="文字"><div className="storyboard-overlay-row">{overlayItems.map((item, index) => { const active = activeOverlays.some(activeItem => activeItem.id === item.id); return <button type="button" className={`storyboard-overlay-item overlay-${item.position} ${active ? "is-active" : ""}`} key={item.id} style={positionStyle(item.startSeconds, item.endSeconds, total)} title={`${item.text || "未填写文字"} · ${formatSeconds(item.startSeconds)} - ${formatSeconds(item.endSeconds)}`} aria-label={`文字 ${index + 1}：${item.text || "未填写文字"}`} onClick={() => { setPlayhead(clamp(item.startSeconds, 0, total)); onOverlayFocus?.(item.id); }}>{`文字 ${index + 1} · ${item.text || "未填写"}`}</button>; })}</div></StoryboardTrack>
      <div className="storyboard-playhead" style={{ left: playheadLeft }} aria-hidden="true" />
    </div></div>
    <label className="storyboard-scrubber"><span>播放指针</span><input aria-label="时间线播放指针" type="range" min="0" max={Math.max(total, 0)} step="0.1" value={playhead} onChange={event => setPlayhead(Number(event.target.value))} /><output>{formatSeconds(playhead)}</output></label>
    <div className="storyboard-preview"><div className="storyboard-preview-media">{activeClip?.clip.sourceUrl ? <video ref={previewVideoRef} muted playsInline preload="metadata" src={activeClip.clip.sourceUrl} /> : <div className="storyboard-preview-placeholder">{clips.length ? "当前片段暂无本地视频" : "先把视频片段加入成片时间线"}</div>}{activeOverlays.length > 0 && <div className="storyboard-preview-overlays">{activeOverlays.map(item => <span className={`preview-overlay preview-${item.position}`} key={item.id}>{item.text || "未填写文字"}</span>)}</div>}</div><div className="storyboard-preview-meta"><strong>{activeClip?.clip.dish || "暂无片段"}</strong><span>{activeClip ? `${formatSeconds(activeClip.start)} - ${formatSeconds(activeClip.end)} · ${activeOverlays.length ? `当前文字：${activeOverlays.map(item => item.text || "未填写").join(" / ")}` : "当前时间无画面文字"}` : "播放指针移动到文字时间段后，文字会出现在左侧 9:16 预览中"}</span>{activeOverlays.length > 0 && <div className="storyboard-active-overlay-list">{activeOverlays.map(item => <span key={item.id}>{item.text || "未填写文字"} · {item.position === "top" ? "上方品牌区" : item.position === "upper" ? "中上钩子区" : item.position === "center" ? "画面中央" : "底部安全区"}</span>)}</div>}</div></div>
  </section>;
}

function TimeRuler({ total }: { total: number }) {
  const ticks = Array.from({ length: Math.max(1, Math.ceil(total) + 1) }, (_, index) => index);
  return <div className="storyboard-ruler">{ticks.map(tick => <span key={tick} style={{ left: `${clamp((tick / Math.max(total, 0.1)) * 100, 0, 100)}%` }}>{tick}s</span>)}</div>;
}

function StoryboardTrack({ label, children }: { label: string; children: ReactNode }) {
  return <div className="storyboard-track"><span className="storyboard-track-label">{label}</span><div className="storyboard-track-lane">{children}</div></div>;
}

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
