# -*- coding: utf-8 -*-
"""Asynchronous Kling generation jobs for canvas generator nodes."""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.config import CANVAS_CLIP_ROOT, KLING_ACCESS_KEY, KLING_API_KEY, KLING_SECRET_KEY, VIDEO_DURATION
from web.services.canvas_state import draft_directory, load_draft, uploaded_file
from web.services.canvas_quality import analyze_video, infer_category

_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_JOB_LOCK = threading.RLock()
_MANIFEST_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _job_path(draft_id: str, job_id: str) -> Path:
    return draft_directory(draft_id) / f"generate-{job_id}.json"


def _save_job(draft_id: str, job: dict[str, Any]) -> None:
    path = _job_path(draft_id, job["job_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(job, stream, ensure_ascii=False, indent=2)
    temporary.replace(path)


def get_generation_job(draft_id: str, job_id: str) -> dict[str, Any] | None:
    if not _JOB_ID_RE.fullmatch(job_id or ""):
        return None
    path = _job_path(draft_id, job_id)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError):
        return None


def _update_job(draft_id: str, job: dict[str, Any], **changes: Any) -> None:
    job.update(changes, updated_at=_now())
    with _JOB_LOCK:
        _save_job(draft_id, job)


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", str(value or "").strip())
    return cleaned.strip("_-") or "canvas_clip"


def _uploaded_image(draft_id: str, url: str | None) -> Path | None:
    if not url:
        return None
    return uploaded_file(draft_id, Path(str(url).split("?", 1)[0]).name)


def _prompt_from_node(data: dict[str, Any]) -> tuple[str, str, bool]:
    from pipeline.prompt_assembler import L2Item, PromptConfig, assemble_prompt

    raw = data.get("promptConfig") if isinstance(data.get("promptConfig"), dict) else {}
    dynamics = [
        L2Item(type=str(item.get("type", "")), target=str(item.get("target", "")))
        for item in raw.get("l2_dynamics", [])
        if isinstance(item, dict)
    ]
    config = PromptConfig(
        mode=str(raw.get("mode", "single_image")),
        camera_move=str(raw.get("camera_move", "dolly_in")),
        camera_amplitude=str(raw.get("camera_amplitude", "subtle")),
        elements=list(raw.get("elements") or []),
        l1_subject=str(raw.get("l1_subject", "dish_hot")),
        l1_action_level=raw.get("l1_action_level"),
        l1_action_verb=raw.get("l1_action_verb"),
        l2_dynamics=dynamics,
        speed_curve=raw.get("speed_curve"),
        seamless_loop=bool(raw.get("seamless_loop", False)),
    )
    result = assemble_prompt(config)
    if result.blocked:
        detail = "；".join(error.message for error in result.errors)
        raise ValueError(f"提示词配置阻断生成：{detail}")
    return result.prompt, result.negative_prompt, config.mode == "keyframes"


def _append_manifest(record: dict[str, Any]) -> None:
    CANVAS_CLIP_ROOT.mkdir(parents=True, exist_ok=True)
    path = CANVAS_CLIP_ROOT / "manifest.json"
    with _MANIFEST_LOCK:
        records: list[dict[str, Any]] = []
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    records = [item for item in payload if isinstance(item, dict) and item.get("filename") != record.get("filename")]
            except (OSError, json.JSONDecodeError):
                records = []
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps([*records, record], ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)


def _build_clip(job: dict[str, Any], path: Path, dish: str, category: str) -> dict[str, Any]:
    analysis = analyze_video(path, dish, category)
    duration = float(analysis.get("durationSeconds") or VIDEO_DURATION)
    filename = path.name
    return {
        "id": f"clip_canvas_{filename}",
        "filename": filename,
        "dish": dish,
        "label": "生成片段",
        "tone": "#355e62",
        "durationSeconds": round(duration, 2),
        "timelineDuration": min(round(duration, 2), 2.5),
        "sourceDurationSeconds": round(duration, 2),
        "sourceStartSeconds": min(0.5, max(0.0, duration - 0.1)),
        "sourceEndSeconds": round(duration, 2),
        "status": "generated",
        "sourcePath": str(path.resolve()),
        "sourceUrl": f"/api/canvas/clips/library/{filename}",
        "dishCategory": category,
        "generatorNodeId": job["node_id"],
        "generationJobId": job["job_id"],
        "qualityScore": analysis.get("qualityScore", 50),
        "qualityLabel": analysis.get("qualityLabel", "warning"),
        "qualityWarnings": analysis.get("qualityWarnings", []),
        "analysisMode": analysis.get("analysisMode", "technical_rules"),
    }


def start_generation(draft_id: str, node_id: str, force: bool = False) -> dict[str, Any]:
    draft = load_draft(draft_id)
    if draft is None:
        raise ValueError("画布草稿不存在，请先保存草稿")
    node = next((item for item in draft.get("nodes", []) if item.get("id") == node_id), None)
    if not node or node.get("data", {}).get("kind") != "generator":
        raise ValueError("生成节点不存在")
    if not ((KLING_ACCESS_KEY and KLING_SECRET_KEY) or KLING_API_KEY):
        raise ValueError("未配置 Kling 鉴权信息")

    input_data = next((item.get("data", {}) for item in draft.get("nodes", []) if item.get("data", {}).get("kind") == "input"), {})
    prompt_data = next((item.get("data", {}) for item in draft.get("nodes", []) if item.get("data", {}).get("kind") == "prompt"), {})
    image_path = _uploaded_image(draft_id, input_data.get("imagePreview"))
    if image_path is None or not image_path.is_file():
        raise ValueError("请先在素材与菜品节点上传首帧图片")
    prompt, negative_prompt, keyframe_mode = _prompt_from_node(prompt_data)
    tail_path = _uploaded_image(draft_id, prompt_data.get("promptEndImagePreview"))
    if keyframe_mode and (tail_path is None or not tail_path.is_file()):
        raise ValueError("首尾帧模式需要先上传尾帧图片")

    duration_text = str(node.get("data", {}).get("duration") or f"{VIDEO_DURATION}s")
    duration_match = re.search(r"(\d+)", duration_text)
    duration = int(duration_match.group(1)) if duration_match else VIDEO_DURATION
    if duration < 3 or duration > 15:
        raise ValueError("Kling 生成时长必须在 3-15 秒之间")

    job_id = uuid.uuid4().hex
    job = {
        "job_id": job_id,
        "draft_id": draft_id,
        "node_id": node_id,
        "status": "queued",
        "created_at": _now(),
        "updated_at": _now(),
        "task_id": None,
        "clip": None,
        "error": None,
        "force": force,
    }
    with _JOB_LOCK:
        _save_job(draft_id, job)

    def worker() -> None:
        try:
            from pipeline.step3_gen_videos import create_task, download_video, image_to_base64, session_with_retry, wait_for_video

            _update_job(draft_id, job, status="running", stage="准备图片和提示词")
            session = session_with_retry()
            image_base64 = image_to_base64(str(image_path))
            tail_base64 = image_to_base64(str(tail_path)) if tail_path else None
            task_id = create_task(session, image_base64, prompt, negative_prompt, duration=duration, image_tail_base64=tail_base64)
            _update_job(draft_id, job, task_id=task_id, stage="Kling 生成中")
            video_url, info = wait_for_video(session, task_id)
            if not video_url:
                raise RuntimeError(str(info.get("error") or "Kling 生成失败"))

            input_dish = str(input_data.get("dishName") or "待配置菜品")
            category = infer_category(input_dish, input_data.get("dishCategory"))
            filename = f"{_safe_name(input_dish)}_{_safe_name(node_id)}_{job_id[:8]}_{duration}s.mp4"
            output_path = CANVAS_CLIP_ROOT / filename
            download_video(session, video_url, str(output_path))
            clip = _build_clip(job, output_path, input_dish, category)
            _append_manifest({**clip, "videoTaskId": task_id, "prompt": prompt})
            _update_job(draft_id, job, status="done", stage="已下载到本地片段库", clip=clip)
        except Exception as exc:
            _update_job(draft_id, job, status="error", stage="生成失败", error=str(exc))

    threading.Thread(target=worker, name=f"canvas-generate-{job_id}", daemon=True).start()
    return job
