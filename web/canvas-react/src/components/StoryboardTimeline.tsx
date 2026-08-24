import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { overlayStyleFromItem, type OverlayItem, type TimelineClip } from "../model";

type PositionedClip = { clip: TimelineClip; start: number; end: number };
type TrimDrag = { clipId: string; edge: "start" | "end"; originX: number; originStart: number; originEnd: number; sourceDuration: number };

type StoryboardTimelineProps = {
  clips: TimelineClip[];
  overlayItems: OverlayItem[];
  onOverlayFocus?: (overlayId: string) => void;
  onUpdateClip?: (clipId: string, patch: Partial<TimelineClip>) => void;
  voiceText?: string;
  bgmName?: string;
};

export function StoryboardTimeline({ clips, overlayItems, onOverlayFocus, onUpdateClip, voiceText, bgmName }: StoryboardTimelineProps) {
  const total = clips.reduce((sum, clip) => sum + Math.max(0.1, clip.timelineDuration), 0);
  const [playhead, setPlayhead] = useState(0);
  const [trimDrag, setTrimDrag] = useState<TrimDrag | null>(null);
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
    if (!trimDrag || !onUpdateClip) return;
    const onPointerMove = (event: PointerEvent) => {
      const delta = (event.clientX - trimDrag.originX) / 100;
      const minimum = 0.1;
      const nextStart = trimDrag.edge === "start" ? clamp(trimDrag.originStart + delta, 0, trimDrag.originEnd - minimum) : trimDrag.originStart;
      const nextEnd = trimDrag.edge === "end" ? clamp(trimDrag.originEnd + delta, nextStart + minimum, trimDrag.sourceDuration) : trimDrag.originEnd;
      onUpdateClip(trimDrag.clipId, {
        sourceStartSeconds: roundSeconds(nextStart),
        sourceEndSeconds: roundSeconds(nextEnd),
        timelineDuration: roundSeconds(nextEnd - nextStart),
      });
    };
    const onPointerUp = () => setTrimDrag(null);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [onUpdateClip, trimDrag]);

  useEffect(() => {
    const video = previewVideoRef.current;
    if (!video || !activeClip?.clip.sourceUrl) return;
    const clipStart = activeClip.clip.sourceStartSeconds ?? 0;
    const localTime = clamp(clipStart + playhead - activeClip.start, clipStart, activeClip.clip.sourceEndSeconds ?? clipStart + activeClip.clip.timelineDuration);
    const seek = () => {
      try { video.currentTime = localTime; } catch { /* Metadata may not be available yet. */ }
    };
    if (video.readyState >= 1) seek();
    else video.addEventListener("loadedmetadata", seek, { once: true });
    void video.play().catch(() => undefined);
    return () => video.removeEventListener("loadedmetadata", seek);
  }, [activeClip?.clip.id, activeClip?.clip.sourceUrl, activeClip?.clip.sourceStartSeconds, activeClip?.clip.sourceEndSeconds, activeClip?.start, playhead]);

  const startTrim = (event: ReactPointerEvent<HTMLButtonElement>, item: PositionedClip, edge: TrimDrag["edge"]) => {
    event.preventDefault();
    event.stopPropagation();
    if (!onUpdateClip) return;
    const sourceDuration = Math.max(item.clip.sourceDurationSeconds ?? 3, item.clip.sourceEndSeconds ?? 0.1);
    setTrimDrag({
      clipId: item.clip.id,
      edge,
      originX: event.clientX,
      originStart: item.clip.sourceStartSeconds ?? 0,
      originEnd: Math.min(sourceDuration, item.clip.sourceEndSeconds ?? sourceDuration),
      sourceDuration,
    });
  };

  return <section className="storyboard-editor">
    <div className="storyboard-head"><div><span className="panel-label">STORYBOARD TIMELINE</span><strong>视频分镜与文字对齐</strong><p>按秒检查菜品切换点和当前画面文字；拖动视频块两侧调整入点和出点。</p></div><span className="storyboard-current">当前 {formatSeconds(playhead)} / {formatSeconds(total)}</span></div>
    {outOfRangeOverlays.length > 0 && <div className="timeline-warning">有 {outOfRangeOverlays.length} 条文字超出当前成片时长，当前预览不会显示它们。</div>}
    <div className="storyboard-scroll"><div className="storyboard-track-stack" style={{ minWidth: `${trackWidth}px` }}>
      <TimeRuler total={total} />
      <StoryboardTrack label="视频"><div className="storyboard-video-row">{positionedClips.map(item => <div className="storyboard-clip" key={item.clip.id} style={positionStyle(item.start, item.end, total)} onClick={() => setPlayhead(item.start)}><div className="storyboard-thumb">{item.clip.sourceUrl ? <video muted loop autoPlay playsInline preload="metadata" src={item.clip.sourceUrl} /> : <span className="storyboard-thumb-placeholder">待下载</span>}</div><div className="storyboard-clip-label"><strong>{item.clip.dish}</strong><small>{formatSeconds(item.start)} - {formatSeconds(item.end)} · 源 {formatSeconds(item.clip.sourceStartSeconds ?? 0)} - {formatSeconds(item.clip.sourceEndSeconds ?? item.clip.sourceDurationSeconds ?? item.clip.timelineDuration)}</small></div>{onUpdateClip && <><button type="button" className="trim-handle trim-start" aria-label={`调整${item.clip.dish}入点`} onPointerDown={event => startTrim(event, item, "start")} /> <button type="button" className="trim-handle trim-end" aria-label={`调整${item.clip.dish}出点`} onPointerDown={event => startTrim(event, item, "end")} /></>}</div>)}</div></StoryboardTrack>
      <StoryboardTrack label="文字"><div className="storyboard-overlay-row">{overlayItems.map((item, index) => { const active = activeOverlays.some(activeItem => activeItem.id === item.id); return <button type="button" className={`storyboard-overlay-item overlay-${item.position} ${active ? "is-active" : ""}`} key={item.id} style={{ ...positionStyle(item.startSeconds, item.endSeconds, total), ...overlayTrackStyle(item) }} title={`${item.text || "未填写文字"} · ${formatSeconds(item.startSeconds)} - ${formatSeconds(item.endSeconds)}`} aria-label={`文字 ${index + 1}：${item.text || "未填写文字"}`} onClick={() => { setPlayhead(clamp(item.startSeconds, 0, total)); onOverlayFocus?.(item.id); }}>{`文字 ${index + 1} · ${item.text || "未填写"}`}</button>; })}</div></StoryboardTrack>
      <StoryboardTrack label="人声"><AudioTrackBlock className="voice-track-block" label={voiceText?.trim() ? `人声 · ${voiceText.trim()}` : "未填写人声文案"} tone="voice" total={total} /></StoryboardTrack>
      <StoryboardTrack label="BGM"><AudioTrackBlock className="bgm-track-block" label={bgmName?.trim() ? `BGM · ${bgmName}` : "未上传 BGM"} tone="bgm" total={total} /></StoryboardTrack>
      <div className="storyboard-playhead" style={{ left: playheadLeft }} aria-hidden="true" />
    </div></div>
    <label className="storyboard-scrubber"><span>播放指针</span><input aria-label="时间线播放指针" type="range" min="0" max={Math.max(total, 0)} step="0.1" value={playhead} onChange={event => setPlayhead(Number(event.target.value))} /><output>{formatSeconds(playhead)}</output></label>
    <div className="storyboard-preview"><div className="storyboard-preview-media">{activeClip?.clip.sourceUrl ? <video ref={previewVideoRef} muted playsInline preload="metadata" src={activeClip.clip.sourceUrl} /> : <div className="storyboard-preview-placeholder">{clips.length ? "当前片段暂无本地视频" : "先把视频片段加入成片时间线"}</div>}{activeOverlays.length > 0 && <div className="storyboard-preview-overlays">{activeOverlays.map(item => <span className={`preview-overlay preview-${item.position}`} style={overlayPreviewStyle(item)} key={item.id}>{item.text || "未填写文字"}</span>)}</div>}</div><div className="storyboard-preview-meta"><strong>{activeClip?.clip.dish || "暂无片段"}</strong><span>{activeClip ? `${formatSeconds(activeClip.start)} - ${formatSeconds(activeClip.end)} · ${activeOverlays.length ? `当前文字：${activeOverlays.map(item => item.text || "未填写").join(" / ")}` : "当前时间无画面文字"}` : "播放指针移动到文字时间段后，文字会出现在左侧 9:16 预览中"}</span>{activeOverlays.length > 0 && <div className="storyboard-active-overlay-list">{activeOverlays.map(item => <span key={item.id}>{item.text || "未填写文字"} · {positionLabel(item.position)}</span>)}</div>}</div></div>
  </section>;
}

function AudioTrackBlock({ className, label, tone, total }: { className: string; label: string; tone: "voice" | "bgm"; total: number }) {
  return <div className={`storyboard-audio-row ${className}`} style={{ width: `${Math.max(100, total > 0 ? 100 : 0)}%` }}><div className="storyboard-waveform" aria-hidden="true">{Array.from({ length: 48 }, (_, index) => <i key={index} style={{ height: `${20 + ((index * 17 + (tone === "voice" ? 7 : 13)) % 64)}%` }} />)}</div><span className="storyboard-audio-label">{label}</span></div>;
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

function roundSeconds(value: number) {
  return Math.round(value * 10) / 10;
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

function overlayTrackStyle(item: OverlayItem): CSSProperties {
  const style = overlayStyleFromItem(item);
  return { color: style.color, fontWeight: style.fontWeight, backgroundColor: rgba(style.backgroundColor, style.backgroundOpacity) };
}

function overlayPreviewStyle(item: OverlayItem): CSSProperties {
  const style = overlayStyleFromItem(item);
  return {
    color: style.color,
    fontFamily: style.fontFamily,
    fontSize: `${Math.max(10, style.fontSize / 4)}px`,
    fontWeight: style.fontWeight,
    backgroundColor: style.backgroundEnabled ? rgba(style.backgroundColor, style.backgroundOpacity) : "transparent",
    textShadow: style.strokeWidth > 0 ? `0 0 ${style.strokeWidth}px ${style.strokeColor}` : "none",
  };
}

function rgba(hex: string, opacity: number) {
  const value = hex.replace("#", "");
  if (!/^[0-9a-f]{6}$/i.test(value)) return hex;
  const red = Number.parseInt(value.slice(0, 2), 16);
  const green = Number.parseInt(value.slice(2, 4), 16);
  const blue = Number.parseInt(value.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${clamp(opacity, 0, 1)})`;
}

function positionLabel(position: OverlayItem["position"]) {
  return position === "top" ? "上方品牌区" : position === "upper" ? "中上钩子区" : position === "center" ? "画面中央" : "底部安全区";
}
