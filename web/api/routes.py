# -*- coding: utf-8 -*-
"""API routers for the FastAPI web workbench."""
import json
import os
import re
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from pipeline.config import (
    EXTRA_IMAGE_LIBS,
    IMAGE_LIBRARY,
    KLING_ACCESS_KEY,
    KLING_API_KEY,
    KLING_BASE_URL,
    KLING_MODEL,
    KLING_SECRET_KEY,
    CANVAS_CLIP_ROOT,
    OUTPUT_ROOT,
    QWEN_API_KEY,
    QWEN_TTS_MODEL,
    TTS_PROVIDER,
    VIDEO_ASPECT,
    VIDEO_DURATION,
    VIDEO_RESOLUTION,
    VIDEO_SILENT,
    batch_subdirs,
)
from pipeline.step6_voice_bgm import qwen_tts_options
from web.core.logging import get_logger
from web.services.pipeline_tasks import run_compose, run_step1, run_step2, run_step3
from web.services.canvas_compose import compose_output_path, get_compose_job, start_compose
from web.services.canvas_generation import get_generation_job, start_generation
from web.services.canvas_quality import analyze_image, analyze_video, preflight_draft
from web.services.planning import write_selection_csv
from web.services.canvas_state import load_draft, save_draft, save_upload, uploaded_file
from web.services.state import get_batch_state, load_manifest, load_state, save_state

router = APIRouter()
logger = get_logger(__name__)
CANVAS_CLIP_PREVIEW_ROOT = CANVAS_CLIP_ROOT / ".previews"


@router.get("/api/canvas/tts/options")
def list_canvas_tts_options() -> dict[str, Any]:
    """Expose configured Qwen voice metadata without ever exposing API keys."""
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
    if stem.startswith("omni_smoke_"):
        stem = stem.removeprefix("omni_smoke_")
        stem = re.sub(r"_\d{8}_\d{6}.*$", "", stem)
    stem = re.sub(r"(?:_|-)roll[_-]?\d+.*$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"_v\d+.*$", "", stem, flags=re.IGNORECASE)
    return stem or Path(filename).stem


def _canvas_clip_payload(clip_path: Path, source_url: str, batch_id: str | None = None) -> dict[str, Any] | None:
    analysis = analyze_video(clip_path, _canvas_clip_dish(clip_path.name))
    duration = analysis.get("durationSeconds") or _read_video_duration_seconds(clip_path)
    if duration is None:
        return None
    item: dict[str, Any] = {
        "id": f"clip_{'canvas' if batch_id is None else batch_id}_{clip_path.name}",
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
        "sourceUrl": source_url,
        "previewUrl": _ensure_browser_preview(clip_path, analysis),
        "qualityScore": analysis.get("qualityScore", 50),
        "qualityLabel": analysis.get("qualityLabel", "warning"),
        "qualityWarnings": analysis.get("qualityWarnings", []),
        "analysisMode": analysis.get("analysisMode", "technical_rules"),
        "dishCategory": analysis.get("category", "其他"),
    }
    if batch_id is not None:
        item["batchId"] = batch_id
    return item


def _ensure_browser_preview(clip_path: Path, analysis: dict[str, Any]) -> str | None:
    """Create a cached H.264 proxy when the source codec is not browser-safe."""
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
            [
                ffmpeg, "-y", "-i", str(clip_path), "-an",
                "-vf", "scale=w=720:h=-2:force_original_aspect_ratio=decrease",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary),
            ],
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


@router.get("/api/canvas/clips")
def list_canvas_clips() -> list[dict[str, Any]]:
    """List existing MP4 clips so the canvas can use real local media."""
    if not OUTPUT_ROOT.exists() and not CANVAS_CLIP_ROOT.exists():
        return []

    result: list[dict[str, Any]] = []
    if CANVAS_CLIP_ROOT.is_dir():
        for clip_path in CANVAS_CLIP_ROOT.glob("*.mp4"):
            item = _canvas_clip_payload(
                clip_path,
                f"/api/canvas/clips/library/{clip_path.name}",
            )
            if item is not None:
                result.append(item)

    for batch_dir in OUTPUT_ROOT.glob("batch_*"):
        clips_dir = batch_dir / "03_clips"
        if not clips_dir.is_dir():
            continue
        for clip_path in clips_dir.glob("*.mp4"):
            item = _canvas_clip_payload(
                clip_path,
                f"/api/canvas/clips/{batch_dir.name}/{clip_path.name}",
                batch_id=batch_dir.name,
            )
            if item is not None:
                result.append(item)
    return sorted(result, key=lambda item: (item["dish"], item["filename"]))


@router.get("/api/canvas/clips/library/{filename}")
def serve_canvas_library_clip(filename: str) -> FileResponse:
    clip_path = CANVAS_CLIP_ROOT / Path(filename).name
    if clip_path.suffix.lower() != ".mp4" or not clip_path.is_file():
        raise _json_error("视频片段不存在", 404)
    return FileResponse(str(clip_path), media_type="video/mp4")


@router.get("/api/canvas/clips/previews/{filename}")
def serve_canvas_library_preview(filename: str) -> FileResponse:
    preview_path = CANVAS_CLIP_PREVIEW_ROOT / Path(filename).name
    if preview_path.suffix.lower() != ".mp4" or not preview_path.is_file():
        raise _json_error("视频预览不存在", 404)
    return FileResponse(str(preview_path), media_type="video/mp4")


@router.get("/api/canvas/clips/{batch_id}/{filename}")
def serve_canvas_clip(batch_id: str, filename: str) -> FileResponse:
    if not re.fullmatch(r"batch_[A-Za-z0-9_-]+", batch_id):
        raise _json_error("视频批次无效", 400)
    clip_path = OUTPUT_ROOT / batch_id / "03_clips" / Path(filename).name
    if clip_path.suffix.lower() != ".mp4" or not clip_path.is_file():
        raise _json_error("视频片段不存在", 404)
    return FileResponse(str(clip_path), media_type="video/mp4")


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
async def upload_canvas_file(
    draft_id: str,
    kind: str = Form(...),
    dish: str = Form(""),
    category: str = Form(""),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    try:
        metadata = await save_upload(draft_id, file, kind)
    except (ValueError, OSError) as exc:
        raise _json_error(str(exc), 400) from exc
    metadata["url"] = f"/api/canvas/drafts/{draft_id}/files/{metadata['stored_name']}"
    if kind == "image":
        path = uploaded_file(draft_id, metadata["stored_name"])
        if path is not None:
            metadata["analysis"] = analyze_image(path, dish, category or None)
    return metadata


@router.get("/api/canvas/drafts/{draft_id}/files/{stored_name}")
def get_canvas_file(draft_id: str, stored_name: str) -> FileResponse:
    path = uploaded_file(draft_id, stored_name)
    if path is None:
        raise _json_error("文件不存在", 404)
    return FileResponse(str(path))


@router.post("/api/canvas/drafts/{draft_id}/generations")
def start_canvas_generation(draft_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request = payload or {}
    try:
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
        if bool(request.get("include_sound", False)):
            return start_compose(draft_id, workspace_id=request.get("workspace_id"), include_sound=True)
        return start_compose(draft_id, workspace_id=request.get("workspace_id"))
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


def _json_error(message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


def _read_video_duration_seconds(path: str | Path | None) -> float | None:
    if not path or not os.path.exists(str(path)):
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            return None
        return float(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _read_file_timestamp(path: str | Path | None) -> str | None:
    if not path or not os.path.exists(str(path)):
        return None
    try:
        return datetime.fromtimestamp(os.path.getmtime(str(path))).isoformat(timespec="seconds")
    except OSError:
        return None


def _format_generated_at(value: str | None) -> str:
    if not value:
        return "生成时间未知"
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return dt.strftime("%Y年%m月%d日%H:%M:%S生成")


def _guess_dish_from_clip_name(filename: str, dish_names: list[str]) -> str:
    for dish in sorted(dish_names, key=len, reverse=True):
        if dish and dish in filename:
            return dish
    stem = Path(filename).stem
    if stem.startswith("omni_smoke_"):
        parts = stem.split("_")
        if len(parts) >= 6:
            return "_".join(parts[2:-3]) or "未登记视频"
    return stem.split("_")[0] or "未登记视频"


@router.get("/api/config")
def get_config() -> dict[str, Any]:
    if KLING_API_KEY:
        kling_auth_mode = "api_key"
        kling_key_suffix = KLING_API_KEY[-4:]
    elif KLING_ACCESS_KEY and KLING_SECRET_KEY:
        kling_auth_mode = "ak_sk"
        kling_key_suffix = KLING_ACCESS_KEY[-4:]
    else:
        kling_auth_mode = "none"
        kling_key_suffix = ""

    return {
        "kling": bool(KLING_API_KEY or (KLING_ACCESS_KEY and KLING_SECRET_KEY)),
        "kling_base_url": KLING_BASE_URL,
        "kling_model": KLING_MODEL,
        "video_spec": {
            "duration_seconds": VIDEO_DURATION,
            "resolution": VIDEO_RESOLUTION,
            "aspect_ratio": VIDEO_ASPECT,
            "silent": VIDEO_SILENT,
            "supports_last_frame": True,
        },
        "kling_auth_mode": kling_auth_mode,
        "kling_key_suffix": kling_key_suffix,
        "image_library": str(IMAGE_LIBRARY),
        "image_library_exists": IMAGE_LIBRARY.exists(),
    }


@router.get("/api/batches")
def list_batches() -> list[dict[str, Any]]:
    batches = []
    if OUTPUT_ROOT.exists():
        for directory in sorted(OUTPUT_ROOT.iterdir(), reverse=True):
            if not directory.is_dir() or not directory.name.startswith("batch_"):
                continue
            date_str = directory.name.replace("batch_", "")
            state_file = directory / "state.json"
            state = {}
            if state_file.exists():
                with open(state_file, encoding="utf-8") as f:
                    state = json.load(f)
            batches.append({
                "id": directory.name,
                "date": date_str,
                "name": state.get("name", ""),
                "status": state.get("status", "unknown"),
                "dish_count": len(state.get("dishes", [])),
            })
    return batches


@router.post("/api/batch")
def create_batch(payload: dict[str, Any]) -> dict[str, Any]:
    batch_name = payload.get("name", "")
    batch_date = payload.get("date", datetime.now().strftime("%Y%m%d"))
    batch_id = f"batch_{batch_date}"

    if (OUTPUT_ROOT / batch_id).exists():
        suffix = 2
        while (OUTPUT_ROOT / f"{batch_id}_{suffix}").exists():
            suffix += 1
        batch_id = f"{batch_id}_{suffix}"

    state = get_batch_state(batch_id)
    state["name"] = batch_name
    state["date"] = batch_date
    batch_subdirs(OUTPUT_ROOT / batch_id)
    save_state(batch_id)
    logger.info("Batch created batch=%s name=%s", batch_id, batch_name)
    return {"id": batch_id, "state": state}


@router.get("/api/batch/{batch_id}")
def get_batch(batch_id: str) -> dict[str, Any]:
    state = load_state(batch_id)
    if not state:
        raise _json_error("批次不存在", 404)
    return state


@router.post("/api/batch/{batch_id}/dishes")
def update_dishes(batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    state = get_batch_state(batch_id)
    state["dishes"] = payload.get("dishes", [])
    state["status"] = "configured"
    save_state(batch_id)
    logger.info("Dishes updated batch=%s count=%s", batch_id, len(state["dishes"]))
    return state


@router.post("/api/batch/{batch_id}/upload")
async def upload_images(batch_id: str, dish: str = Form(""), tail: str = Form("0"),
                        files: list[UploadFile] = File(...)) -> dict[str, Any]:
    """上传菜品图片。tail=1 时作为尾帧图存入 01_images/tail/（环绕方案使用）。"""
    get_batch_state(batch_id)
    dirs = batch_subdirs(OUTPUT_ROOT / batch_id)
    is_tail = tail == "1"
    target_dir = dirs["images"] / "tail" if is_tail else dirs["images"]
    uploaded = []
    for upload in files:
        ext = Path(upload.filename or "").suffix
        filename = f"{dish}_{uuid.uuid4().hex[:8]}{ext}"
        filepath = target_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(await upload.read())
        uploaded.append(str(filepath))
    logger.info("Images uploaded batch=%s dish=%s tail=%s count=%s", batch_id, dish, is_tail, len(uploaded))
    if is_tail:
        return {"dish": dish, "tail_images": uploaded}
    return {"dish": dish, "images": uploaded}


@router.get("/api/library/dishes")
def list_library_dishes() -> list[dict[str, Any]]:
    dishes = []
    for lib in [IMAGE_LIBRARY] + EXTRA_IMAGE_LIBS:
        if not lib.exists():
            continue
        for sub in lib.iterdir():
            if not sub.is_dir():
                continue
            images = list(sub.glob("*.jpg")) + list(sub.glob("*.jpeg")) + list(sub.glob("*.png")) + list(sub.glob("*.JPG"))
            if images:
                dishes.append({
                    "name": sub.name,
                    "library": str(lib),
                    "image_count": len(images),
                    "sample": str(images[0]),
                })
    return dishes


@router.get("/api/library/preview")
def library_preview(path: str) -> FileResponse:
    file_path = Path(path)
    if file_path.exists():
        return FileResponse(str(file_path))
    raise _json_error("图片不存在", 404)


@router.post("/api/batch/{batch_id}/run/step1")
def api_run_step1(batch_id: str) -> dict[str, Any]:
    return run_step1(batch_id)


@router.post("/api/prompt/assemble")
def api_prompt_assemble(payload: dict[str, Any]) -> dict[str, Any]:
    """槽位 → 提示词实时装配（确定性纯函数，不调 LLM）。

    前端槽位表单每次变更都调这个接口拿实时预览。
    """
    from pipeline.prompt_assembler import L2Item, PromptConfig, assemble_prompt

    try:
        cfg = PromptConfig(
            mode=payload.get("mode", "single_image"),
            camera_move=payload.get("camera_move", "dolly_in"),
            camera_amplitude=payload.get("camera_amplitude", "subtle"),
            elements=payload.get("elements", []),
            l1_subject=payload.get("l1_subject", "none"),
            l1_action_level=payload.get("l1_action_level"),
            l1_action_verb=payload.get("l1_action_verb"),
            l2_dynamics=[
                L2Item(type=item.get("type", ""), target=item.get("target", ""))
                for item in payload.get("l2_dynamics", [])
            ],
            speed_curve=payload.get("speed_curve"),
            seamless_loop=bool(payload.get("seamless_loop", False)),
        )
        result = assemble_prompt(cfg)
        return {
            "blocked": result.blocked,
            "errors": [{"code": e.code, "message": e.message, "field": e.field} for e in result.errors],
            "warnings": [{"code": w.code, "message": w.message, "field": w.field} for w in result.warnings],
            "prompt": result.prompt,
            "negative_prompt": result.negative_prompt,
        }
    except Exception as e:
        return {"blocked": True, "errors": [{"code": "ERR", "message": str(e), "field": ""}], "warnings": [], "prompt": "", "negative_prompt": ""}


@router.post("/api/batch/{batch_id}/run/step2")
def api_run_step2(batch_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return run_step2(batch_id, force=bool((payload or {}).get("force", False)))


@router.get("/api/batch/{batch_id}/prompts")
def get_prompts(batch_id: str) -> list[dict[str, Any]]:
    dirs = batch_subdirs(OUTPUT_ROOT / batch_id)
    prompts_data = load_manifest(dirs, "prompts") or []
    edited_path = dirs["prompts"] / "edited_prompts.json"
    edited = {}
    if edited_path.exists():
        with open(edited_path, encoding="utf-8") as f:
            edited = json.load(f)

    result = []
    for prompt in prompts_data:
        dish = prompt["dish"]
        variant_id = prompt.get("variant_id", "v1")
        key = f"{dish}|{variant_id}"
        merged = edited.get(key, {})
        result.append({
            "dish": dish,
            "variant_id": variant_id,
            "variant_label": prompt.get("variant_label", variant_id),
            "selected": merged.get("selected", prompt.get("selected", False)),
            "video_prompt": merged.get("video_prompt", prompt["video_prompt"]),
            "negative_prompt": merged.get("negative_prompt", prompt.get("negative_prompt", "")),
            "slots": merged.get("slots", prompt.get("slots", {})),
            "warnings": merged.get("warnings", prompt.get("warnings", [])),
            "errors": merged.get("errors", prompt.get("errors", [])),
            "blocked": bool(merged.get("blocked", prompt.get("blocked", False))),
            "subtitle": prompt.get("subtitle", dish),
            "caption": prompt.get("caption", ""),
        })
    return result


@router.post("/api/batch/{batch_id}/prompts")
def save_prompts(batch_id: str, payload: dict[str, Any]) -> dict[str, str]:
    prompts = payload.get("prompts", [])
    dirs = batch_subdirs(OUTPUT_ROOT / batch_id)
    edited = {}
    for prompt in prompts:
        key = f"{prompt['dish']}|{prompt.get('variant_id', 'v1')}"
        edited[key] = {
            "video_prompt": prompt["video_prompt"],
            "negative_prompt": prompt.get("negative_prompt", ""),
            "selected": bool(prompt.get("selected", False)),
            "slots": prompt.get("slots", {}),
            "warnings": prompt.get("warnings", []),
            "errors": prompt.get("errors", []),
            "blocked": bool(prompt.get("blocked", False)),
        }
    with open(dirs["prompts"] / "edited_prompts.json", "w", encoding="utf-8") as f:
        json.dump(edited, f, ensure_ascii=False, indent=2)
    # 首尾帧全局开关：随保存持久化到批次状态
    if "use_tail_frame" in payload:
        state = get_batch_state(batch_id)
        state["use_tail_frame"] = bool(payload["use_tail_frame"])
        save_state(batch_id, state)
    logger.info("Prompts saved batch=%s count=%s", batch_id, len(edited))
    return {"status": "saved"}


@router.post("/api/batch/{batch_id}/run/step3")
def api_run_step3(batch_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return run_step3(batch_id, force=bool((payload or {}).get("force", False)))
    except ValueError as exc:
        raise _json_error(str(exc), 400) from exc


@router.get("/api/batch/{batch_id}/clips")
def get_clips(batch_id: str) -> dict[str, list[dict[str, Any]]]:
    dirs = batch_subdirs(OUTPUT_ROOT / batch_id)
    clips = load_manifest(dirs, "clips") or []
    grouped = {}
    seen_filenames = set()
    for clip in clips:
        if clip.get("status") != "ok":
            continue
        dish = clip["dish"]
        duration = clip.get("duration_seconds")
        if duration is None:
            duration = _read_video_duration_seconds(clip.get("output"))
        if duration is None or abs(float(duration) - float(VIDEO_DURATION)) > 0.35:
            continue
        generated_at = clip.get("generated_at") or _read_file_timestamp(clip.get("output"))
        filename = os.path.basename(clip["output"])
        seen_filenames.add(filename)
        grouped.setdefault(dish, []).append({
            "roll": clip["roll"],
            "variant_id": clip.get("variant_id", ""),
            "variant_label": clip.get("variant_label", ""),
            "filename": filename,
            "path": clip["output"],
            "duration_seconds": duration,
            "generated_at": generated_at,
            "generated_at_label": _format_generated_at(generated_at),
        })

    state = load_state(batch_id) or {}
    dish_names = [dish.get("name", "") for dish in state.get("dishes", []) if isinstance(dish, dict)]
    for clip_path in sorted(dirs["clips"].glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
        if clip_path.name in seen_filenames:
            continue
        duration = _read_video_duration_seconds(clip_path)
        if duration is None or abs(float(duration) - float(VIDEO_DURATION)) > 0.35:
            continue
        generated_at = _read_file_timestamp(clip_path)
        dish = _guess_dish_from_clip_name(clip_path.name, dish_names)
        grouped.setdefault(dish, []).append({
            "roll": 1,
            "variant_id": "orphan",
            "variant_label": "未登记片段",
            "filename": clip_path.name,
            "path": str(clip_path),
            "duration_seconds": duration,
            "generated_at": generated_at,
            "generated_at_label": _format_generated_at(generated_at),
        })
    return grouped


@router.get("/api/batch/{batch_id}/clips/{filename}")
def serve_clip(batch_id: str, filename: str) -> FileResponse:
    clip_path = OUTPUT_ROOT / batch_id / "03_clips" / Path(filename).name
    if not clip_path.exists():
        raise _json_error("视频片段不存在", 404)
    return FileResponse(str(clip_path), media_type="video/mp4")


@router.post("/api/batch/{batch_id}/select")
def select_clips(batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    state = get_batch_state(batch_id)
    state["selected_clips"] = payload.get("selected", {})
    state["status"] = "selected"
    dirs = batch_subdirs(OUTPUT_ROOT / batch_id)
    write_selection_csv(dirs, state["selected_clips"])
    save_state(batch_id)
    logger.info("Clips selected batch=%s count=%s", batch_id, len(state["selected_clips"]))
    return state


@router.get("/api/batch/{batch_id}/captions")
def get_captions(batch_id: str) -> dict[str, dict[str, str]]:
    dirs = batch_subdirs(OUTPUT_ROOT / batch_id)
    prompts = load_manifest(dirs, "prompts") or []
    clips = load_manifest(dirs, "clips") or []
    selected = get_batch_state(batch_id).get("selected_clips", {})
    selected_variants = {
        dish: clip.get("variant_id")
        for dish, filename in selected.items()
        for clip in clips
        if clip.get("status") == "ok" and Path(clip.get("output", "")).name == filename
    }

    captions = {}
    for prompt in prompts:
        dish = prompt["dish"]
        selected_variant = selected_variants.get(dish)
        if dish not in captions or prompt.get("variant_id") == selected_variant:
            captions[dish] = {
                "subtitle": prompt.get("subtitle", dish),
                "caption": prompt.get("caption", ""),
            }
    return captions


@router.post("/api/batch/{batch_id}/captions")
def update_captions(batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    state = get_batch_state(batch_id)
    state["captions"] = payload.get("captions", {})
    save_state(batch_id)
    return state


@router.post("/api/batch/{batch_id}/run/compose")
def api_run_compose(batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return run_compose(batch_id, payload.get("video_config", {}))
    except ValueError as exc:
        raise _json_error(str(exc), 400) from exc


@router.get("/api/batch/{batch_id}/status")
def get_status(batch_id: str) -> dict[str, Any]:
    state = load_state(batch_id)
    if not state:
        raise _json_error("批次不存在", 404)
    return state


@router.get("/api/batch/{batch_id}/final")
def download_final(batch_id: str):
    state = load_state(batch_id) or {}
    final_dir = OUTPUT_ROOT / batch_id / "06_final"
    videos = [v for v in state.get("videos", []) if os.path.exists(v.get("path", ""))]
    if len(videos) == 1:
        video = videos[0]
        return FileResponse(video["path"], filename=video.get("filename", f"{batch_id}_final.mp4"), media_type="video/mp4")
    if len(videos) > 1:
        zip_path = final_dir / f"{batch_id}_final_videos.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for video in videos:
                zf.write(video["path"], arcname=video.get("filename", Path(video["path"]).name))
        return FileResponse(str(zip_path), filename=f"{batch_id}_final_videos.zip", media_type="application/zip")

    final_path = final_dir / "final_video.mp4"
    if final_path.exists():
        return FileResponse(str(final_path), filename=f"{batch_id}_final.mp4", media_type="video/mp4")
    raise _json_error("视频未生成", 404)


@router.get("/api/batch/{batch_id}/final/{filename}")
def serve_final_video(batch_id: str, filename: str) -> FileResponse:
    final_path = OUTPUT_ROOT / batch_id / "06_final" / Path(filename).name
    if not final_path.exists():
        raise _json_error("视频不存在", 404)
    return FileResponse(str(final_path), media_type="video/mp4")
