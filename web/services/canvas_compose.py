# -*- coding: utf-8 -*-
"""Compose the real video files referenced by a canvas draft."""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.config import CANVAS_CLIP_ROOT, OUTPUT_ROOT, batch_subdirs
from web.services.canvas_state import draft_directory, load_draft, uploaded_file
from web.services.canvas_quality import preflight_draft

_JOB_ID_RE = r"^[0-9a-f]{32}$"
_JOB_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _job_path(draft_id: str, job_id: str) -> Path:
    return draft_directory(draft_id) / f"compose-{job_id}.json"


def _save_job(draft_id: str, job: dict[str, Any]) -> None:
    path = _job_path(draft_id, job["job_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(job, stream, ensure_ascii=False, indent=2)
    temporary.replace(path)


def get_compose_job(draft_id: str, job_id: str) -> dict[str, Any] | None:
    if not job_id or not re.fullmatch(_JOB_ID_RE, job_id):
        return None
    path = _job_path(draft_id, job_id)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError):
        return None


def _find_generated_clip(dish: str) -> Path | None:
    if not dish:
        return None
    candidates = []
    if CANVAS_CLIP_ROOT.is_dir():
        candidates.extend(path for path in CANVAS_CLIP_ROOT.glob("*.mp4") if dish in path.name)
    if not OUTPUT_ROOT.exists():
        return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None
    for batch_dir in OUTPUT_ROOT.glob("batch_*"):
        clips_dir = batch_subdirs(batch_dir)["clips"]
        candidates.extend(path for path in clips_dir.glob("*.mp4") if dish in path.name)
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def _allowed_source(path: Path, draft_id: str) -> bool:
    resolved = path.resolve()
    allowed_roots = [OUTPUT_ROOT.resolve(), draft_directory(draft_id).resolve()]
    return any(resolved == root or root in resolved.parents for root in allowed_roots)


def _resolve_source(draft_id: str, clip: dict[str, Any]) -> Path | None:
    source = clip.get("sourcePath") or clip.get("source_path")
    path = Path(str(source)).expanduser() if source else _find_generated_clip(str(clip.get("dish", "")))
    if path is None or not path.exists() or path.suffix.lower() not in {".mp4", ".mov", ".m4v", ".webm"}:
        return None
    return path.resolve() if _allowed_source(path, draft_id) else None


def _clip_trim_range(clip: dict[str, Any]) -> tuple[float, float]:
    source_duration = max(0.1, float(clip.get("sourceDurationSeconds") or clip.get("durationSeconds") or 3.0))
    start = max(0.0, min(source_duration - 0.1, float(clip.get("sourceStartSeconds") or 0.0)))
    default_end = start + max(0.1, float(clip.get("timelineDuration") or 2.5))
    end = max(start + 0.1, min(source_duration, float(clip.get("sourceEndSeconds") or default_end)))
    return start, end


def _prepare_sources(draft_id: str, timeline: list[dict[str, Any]]) -> list[tuple[dict[str, Any], Path]]:
    if not timeline:
        raise ValueError("时间线中没有可合成的视频片段")
    prepared = []
    missing = []
    for clip in timeline:
        source = _resolve_source(draft_id, clip)
        if source is None:
            missing.append(str(clip.get("dish") or clip.get("id") or "未命名片段"))
            continue
        prepared.append((clip, source))
    if missing:
        names = "、".join(missing)
        raise ValueError(f"以下片段没有关联真实视频文件：{names}。请先生成或上传视频片段")
    return prepared


def _sound_node(draft: dict[str, Any]) -> dict[str, Any]:
    for node in draft.get("nodes", []):
        data = node.get("data", {}) if isinstance(node, dict) else {}
        if data.get("kind") == "sound":
            return data
    return {}


def _overlay_items(sound: dict[str, Any], voice_timings: dict[str, tuple[float, float]] | None = None) -> list[dict[str, Any]]:
    items = sound.get("overlayItems")
    if isinstance(items, list):
        result = []
        for item in items:
            if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                continue
            start = max(0.0, float(item.get("startSeconds", 0) or 0))
            end = max(start + 0.1, float(item.get("endSeconds", start + 2.5) or start + 2.5))
            sync_voice_id = str(item.get("syncVoiceId") or "")
            if voice_timings and sync_voice_id in voice_timings:
                start, end = voice_timings[sync_voice_id]
            result.append({
                "text": str(item["text"]),
                "start": start,
                "end": end,
                "position": item.get("position", "upper"),
                "x": item.get("x"),
                "y": item.get("y"),
                "animation": item.get("animation", "static"),
                "sync_voice_id": sync_voice_id or None,
                "style": item.get("style") if isinstance(item.get("style"), dict) else {},
            })
        return result
    main = str(sound.get("overlayMain", "")).strip()
    cta = str(sound.get("overlayCta", "")).strip()
    start = max(0.0, float(str(sound.get("overlayStart", "0")).rstrip("s")) or 0)
    end = max(start + 0.1, float(str(sound.get("overlayEnd", "2.5")).rstrip("s")) or 2.5)
    position = "top" if "顶部" in str(sound.get("overlayPosition", "")) else "upper" if "中上" in str(sound.get("overlayPosition", "")) else "center" if "中央" in str(sound.get("overlayPosition", "")) else "bottom"
    result = []
    if main:
        result.append({"text": main, "start": start, "end": end, "position": position, "style": {}})
    if cta and cta != main:
        result.append({"text": cta, "start": max(0.0, end - 2), "end": end, "position": "top", "style": {}})
    return result


def _uploaded_audio_path(draft_id: str, url: str | None) -> Path | None:
    if not url:
        return None
    path = uploaded_file(draft_id, Path(url.split("?", 1)[0]).name)
    return path


def _voice_items(sound: dict[str, Any]) -> list[dict[str, Any]]:
    items = sound.get("voiceItems")
    if isinstance(items, list):
        result = []
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                continue
            start = max(0.0, float(item.get("startSeconds", 0) or 0))
            end = max(start + 0.1, float(item.get("endSeconds", start + 4) or start + 4))
            result.append({
                "id": str(item.get("id") or f"voice_{index + 1}"),
                "text": str(item["text"]),
                "start": start,
                "end": end,
                "voice_id": str(item.get("voiceId") or ""),
                "provider": str(item.get("provider") or "qwen"),
                "model": str(item.get("model") or ""),
                "voice": str(item.get("voiceName") or sound.get("voiceName") or "none"),
                "volume": max(0.0, min(float(item.get("volume", sound.get("voiceVolume", 85)) or 85) / 100, 1.0)),
            })
        return result
    text = str(sound.get("voiceText", "")).strip()
    return [{"text": text, "start": 0.0, "end": 4.0, "voice_id": "", "provider": "qwen", "model": "", "voice": str(sound.get("voiceName", "none")), "volume": max(0.0, min(float(sound.get("voiceVolume", 85) or 85) / 100, 1.0))}] if text else []


def start_compose(draft_id: str, workspace_id: str | None = None, include_sound: bool = False) -> dict[str, Any]:
    draft = load_draft(draft_id)
    if draft is None:
        raise ValueError("画布草稿不存在，请先保存草稿")
    workspace = next((item for item in draft.get("composeWorkspaces", []) if item.get("id") == workspace_id), None) if workspace_id else None
    timeline = (workspace or {}).get("clips") if workspace is not None else draft.get("timeline") or []
    preflight = preflight_draft(draft, draft_id, workspace_id, include_sound=include_sound)
    if not preflight["ok"]:
        detail = "；".join(item["message"] for item in preflight["errors"])
        raise ValueError(f"合成预检未通过：{detail}")
    prepared = _prepare_sources(draft_id, timeline)
    job_id = uuid.uuid4().hex
    job = {
        "job_id": job_id,
        "draft_id": draft_id,
        "status": "running",
        "timeline_count": len(prepared),
        "created_at": _now(),
        "updated_at": _now(),
        "output_url": None,
        "error": None,
        "workspace_id": workspace_id,
        "include_sound": include_sound,
        "preflight": preflight,
    }
    with _JOB_LOCK:
        _save_job(draft_id, job)

    def worker() -> None:
        output_dir = draft_directory(draft_id) / "compositions" / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        temporary_paths: list[str] = []
        try:
            from pipeline.step5_compose import concat_clips, trim_clip

            trimmed_paths = []
            for index, (clip, source) in enumerate(prepared):
                start, end = _clip_trim_range(clip)
                duration = max(0.1, min(end - start, 60.0))
                trimmed_path = output_dir / f"segment_{index:03d}.mp4"
                trim_clip(str(source), str(trimmed_path), start=start, duration=duration)
                trimmed_paths.append(str(trimmed_path))
                temporary_paths.append(str(trimmed_path))

            output_path = output_dir / ("canvas_final.mp4" if include_sound else "canvas_composed.mp4")
            sound = _sound_node(draft)
            voice_timings: dict[str, tuple[float, float]] = {}
            if not include_sound:
                concat_clips(trimmed_paths, str(output_path), subtitles=[], brand_info=None)
            if include_sound:
                from pipeline.step6_voice_bgm import generate_tts, get_audio_duration, merge_audio_video, mix_voice_segments

                video_duration = sum(float(clip.get("timelineDuration") or 2.5) for clip, _source in prepared)
                bgm_volume = max(0.0, min(float(sound.get("bgmVolume", 30) or 30) / 100, 1.0))
                audio_path = output_dir / "mixed_audio.m4a"
                bgm_file = _uploaded_audio_path(draft_id, draft.get("bgmUrl"))
                voice_segments = []
                for voice_index, item in enumerate(_voice_items(sound)):
                    if item["voice"] in {"", "none", "无"} and not item.get("voice_id"):
                        continue
                    segment_path = output_dir / f"voice_{voice_index:03d}.mp3"
                    generated = generate_tts(item["text"], str(segment_path), voice=item.get("voice_id") or item["voice"], model=item.get("model") or None)
                    if not generated:
                        raise RuntimeError("Qwen 人声生成失败，请检查 QWEN_API_KEY 和音色配置，或将该段音色设置为“无”")
                    actual_duration = get_audio_duration(generated)
                    if actual_duration <= 0:
                        raise RuntimeError("无法读取 TTS 音频时长，请确认 ffprobe 可用")
                    temporary_paths.append(str(segment_path))
                    effective_end = min(item["end"], item["start"] + actual_duration)
                    voice_segments.append((generated, item["start"], effective_end, item["volume"]))
                    if item.get("id"):
                        voice_timings[item["id"]] = (item["start"], effective_end)
                subtitles = _overlay_items(sound, voice_timings)
                concat_clips(trimmed_paths, str(output_path), subtitles=subtitles, brand_info=None)
                if voice_segments or (bgm_file and bgm_file.exists() and bgm_volume > 0):
                    mix_voice_segments(voice_segments, str(bgm_file) if bgm_file and bgm_file.exists() and bgm_volume > 0 else None, str(audio_path), bgm_volume=bgm_volume, video_duration=video_duration)
                    temporary_paths.append(str(audio_path))
                    merge_audio_video(str(output_path), str(audio_path), str(output_path.with_suffix(".with-audio.mp4")), video_duration=video_duration)
                    output_path.unlink(missing_ok=True)
                    output_path.with_suffix(".with-audio.mp4").replace(output_path)
            for path in temporary_paths:
                Path(path).unlink(missing_ok=True)
            job.update({
                "status": "done",
                "updated_at": _now(),
                "output_url": f"/api/canvas/drafts/{draft_id}/compose/{job_id}/file",
            })
        except Exception as exc:
            for path in temporary_paths:
                Path(path).unlink(missing_ok=True)
            job.update({"status": "error", "updated_at": _now(), "error": str(exc)})
        with _JOB_LOCK:
            _save_job(draft_id, job)

    threading.Thread(target=worker, name=f"canvas-compose-{job_id}", daemon=True).start()
    return job


def compose_output_path(draft_id: str, job_id: str) -> Path | None:
    job = get_compose_job(draft_id, job_id)
    if not job or job.get("status") != "done":
        return None
    output_dir = draft_directory(draft_id) / "compositions" / job_id
    for filename in ("canvas_final.mp4", "canvas_composed.mp4"):
        path = output_dir / filename
        if path.exists() and path.is_file():
            return path
    return None
