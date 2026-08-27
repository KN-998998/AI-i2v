# -*- coding: utf-8 -*-
"""HTTP API for the canvas-first video production workflow."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from pipeline.audio import qwen_tts_options
from pipeline.config import (
    BACKGROUND_REMOVAL_PROVIDER,
    CANVAS_CLIP_ROOT,
    KLING_ACCESS_KEY,
    KLING_API_KEY,
    KLING_BASE_URL,
    KLING_MODEL,
    KLING_SECRET_KEY,
    QWEN_API_KEY,
    QWEN_TTS_MODEL,
    TENCENT_COS_BUCKET,
    TENCENT_COS_MODEL,
    TENCENTCLOUD_REGION,
    TTS_PROVIDER,
    VIDEO_ASPECT,
    VIDEO_DURATION,
    VIDEO_RESOLUTION,
    VIDEO_SILENT,
)
from web.services.canvas_compose import compose_output_path, get_compose_job, start_compose
from web.services.canvas_asset_library import ASSET_CATEGORIES, build_asset_plan
from web.services.canvas_generation import get_generation_job, start_generation
from web.services.canvas_image_processing import get_image_processing_job, start_image_processing, tencent_matting_configured
from web.services.canvas_quality import analyze_image, analyze_video, preflight_draft
from web.services.canvas_state import background_file, list_background_files, load_draft, save_background_upload, save_draft, save_upload, uploaded_file

router = APIRouter()
CANVAS_CLIP_PREVIEW_ROOT = CANVAS_CLIP_ROOT / ".previews"
CANVAS_CLIP_THUMBNAIL_ROOT = CANVAS_CLIP_ROOT / ".thumbnails"


@router.get("/api/canvas/tts/options")
def list_canvas_tts_options() -> dict[str, Any]:
    configured = bool(QWEN_API_KEY) and TTS_PROVIDER in {"qwen", "dashscope"}
    return {
        "configured": configured,
        "provider": "qwen" if configured else None,
        "default_model": QWEN_TTS_MODEL if configured else None,
        "voices": qwen_tts_options() if configured else [],
    }


def _clip_label(filename: str) -> str:
    match = re.search(r"(?:_|-)roll[_-]?(\d+)", Path(filename).stem, re.IGNORECASE)
    return f"Roll {match.group(1)}" if match else "本地片段"


def _canvas_clip_dish(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"(?:_|-)roll[_-]?\d+.*$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"_v\d+.*$", "", stem, flags=re.IGNORECASE)
    return stem or Path(filename).stem


def _read_video_duration_seconds(path: str | Path) -> float | None:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
        return float(result.stdout.strip()) if result.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _ensure_browser_preview(clip_path: Path, analysis: dict[str, Any]) -> str | None:
    if str(analysis.get("codec") or "").lower() in {"h264", "avc1"}:
        return None
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    CANVAS_CLIP_PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    preview_path = CANVAS_CLIP_PREVIEW_ROOT / f"{clip_path.stem}.preview.mp4"
    if not preview_path.exists():
        temporary = preview_path.with_suffix(".tmp.mp4")
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(clip_path), "-an", "-vf", "scale=w=720:h=-2:force_original_aspect_ratio=decrease", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        if result.returncode != 0 or not temporary.is_file():
            temporary.unlink(missing_ok=True)
            return None
        temporary.replace(preview_path)
    return f"/api/canvas/clips/previews/{preview_path.name}"


def _clip_thumbnail(clip_path: Path, at_seconds: float) -> Path | None:
    """Extract and cache a JPEG frame so all source codecs remain inspectable."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    duration = _read_video_duration_seconds(clip_path)
    if duration is None:
        return None
    timestamp = max(0.0, min(float(at_seconds), max(0.0, duration - 0.04)))
    token = int(round(timestamp * 100))
    CANVAS_CLIP_THUMBNAIL_ROOT.mkdir(parents=True, exist_ok=True)
    thumbnail_path = CANVAS_CLIP_THUMBNAIL_ROOT / f"{clip_path.stem}_{token:06d}.jpg"
    if thumbnail_path.is_file():
        return thumbnail_path
    temporary = thumbnail_path.with_suffix(".tmp.jpg")
    result = subprocess.run(
        [
            ffmpeg, "-y", "-ss", f"{timestamp:.3f}", "-i", str(clip_path),
            "-frames:v", "1", "-vf", "scale=w=240:h=135:force_original_aspect_ratio=decrease",
            "-q:v", "3", str(temporary),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0 or not temporary.is_file():
        temporary.unlink(missing_ok=True)
        return None
    temporary.replace(thumbnail_path)
    return thumbnail_path


def _canvas_clip_payload(clip_path: Path) -> dict[str, Any] | None:
    analysis = analyze_video(clip_path, _canvas_clip_dish(clip_path.name))
    duration = analysis.get("durationSeconds") or _read_video_duration_seconds(clip_path)
    if duration is None:
        return None
    return {
        "id": f"clip_canvas_{clip_path.name}",
        "filename": clip_path.name,
        "dish": _canvas_clip_dish(clip_path.name),
        "label": _clip_label(clip_path.name),
        "tone": "#355e62",
        "durationSeconds": round(float(duration), 2),
        "timelineDuration": min(round(float(duration), 2), 2.5),
        "sourceDurationSeconds": round(float(duration), 2),
        "sourceStartSeconds": min(0.5, max(0.0, float(duration) - 0.1)),
        "sourceEndSeconds": round(float(duration), 2),
        "status": "generated",
        "sourcePath": str(clip_path.resolve()),
        "sourceUrl": f"/api/canvas/clips/library/{clip_path.name}",
        "previewUrl": _ensure_browser_preview(clip_path, analysis),
        "qualityScore": analysis.get("qualityScore", 50),
        "qualityLabel": analysis.get("qualityLabel", "warning"),
        "qualityWarnings": analysis.get("qualityWarnings", []),
        "analysisMode": analysis.get("analysisMode", "technical_rules"),
        "dishCategory": analysis.get("category", "其他"),
    }


@router.get("/api/canvas/clips")
def list_canvas_clips() -> list[dict[str, Any]]:
    if not CANVAS_CLIP_ROOT.is_dir():
        return []
    items = (_canvas_clip_payload(path) for path in CANVAS_CLIP_ROOT.glob("*.mp4"))
    return sorted((item for item in items if item is not None), key=lambda item: (item["dish"], item["filename"]))


@router.get("/api/canvas/clips/library/{filename}")
def serve_canvas_library_clip(filename: str) -> FileResponse:
    clip_path = CANVAS_CLIP_ROOT / Path(filename).name
    if clip_path.suffix.lower() != ".mp4" or not clip_path.is_file():
        raise _json_error("视频片段不存在", 404)
    return FileResponse(str(clip_path), media_type="video/mp4")


@router.get("/api/canvas/clips/playback/{filename}")
def serve_canvas_playback_clip(filename: str) -> FileResponse:
    clip_path = CANVAS_CLIP_ROOT / Path(filename).name
    if clip_path.suffix.lower() != ".mp4" or not clip_path.is_file():
        raise _json_error("视频片段不存在", 404)
    analysis = analyze_video(clip_path, _canvas_clip_dish(clip_path.name))
    preview_url = _ensure_browser_preview(clip_path, analysis)
    if preview_url:
        preview_path = CANVAS_CLIP_PREVIEW_ROOT / Path(preview_url).name
        if preview_path.is_file():
            return FileResponse(str(preview_path), media_type="video/mp4")
    return FileResponse(str(clip_path), media_type="video/mp4")


@router.get("/api/canvas/clips/thumbnails/{filename}")
def serve_canvas_clip_thumbnail(filename: str, at: float = 0) -> FileResponse:
    clip_path = CANVAS_CLIP_ROOT / Path(filename).name
    if clip_path.suffix.lower() != ".mp4" or not clip_path.is_file():
        raise _json_error("视频片段不存在", 404)
    try:
        thumbnail_path = _clip_thumbnail(clip_path, at)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise _json_error("视频缩略图生成失败", 500) from exc
    if thumbnail_path is None:
        raise _json_error("无法生成视频缩略图，请检查 ffmpeg", 500)
    return FileResponse(str(thumbnail_path), media_type="image/jpeg")


@router.get("/api/canvas/clips/previews/{filename}")
def serve_canvas_library_preview(filename: str) -> FileResponse:
    preview_path = CANVAS_CLIP_PREVIEW_ROOT / Path(filename).name
    if preview_path.suffix.lower() != ".mp4" or not preview_path.is_file():
        raise _json_error("视频预览不存在", 404)
    return FileResponse(str(preview_path), media_type="video/mp4")


@router.get("/api/canvas/drafts/{draft_id}")
def get_canvas_draft(draft_id: str) -> dict[str, Any]:
    try:
        draft = load_draft(draft_id)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        raise _json_error("草稿读取失败", 500) from exc
    if draft is None:
        raise _json_error("草稿不存在", 404)
    return draft


@router.put("/api/canvas/drafts/{draft_id}")
def put_canvas_draft(draft_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return save_draft(draft_id, payload)
    except (ValueError, TypeError, OSError) as exc:
        raise _json_error(str(exc), 400) from exc


@router.post("/api/canvas/drafts/{draft_id}/files")
async def upload_canvas_file(draft_id: str, kind: str = Form(...), dish: str = Form(""), category: str = Form(""), file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        metadata = await save_upload(draft_id, file, kind)
    except (ValueError, OSError) as exc:
        raise _json_error(str(exc), 400) from exc
    metadata["url"] = f"/api/canvas/drafts/{draft_id}/files/{metadata['stored_name']}"
    if kind == "image" and (path := uploaded_file(draft_id, metadata["stored_name"])) is not None:
        metadata["analysis"] = analyze_image(path, dish, category or None)
    return metadata


@router.get("/api/canvas/drafts/{draft_id}/files/{stored_name}")
def get_canvas_file(draft_id: str, stored_name: str) -> FileResponse:
    path = uploaded_file(draft_id, stored_name)
    if path is None:
        raise _json_error("文件不存在", 404)
    return FileResponse(str(path))


@router.get("/api/canvas/backgrounds")
def list_canvas_backgrounds() -> list[dict[str, Any]]:
    return [{"id": path.name, "name": path.name, "url": f"/api/canvas/backgrounds/{path.name}", "source": "local"} for path in list_background_files()]


@router.post("/api/canvas/asset-library/plan")
def create_asset_library_plan(draft_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request = payload or {}
    counts = request.get("category_counts") or {}
    if not isinstance(counts, dict):
        raise _json_error("分类数量必须是对象")
    unknown = set(counts) - set(ASSET_CATEGORIES)
    if unknown:
        raise _json_error(f"不支持的素材分类：{', '.join(sorted(unknown))}")
    try:
        return build_asset_plan(
            draft_id,
            str(request.get("asset_root") or ""),
            str(request.get("background_root") or ""),
            counts,
        )
    except (OSError, ValueError) as exc:
        raise _json_error(str(exc), 400) from exc


@router.post("/api/canvas/asset-library/pick-folder")
def pick_asset_library_folder(payload: dict[str, Any] | None = None) -> dict[str, str]:
    """Open a local folder picker for the desktop-only local workflow."""
    title = str((payload or {}).get("title") or "选择素材库文件夹")
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            selected = filedialog.askdirectory(title=title, mustexist=True)
        finally:
            root.destroy()
    except Exception as exc:
        raise _json_error("本机文件夹选择器不可用，请手动填写路径", 400) from exc
    return {"path": str(selected or "")}


@router.post("/api/canvas/backgrounds")
async def upload_canvas_background(file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        metadata = await save_background_upload(file)
    except (ValueError, OSError) as exc:
        raise _json_error(str(exc), 400) from exc
    return {**metadata, "id": metadata["stored_name"], "name": metadata["original_name"], "url": f"/api/canvas/backgrounds/{metadata['stored_name']}", "source": "local"}


@router.get("/api/canvas/backgrounds/{stored_name}")
def get_canvas_background(stored_name: str) -> FileResponse:
    path = background_file(stored_name)
    if path is None:
        raise _json_error("背景模板不存在", 404)
    return FileResponse(str(path))


@router.post("/api/canvas/drafts/{draft_id}/image-processing")
def start_canvas_image_processing(draft_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return start_image_processing(draft_id, str((payload or {}).get("node_id") or ""))
    except (ValueError, RuntimeError) as exc:
        raise _json_error(str(exc), 400) from exc


@router.get("/api/canvas/drafts/{draft_id}/image-processing/{job_id}")
def get_canvas_image_processing_status(draft_id: str, job_id: str) -> dict[str, Any]:
    job = get_image_processing_job(draft_id, job_id)
    if job is None:
        raise _json_error("图片处理任务不存在", 404)
    return job


@router.post("/api/canvas/drafts/{draft_id}/generations")
def start_canvas_generation(draft_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        request = payload or {}
        return start_generation(draft_id, str(request.get("node_id") or ""), force=bool(request.get("force", False)))
    except (ValueError, RuntimeError) as exc:
        raise _json_error(str(exc), 400) from exc


@router.get("/api/canvas/drafts/{draft_id}/generations/{job_id}")
def get_canvas_generation_status(draft_id: str, job_id: str) -> dict[str, Any]:
    job = get_generation_job(draft_id, job_id)
    if job is None:
        raise _json_error("生成任务不存在", 404)
    return job


@router.post("/api/canvas/drafts/{draft_id}/preflight")
def canvas_preflight(draft_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    draft = load_draft(draft_id)
    if draft is None:
        raise _json_error("画布草稿不存在，请先保存草稿", 404)
    request = payload or {}
    return preflight_draft(draft, draft_id, request.get("workspace_id"), include_sound=bool(request.get("include_sound", True)))


@router.post("/api/canvas/drafts/{draft_id}/compose")
def compose_canvas_draft(draft_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        request = payload or {}
        return start_compose(draft_id, workspace_id=request.get("workspace_id"), include_sound=bool(request.get("include_sound", False)))
    except ValueError as exc:
        raise _json_error(str(exc), 400) from exc


@router.get("/api/canvas/drafts/{draft_id}/compose/{job_id}")
def get_canvas_compose_status(draft_id: str, job_id: str) -> dict[str, Any]:
    job = get_compose_job(draft_id, job_id)
    if job is None:
        raise _json_error("合成任务不存在", 404)
    return job


@router.get("/api/canvas/drafts/{draft_id}/compose/{job_id}/file")
def get_canvas_compose_file(draft_id: str, job_id: str) -> FileResponse:
    path = compose_output_path(draft_id, job_id)
    if path is None:
        raise _json_error("合成视频尚未生成", 404)
    return FileResponse(str(path), media_type="video/mp4", filename="canvas_composed.mp4")


@router.get("/api/config")
def get_config() -> dict[str, Any]:
    auth_mode = "api_key" if KLING_API_KEY else "ak_sk" if KLING_ACCESS_KEY and KLING_SECRET_KEY else "none"
    return {
        "kling": bool(KLING_API_KEY or (KLING_ACCESS_KEY and KLING_SECRET_KEY)),
        "kling_auth_mode": auth_mode,
        "kling_base_url": KLING_BASE_URL,
        "kling_model": KLING_MODEL,
        "video_spec": {"duration_seconds": VIDEO_DURATION, "resolution": VIDEO_RESOLUTION, "aspect_ratio": VIDEO_ASPECT, "silent": VIDEO_SILENT, "supports_last_frame": True},
        "image_processing": {"provider": BACKGROUND_REMOVAL_PROVIDER or None, "model": TENCENT_COS_MODEL, "region": TENCENTCLOUD_REGION, "bucket_configured": bool(TENCENT_COS_BUCKET), "configured": tencent_matting_configured()},
    }


def _json_error(message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)
