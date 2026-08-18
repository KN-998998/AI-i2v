# -*- coding: utf-8 -*-
"""API routers for the FastAPI web workbench."""
import json
import os
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from pipeline.config import (
    DEEPSEEK_API_KEY,
    EXTRA_IMAGE_LIBS,
    IMAGE_LIBRARY,
    KLING_ACCESS_KEY,
    KLING_API_KEY,
    KLING_BASE_URL,
    KLING_MODEL,
    KLING_SECRET_KEY,
    OUTPUT_ROOT,
    batch_subdirs,
)
from web.core.logging import get_logger
from web.services.pipeline_tasks import run_compose, run_step1, run_step2, run_step3
from web.services.planning import write_selection_csv
from web.services.state import get_batch_state, load_manifest, load_state, save_state

router = APIRouter()
logger = get_logger(__name__)


def _json_error(message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


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
        "deepseek": bool(DEEPSEEK_API_KEY),
        "kling": bool(KLING_API_KEY or (KLING_ACCESS_KEY and KLING_SECRET_KEY)),
        "kling_base_url": KLING_BASE_URL,
        "kling_model": KLING_MODEL,
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
    for clip in clips:
        if clip.get("status") != "ok":
            continue
        dish = clip["dish"]
        grouped.setdefault(dish, []).append({
            "roll": clip["roll"],
            "variant_id": clip.get("variant_id", ""),
            "variant_label": clip.get("variant_label", ""),
            "filename": os.path.basename(clip["output"]),
            "path": clip["output"],
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
