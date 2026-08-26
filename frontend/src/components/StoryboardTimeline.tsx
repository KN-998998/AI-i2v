import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { overlayCoordinatesFromItem, overlayStyleFromItem, type OverlayItem, type TimelineClip, type VoiceItem } from "../model";

type PositionedClip = { clip: TimelineClip; start: number; end: number };
type RangeDrag = { track: "overlay" | "voice"; itemId: string; mode: "start" | "end" | "move"; originX: number; originStart: number; originEnd: number };
type OverlayPositionDrag = { itemId: string; originX: number; originY: number; originPosition: { x: number; y: number } };

type StoryboardTimelineProps = {
  clips: TimelineClip[];
  mode?: "clip" | "sound";
  overlayItems: OverlayItem[];
  onOverlayFocus?: (overlayId: string) => void;
  onUpdateOverlay?: (overlayId: string, patch: Partial<OverlayItem>) => void;
  onRemoveOverlay?: (overlayId: string) => void;
  onUpdateClip?: (clipId: string, patch: Partial<TimelineClip>) => void;
  voiceItems?: VoiceItem[];
  voiceText?: string;
  onVoiceFocus?: (voiceId: string) => void;
  onUpdateVoice?: (voiceId: string, patch: Partial<VoiceItem>) => void;
  onRemoveVoice?: (voiceId: string) => void;
  bgmName?: string;
};

export function StoryboardTimeline({ clips, mode = "sound", overlayItems, onOverlayFocus, onUpdateOverlay, onRemoveOverlay, onUpdateClip, voiceItems = [], voiceText, onVoiceFocus, onUpdateVoice, onRemoveVoice, bgmName }: StoryboardTimelineProps) {
  const showSoundTracks = mode === "sound";
  const resolvedVoiceItems = voiceItems.length > 0 ? voiceItems : voiceText?.trim() ? [{ id: "voice_main", text: voiceText, startSeconds: 0, endSeconds: 4, volume: 85 }] : [];
  const total = clips.reduce((sum, clip) => sum + Math.max(0.1, clip.timelineDuration), 0);
  const [playhead, setPlayhead] = useState(0);
  const [selectedClipId, setSelectedClipId] = useState<string | null>(clips[0]?.id ?? null);
  const [previewSeek, setPreviewSeek] = useState<{ clipId: string; sourceTime: number } | null>(null);
  const [rangeDrag, setRangeDrag] = useState<RangeDrag | null>(null);
  const [overlayPositionDrag, setOverlayPositionDrag] = useState<OverlayPositionDrag | null>(null);
  const previewVideoRef = useRef<HTMLVideoElement>(null);
  const previewMediaRef = useRef<HTMLDivElement>(null);
  const positionedClips: PositionedClip[] = [];
  let cursor = 0;
  clips.forEach(clip => {
    const start = cursor;
    cursor += Math.max(0.1, clip.timelineDuration);
    positionedClips.push({ clip, start, end: cursor });
  });
  const activeClip = positionedClips.find(item => playhead >= item.start && playhead < item.end) ?? positionedClips.at(-1);
  const selectedClip = positionedClips.find(item => item.clip.id === selectedClipId) ?? positionedClips[0];
  const activeOverlays = showSoundTracks ? overlayItems.filter(item => playhead >= item.startSeconds && playhead < item.endSeconds) : [];
  const outOfRangeOverlays = showSoundTracks && total > 0 ? overlayItems.filter(item => item.startSeconds >= total || item.endSeconds > total) : [];
  const trackWidth = Math.max(720, total * 100);
  const playheadRatio = clamp(playhead / Math.max(total, 0.1), 0, 1);
  const playheadLeft = `calc(${playheadRatio * 100}% + ${72 * (1 - playheadRatio)}px)`;

  useEffect(() => {
    setPlayhead(value => clamp(value, 0, Math.max(total, 0)));
    setSelectedClipId(current => clips.some(clip => clip.id === current) ? current : clips[0]?.id ?? null);
  }, [total]);

  useEffect(() => {
    if (!rangeDrag) return;
    const onPointerMove = (event: PointerEvent) => {
      const delta = (event.clientX - rangeDrag.originX) / 100;
      const minimum = 0.1;
      const duration = rangeDrag.originEnd - rangeDrag.originStart;
      let nextStart = rangeDrag.originStart;
      let nextEnd = rangeDrag.originEnd;
      if (rangeDrag.mode === "start") {
        nextStart = clamp(rangeDrag.originStart + delta, 0, rangeDrag.originEnd - minimum);
      } else if (rangeDrag.mode === "end") {
        nextEnd = clamp(rangeDrag.originEnd + delta, rangeDrag.originStart + minimum, total);
      } else {
        const offset = clamp(delta, -rangeDrag.originStart, total - rangeDrag.originEnd);
        nextStart = rangeDrag.originStart + offset;
        nextEnd = nextStart + duration;
      }
      const patch = { startSeconds: roundSeconds(nextStart), endSeconds: roundSeconds(nextEnd) };
      if (rangeDrag.track === "overlay") onUpdateOverlay?.(rangeDrag.itemId, patch);
      else onUpdateVoice?.(rangeDrag.itemId, patch);
    };
    const onPointerUp = () => setRangeDrag(null);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [onUpdateOverlay, onUpdateVoice, rangeDrag, total]);

  useEffect(() => {
    if (!overlayPositionDrag || !onUpdateOverlay) return;
    const onPointerMove = (event: PointerEvent) => {
      const rect = previewMediaRef.current?.getBoundingClientRect();
      if (!rect || rect.width <= 0 || rect.height <= 0) return;
      const nextX = clamp(overlayPositionDrag.originPosition.x + (event.clientX - overlayPositionDrag.originX) / rect.width, 0.05, 0.95);
      const nextY = clamp(overlayPositionDrag.originPosition.y + (event.clientY - overlayPositionDrag.originY) / rect.height, 0.05, 0.95);
      onUpdateOverlay(overlayPositionDrag.itemId, { position: "custom", x: roundRatio(nextX), y: roundRatio(nextY) });
    };
    const onPointerUp = () => setOverlayPositionDrag(null);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [onUpdateOverlay, overlayPositionDrag]);

  useEffect(() => {
    const video = previewVideoRef.current;
    if (!video || !(activeClip?.clip.previewUrl ?? activeClip?.clip.sourceUrl)) return;
    const clipStart = activeClip.clip.sourceStartSeconds ?? 0;
    const clipEnd = activeClip.clip.sourceEndSeconds ?? clipStart + activeClip.clip.timelineDuration;
    const localTime = previewSeek?.clipId === activeClip.clip.id
      ? clamp(previewSeek.sourceTime, clipStart, clipEnd)
      : clamp(clipStart + playhead - activeClip.start, clipStart, clipEnd);
    const seek = () => {
      try { video.currentTime = localTime; } catch { /* Metadata may not be available yet. */ }
    };
    if (video.readyState >= 1) seek();
    else video.addEventListener("loadedmetadata", seek, { once: true });
    if (previewSeek?.clipId === activeClip.clip.id) video.pause();
    else void video.play().catch(() => undefined);
    const loopSelectedRange = () => {
      if (!showSoundTracks && video.currentTime >= clipEnd - 0.03) {
        video.currentTime = clipStart;
        void video.play().catch(() => undefined);
      }
    };
    if (!showSoundTracks) video.addEventListener("timeupdate", loopSelectedRange);
    return () => {
      video.removeEventListener("loadedmetadata", seek);
      video.removeEventListener("timeupdate", loopSelectedRange);
    };
  }, [activeClip?.clip.id, activeClip?.clip.previewUrl, activeClip?.clip.sourceUrl, activeClip?.clip.sourceStartSeconds, activeClip?.clip.sourceEndSeconds, activeClip?.clip.sourceDurationSeconds, activeClip?.start, playhead, previewSeek, showSoundTracks]);

  const movePlayhead = (value: number) => {
    setPreviewSeek(null);
    setPlayhead(clamp(value, 0, total));
  };

  const previewSourceFrame = (item: PositionedClip, sourceTime: number) => {
    setSelectedClipId(item.clip.id);
    setPreviewSeek({ clipId: item.clip.id, sourceTime });
    setPlayhead(item.start);
  };

  const replaySelectedRange = () => {
    if (!activeClip) return;
    const start = activeClip.clip.sourceStartSeconds ?? 0;
    setPreviewSeek(null);
    setPlayhead(activeClip.start);
    const video = previewVideoRef.current;
    if (!video) return;
    try { video.currentTime = start; } catch { /* Metadata may not be available yet. */ }
    void video.play().catch(() => undefined);
  };

  const confirmSelectedClip = () => {
    if (!selectedClip || !onUpdateClip) return;
    onUpdateClip(selectedClip.clip.id, { trimConfirmed: true });
  };

  const startRangeDrag = (event: ReactPointerEvent<HTMLElement>, track: RangeDrag["track"], itemId: string, mode: RangeDrag["mode"], start: number, end: number) => {
    event.preventDefault();
    event.stopPropagation();
    if ((track === "overlay" && !onUpdateOverlay) || (track === "voice" && !onUpdateVoice)) return;
    setRangeDrag({ track, itemId, mode, originX: event.clientX, originStart: start, originEnd: end });
  };

  const startOverlayPositionDrag = (event: ReactPointerEvent<HTMLSpanElement>, item: OverlayItem) => {
    event.preventDefault();
    event.stopPropagation();
    if (!onUpdateOverlay) return;
    movePlayhead(item.startSeconds);
    onOverlayFocus?.(item.id);
    setOverlayPositionDrag({ itemId: item.id, originX: event.clientX, originY: event.clientY, originPosition: overlayCoordinatesFromItem(item) });
  };

  const overlayLanes = layoutRangeLanes(overlayItems);
  const voiceLanes = layoutRangeLanes(resolvedVoiceItems);
  const renderOverlayItem = (item: OverlayItem) => {
    const index = overlayItems.findIndex(candidate => candidate.id === item.id);
    const active = activeOverlays.some(activeItem => activeItem.id === item.id);
    const paired = Boolean(item.syncVoiceId && resolvedVoiceItems.some(voice => voice.id === item.syncVoiceId));
    return <TimelineRangeBlock key={item.id} className={"storyboard-overlay-item overlay-" + item.position + (active ? " is-active" : "")} total={total} locked={paired} style={{ ...positionStyle(item.startSeconds, item.endSeconds, total), ...overlayTrackStyle(item) }} label={"文字 " + (index + 1) + " · " + (item.text || "未填写") + (paired ? " · 同步人声" : "")} removeLabel={`删除文字 ${index + 1}`} onRemove={onRemoveOverlay ? () => onRemoveOverlay(item.id) : undefined} onPointerDown={event => startRangeDrag(event, "overlay", item.id, "move", item.startSeconds, item.endSeconds)} onResizeStart={event => startRangeDrag(event, "overlay", item.id, "start", item.startSeconds, item.endSeconds)} onResizeEnd={event => startRangeDrag(event, "overlay", item.id, "end", item.startSeconds, item.endSeconds)} onClick={() => { movePlayhead(item.startSeconds); onOverlayFocus?.(item.id); }} />;
  };
  const renderVoiceItem = (item: VoiceItem) => {
    const index = resolvedVoiceItems.findIndex(candidate => candidate.id === item.id);
    const paired = overlayItems.some(overlay => overlay.syncVoiceId === item.id);
    return <TimelineRangeBlock key={item.id} className="storyboard-range-audio voice-track-block" tone="voice" total={total} locked={paired} style={{ ...positionStyle(item.startSeconds, item.endSeconds, total), top: "6px", bottom: "6px" }} label={"人声 " + (index + 1) + " · " + (item.text || "未填写") + (paired ? " · 同步文字" : "")} removeLabel={`删除人声 ${index + 1}`} onRemove={onRemoveVoice ? () => onRemoveVoice(item.id) : undefined} onPointerDown={event => startRangeDrag(event, "voice", item.id, "move", item.startSeconds, item.endSeconds)} onResizeStart={event => startRangeDrag(event, "voice", item.id, "start", item.startSeconds, item.endSeconds)} onResizeEnd={event => startRangeDrag(event, "voice", item.id, "end", item.startSeconds, item.endSeconds)} onClick={() => { movePlayhead(item.startSeconds); onVoiceFocus?.(item.id); }} />;
  };

  return <section className={`storyboard-editor ${showSoundTracks ? "" : "storyboard-editor-clip"}`}>
    <div className="storyboard-head"><div><span className="panel-label">STORYBOARD TIMELINE</span><strong>{showSoundTracks ? "视频分镜与文字对齐" : "视频片段选择与裁剪"}</strong><p>{showSoundTracks ? "先在下方胶片轨道定位原视频画面，再拖动入点和出点选择精彩片段。" : "拖动入点和出点选择精彩片段，确认后会保存并复用于后续方案。"}</p></div><span className="storyboard-current">当前 {formatSeconds(playhead)} / {formatSeconds(total)}</span></div>
    {outOfRangeOverlays.length > 0 && <div className="timeline-warning">有 {outOfRangeOverlays.length} 条文字超出当前成片时长，当前预览不会显示它们。</div>}
    <div className="storyboard-scroll"><div className="storyboard-track-stack" style={{ minWidth: `${trackWidth}px` }}>
      <TimeRuler total={total} />
      <StoryboardTrack label="视频"><div className="storyboard-video-row">{positionedClips.map(item => <div className={`storyboard-clip${selectedClip?.clip.id === item.clip.id ? " is-selected" : ""}`} key={item.clip.id} style={positionStyle(item.start, item.end, total)} onClick={() => { setSelectedClipId(item.clip.id); movePlayhead(item.start); }}><div className="storyboard-thumb">{item.clip.sourceUrl ? <video muted loop autoPlay playsInline preload="metadata" src={clipPlaybackUrl(item.clip)} /> : <span className="storyboard-thumb-placeholder">待下载</span>}</div><div className="storyboard-clip-label"><strong>{item.clip.dish}</strong><small>{formatSeconds(item.start)} - {formatSeconds(item.end)} · 源 {formatSeconds(item.clip.sourceStartSeconds ?? 0)} - {formatSeconds(item.clip.sourceEndSeconds ?? item.clip.sourceDurationSeconds ?? item.clip.timelineDuration)}</small></div></div>)}</div></StoryboardTrack>
      {selectedClip && onUpdateClip && <StoryboardTrack label="裁剪"><ClipTrimEditor item={selectedClip} onUpdateClip={onUpdateClip} onPreviewSource={sourceTime => previewSourceFrame(selectedClip, sourceTime)} /></StoryboardTrack>}
      {showSoundTracks && <StoryboardTrack label="文字" style={{ minHeight: rangeTrackHeight(overlayLanes.length) }}><div className="storyboard-range-lane-stack">{overlayLanes.map((lane, laneIndex) => <div className="storyboard-range-lane" key={"overlay-lane-" + laneIndex}>{lane.map(renderOverlayItem)}</div>)}</div></StoryboardTrack>}
      {showSoundTracks && <StoryboardTrack label="人声" style={{ minHeight: rangeTrackHeight(voiceLanes.length) }}><div className="storyboard-range-lane-stack">{voiceLanes.length > 0 ? voiceLanes.map((lane, laneIndex) => <div className="storyboard-range-lane" key={"voice-lane-" + laneIndex}>{lane.map(renderVoiceItem)}</div>) : <span className="storyboard-audio-empty">未配置人声</span>}</div></StoryboardTrack>}
      {showSoundTracks && <StoryboardTrack label="BGM"><AudioTrackBlock className="bgm-track-block" label={bgmName?.trim() ? `BGM · ${bgmName}` : "未上传 BGM"} tone="bgm" total={total} /></StoryboardTrack>}
      <div className="storyboard-playhead" style={{ left: playheadLeft }} aria-hidden="true" />
    </div></div>
    <label className="storyboard-scrubber"><span>播放指针</span><input aria-label="时间线播放指针" type="range" min="0" max={Math.max(total, 0)} step="0.05" value={playhead} onChange={event => movePlayhead(Number(event.target.value))} /><output>{formatSeconds(playhead)}</output></label>
    <div className="storyboard-preview"><div className="storyboard-preview-media" ref={previewMediaRef}>{activeClip?.clip.sourceUrl ? <video ref={previewVideoRef} muted playsInline preload="metadata" src={clipPlaybackUrl(activeClip.clip)} /> : <div className="storyboard-preview-placeholder">{clips.length ? "当前片段暂无本地视频" : "先把视频片段加入成片时间线"}</div>}{showSoundTracks && activeOverlays.length > 0 && <div className="storyboard-preview-overlays">{activeOverlays.map(item => <span className={`preview-overlay preview-${item.position}`} style={overlayPreviewStyle(item)} onPointerDown={event => startOverlayPositionDrag(event, item)} key={item.id}>{previewOverlayText(item, playhead) || "未填写文字"}</span>)}</div>}</div><div className="storyboard-preview-meta"><strong>{activeClip?.clip.dish || "暂无片段"}</strong><span>{activeClip ? `${formatSeconds(activeClip.start)} - ${formatSeconds(activeClip.end)} · ${showSoundTracks ? activeOverlays.length ? `当前文字：${activeOverlays.map(item => previewOverlayText(item, playhead) || "未填写").join(" / ")}` : "当前时间无画面文字" : `已选源片段 ${formatSeconds(activeClip.clip.sourceStartSeconds ?? 0)} - ${formatSeconds(activeClip.clip.sourceEndSeconds ?? activeClip.clip.timelineDuration)}`}` : showSoundTracks ? "播放指针移动到文字时间段后，文字会出现在左侧 9:16 预览中" : "选择视频片段后，可在左侧预览确认画面"}</span>{!showSoundTracks && activeClip && <button type="button" className="btn storyboard-preview-replay" onClick={replaySelectedRange}>预览所选片段</button>}{!showSoundTracks && selectedClip && <button type="button" className="btn btn-primary storyboard-preview-replay" disabled={selectedClip.clip.trimConfirmed} onClick={confirmSelectedClip}>{selectedClip.clip.trimConfirmed ? "已确定所选片段" : "确定所选片段"}</button>}{showSoundTracks && activeOverlays.length > 0 && <div className="storyboard-active-overlay-list">{activeOverlays.map(item => <span key={item.id}>{previewOverlayText(item, playhead) || "未填写文字"} · {positionLabel(item.position)}</span>)}</div>}</div></div>
  </section>;
}

function ClipTrimEditor({ item, onUpdateClip, onPreviewSource }: { item: PositionedClip; onUpdateClip: (clipId: string, patch: Partial<TimelineClip>) => void; onPreviewSource: (sourceTime: number) => void }) {
  const clip = item.clip;
  const sourceDuration = Math.max(0.1, clip.sourceDurationSeconds ?? clip.sourceEndSeconds ?? clip.timelineDuration);
  const start = clamp(clip.sourceStartSeconds ?? 0, 0, sourceDuration);
  const end = clamp(clip.sourceEndSeconds ?? Math.min(sourceDuration, start + clip.timelineDuration), start + 0.1, sourceDuration);
  const stripRef = useRef<HTMLDivElement>(null);
  const [dragEdge, setDragEdge] = useState<"start" | "end" | null>(null);
  const frameCount = Math.max(8, Math.min(18, Math.ceil(sourceDuration * 2)));
  const frameTimes = Array.from({ length: frameCount }, (_, index) => (index / Math.max(1, frameCount - 1)) * sourceDuration);

  useEffect(() => {
    if (!dragEdge) return;
    const onPointerMove = (event: PointerEvent) => {
      const rect = stripRef.current?.getBoundingClientRect();
      if (!rect || rect.width <= 0) return;
      const nextTime = clamp(((event.clientX - rect.left) / rect.width) * sourceDuration, 0, sourceDuration);
      const minimum = 0.1;
      if (dragEdge === "start") {
        const nextStart = clamp(nextTime, 0, end - minimum);
        onUpdateClip(clip.id, { sourceStartSeconds: roundClipSeconds(nextStart), timelineDuration: roundClipSeconds(end - nextStart), trimConfirmed: false });
      } else {
        const nextEnd = clamp(nextTime, start + minimum, sourceDuration);
        onUpdateClip(clip.id, { sourceEndSeconds: roundClipSeconds(nextEnd), timelineDuration: roundClipSeconds(nextEnd - start), trimConfirmed: false });
      }
    };
    const onPointerUp = () => setDragEdge(null);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [clip.id, dragEdge, end, onUpdateClip, sourceDuration, start]);

  const sourceTimeFromEvent = (event: ReactPointerEvent<HTMLDivElement>) => {
    const rect = stripRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return;
    onPreviewSource(clamp(((event.clientX - rect.left) / rect.width) * sourceDuration, 0, sourceDuration));
  };

  return <div className="clip-trim-editor">
    <div className="clip-trim-head"><div><span className="panel-label">PRECISION TRIM</span><strong>{clip.dish} · 选择精彩画面</strong><p>胶片轨道展示原视频完整时长；点击画面定位，拖动两侧标记设置入点和出点。</p></div><span className="clip-trim-values">原片 {formatSeconds(sourceDuration)} · 已选 {formatSeconds(end - start)}</span></div>
    <div className="clip-filmstrip-wrap"><div className="clip-filmstrip" ref={stripRef} onPointerDown={sourceTimeFromEvent}>{clip.sourceUrl ? frameTimes.map((time, index) => <button type="button" className="clip-film-frame" key={`${clip.id}-frame-${index}`} onPointerDown={event => event.stopPropagation()} onClick={() => onPreviewSource(time)}><img src={clipThumbnailUrl(clip, time)} alt={`${clip.dish} ${formatSeconds(time)}`} /></button>) : <span className="clip-filmstrip-empty">当前片段没有本地视频</span>}<div className="clip-trim-selected" style={{ left: `${(start / sourceDuration) * 100}%`, width: `${((end - start) / sourceDuration) * 100}%` }} /><button type="button" className="clip-source-handle clip-source-handle-start" aria-label={`调整${clip.dish}入点`} style={{ left: `${(start / sourceDuration) * 100}%` }} onPointerDown={event => { event.preventDefault(); event.stopPropagation(); setDragEdge("start"); }} /><button type="button" className="clip-source-handle clip-source-handle-end" aria-label={`调整${clip.dish}出点`} style={{ left: `${(end / sourceDuration) * 100}%` }} onPointerDown={event => { event.preventDefault(); event.stopPropagation(); setDragEdge("end"); }} /></div></div>
    <div className="clip-trim-scale"><span>0s</span><span>{formatSeconds(sourceDuration / 2)}</span><span>{formatSeconds(sourceDuration)}</span></div>
    <div className="clip-trim-foot"><span>入点 {formatSeconds(start)}</span><span>出点 {formatSeconds(end)}</span><span>成片使用 {formatSeconds(end - start)}</span></div>
  </div>;
}

function clipFilename(clip: TimelineClip): string | null {
  if (clip.filename) return clip.filename;
  const sourceUrl = clip.sourceUrl ?? "";
  const prefix = "/api/canvas/clips/library/";
  return sourceUrl.startsWith(prefix) ? decodeURIComponent(sourceUrl.slice(prefix.length)) : null;
}

function clipPlaybackUrl(clip: TimelineClip): string {
  const filename = clipFilename(clip);
  return filename
    ? `/api/canvas/clips/playback/${encodeURIComponent(filename)}`
    : (clip.previewUrl ?? clip.sourceUrl ?? "");
}

function clipThumbnailUrl(clip: TimelineClip, at: number): string {
  const filename = clipFilename(clip);
  return filename
    ? `/api/canvas/clips/thumbnails/${encodeURIComponent(filename)}?at=${encodeURIComponent(at.toFixed(3))}`
    : "";
}

function TimelineRangeBlock({ className, label, tone, total: _total, locked = false, style, removeLabel, onRemove, onClick, onPointerDown, onResizeStart, onResizeEnd }: { className: string; label: string; tone?: "voice"; total: number; locked?: boolean; style?: CSSProperties; removeLabel?: string; onRemove?: () => void; onClick?: () => void; onPointerDown?: (event: ReactPointerEvent<HTMLDivElement>) => void; onResizeStart?: (event: ReactPointerEvent<HTMLButtonElement>) => void; onResizeEnd?: (event: ReactPointerEvent<HTMLButtonElement>) => void }) {
  return <div className={`storyboard-range-block ${className}`} style={style} role="button" tabIndex={0} onPointerDown={onPointerDown} onClick={onClick}>
    {!locked && <button type="button" className="storyboard-range-handle range-handle-start" aria-label="Resize start" onPointerDown={onResizeStart} />}
    <div className="storyboard-range-content">{tone === "voice" && <div className="storyboard-waveform" aria-hidden="true">{Array.from({ length: 48 }, (_, index) => <i key={index} style={{ height: `${20 + ((index * 17 + 7) % 64)}%` }} />)}</div>}<span>{label}</span></div>
    {onRemove && <button type="button" className="storyboard-range-remove" aria-label={removeLabel || "删除片段"} title={removeLabel || "删除片段"} onPointerDown={event => { event.preventDefault(); event.stopPropagation(); }} onClick={event => { event.preventDefault(); event.stopPropagation(); onRemove(); }}>×</button>}
    {!locked && <button type="button" className="storyboard-range-handle range-handle-end" aria-label="Resize end" onPointerDown={onResizeEnd} />}
  </div>;
}

function AudioTrackBlock({ className, label, tone, total, style, onClick }: { className: string; label: string; tone: "voice" | "bgm"; total: number; style?: CSSProperties; onClick?: () => void }) {
  const content = <><div className="storyboard-waveform" aria-hidden="true">{Array.from({ length: 48 }, (_, index) => <i key={index} style={{ height: `${20 + ((index * 17 + (tone === "voice" ? 7 : 13)) % 64)}%` }} />)}</div><span className="storyboard-audio-label">{label}</span></>;
  return onClick ? <button type="button" className={`storyboard-audio-row ${className}`} style={{ width: `${Math.max(100, total > 0 ? 100 : 0)}%`, ...style }} onClick={onClick}>{content}</button> : <div className={`storyboard-audio-row ${className}`} style={{ width: `${Math.max(100, total > 0 ? 100 : 0)}%`, ...style }}>{content}</div>;
}

function TimeRuler({ total }: { total: number }) {
  const ticks = Array.from({ length: Math.max(1, Math.ceil(total) + 1) }, (_, index) => index);
  return <div className="storyboard-ruler">{ticks.map(tick => <span key={tick} style={{ left: `${clamp((tick / Math.max(total, 0.1)) * 100, 0, 100)}%` }}>{tick}s</span>)}</div>;
}

function StoryboardTrack({ label, children, style }: { label: string; children: ReactNode; style?: CSSProperties }) {
  return <div className="storyboard-track"><span className="storyboard-track-label">{label}</span><div className="storyboard-track-lane" style={style}>{children}</div></div>;
}

function formatSeconds(value: number) {
  const rounded = Math.round(value * 100) / 100;
  return `${Number.isInteger(rounded * 10) ? rounded.toFixed(1) : rounded.toFixed(2)}s`;
}

function previewOverlayText(item: OverlayItem, playhead: number) {
  if (item.animation !== "typewriter" || !item.text) return item.text;
  const characters = Array.from(item.text);
  const progress = clamp((playhead - item.startSeconds) / Math.max(0.1, item.endSeconds - item.startSeconds), 0, 1);
  return characters.slice(0, Math.max(1, Math.ceil(characters.length * progress))).join("");
}

function roundSeconds(value: number) {
  return Math.round(value * 10) / 10;
}

function roundClipSeconds(value: number) {
  return Math.round(value * 20) / 20;
}

function roundRatio(value: number) {
  return Math.round(value * 1000) / 1000;
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

function layoutRangeLanes<T extends { startSeconds: number; endSeconds: number }>(items: T[]): T[][] {
  const lanes: T[][] = [];
  const sorted = items
    .map((item, index) => ({ item, index }))
    .sort((left, right) => left.item.startSeconds - right.item.startSeconds || left.index - right.index);
  sorted.forEach(({ item }) => {
    const laneIndex = lanes.findIndex(lane => (lane[lane.length - 1]?.endSeconds ?? -Infinity) <= item.startSeconds);
    if (laneIndex < 0) lanes.push([item]);
    else lanes[laneIndex].push(item);
  });
  return lanes;
}

function rangeTrackHeight(laneCount: number) {
  return Math.max(76, laneCount * 40 + 8);
}

function overlayTrackStyle(item: OverlayItem): CSSProperties {
  const style = overlayStyleFromItem(item);
  return { color: style.color, fontWeight: style.fontWeight, backgroundColor: rgba(style.backgroundColor, style.backgroundOpacity) };
}

function overlayPreviewStyle(item: OverlayItem): CSSProperties {
  const style = overlayStyleFromItem(item);
  const position = overlayCoordinatesFromItem(item);
  return {
    color: style.color,
    fontFamily: style.fontFamily,
    fontSize: `${Math.max(10, style.fontSize / 4)}px`,
    fontWeight: style.fontWeight,
    backgroundColor: style.backgroundEnabled ? rgba(style.backgroundColor, style.backgroundOpacity) : "transparent",
    textShadow: style.strokeWidth > 0 ? `0 0 ${style.strokeWidth}px ${style.strokeColor}` : "none",
    left: `${position.x * 100}%`,
    top: `${position.y * 100}%`,
    transform: "translate(-50%, -50%)",
    width: `${style.textBoxWidth * 100}%`,
    maxWidth: `${style.textBoxWidth * 100}%`,
    whiteSpace: style.singleLine ? "nowrap" : "normal",
    overflowWrap: style.singleLine ? "normal" : "anywhere",
    boxSizing: "border-box",
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
  return position === "top" ? "上方品牌区" : position === "upper" ? "中上钩子区" : position === "center" ? "画面中央" : position === "bottom" ? "底部安全区" : "自定义位置";
}
