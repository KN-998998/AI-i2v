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
from web.services import canvas_state
from web.services.canvas_state import draft_directory, load_draft, save_draft, uploaded_file
from web.services.canvas_quality import analyze_video, infer_category

_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_JOB_LOCK = threading.RLock()
_MANIFEST_LOCK = threading.RLock()
_RECOVERY_LOCK = threading.RLock()
_RECOVERED_JOB_KEYS: set[str] = set()


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
        with _JOB_LOCK:
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


def _upstream_data(draft: dict[str, Any], start_id: str, kind: str, allow_legacy_fallback: bool = False) -> dict[str, Any]:
    """Resolve one connected upstream node; normal generation never guesses a branch."""
    pending = [start_id]
    seen: set[str] = set()
    nodes = {str(item.get("id")): item for item in draft.get("nodes", [])}
    matches: list[dict[str, Any]] = []
    while pending:
        target = pending.pop(0)
        if target in seen:
            continue
        seen.add(target)
        for edge in draft.get("edges", []):
            if edge.get("target") != target:
                continue
            source_id = str(edge.get("source"))
            source = nodes.get(source_id)
            if source and source.get("data", {}).get("kind") == kind:
                matches.append(source.get("data", {}))
                continue
            pending.append(source_id)
    if len(matches) > 1:
        raise ValueError(f"生成节点 {start_id} 的上游存在多个 {kind} 节点，请保留唯一连接")
    if matches:
        return matches[0]
    if allow_legacy_fallback:
        return next((item.get("data", {}) for item in draft.get("nodes", []) if item.get("data", {}).get("kind") == kind), {})
    raise ValueError(f"生成节点 {start_id} 没有连接到 {kind} 节点，请先连接完整流程")


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
        shot_size=str(raw.get("shot_size", "close_up")),
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


def _job_context(draft_id: str, job: dict[str, Any]) -> tuple[str, str, int, str]:
    """Recover metadata from the job first, then the current connected graph."""
    dish = str(job.get("dish") or "").strip()
    category = str(job.get("dish_category") or "").strip()
    prompt = str(job.get("prompt") or "")
    duration_match = re.search(r"(\d+)", str(job.get("duration") or ""))
    duration = int(duration_match.group(1)) if duration_match else VIDEO_DURATION

    if not dish or not category:
        draft = load_draft(draft_id)
        if draft is not None:
            related_clip = next(
                (
                    item
                    for item in [*(draft.get("candidateClips") or []), *(draft.get("timeline") or [])]
                    if isinstance(item, dict)
                    and (
                        item.get("generationJobId") == job.get("job_id")
                        or item.get("generatorNodeId") == job.get("node_id")
                    )
                ),
                {},
            )
            dish = dish or str(related_clip.get("dish") or "").strip()
            category = category or str(related_clip.get("dishCategory") or "").strip()
            try:
                input_data = _upstream_data(draft, str(job.get("node_id") or ""), "input")
            except ValueError:
                input_data = {}
            dish = dish or str(input_data.get("dishName") or "").strip()
            category = category or infer_category(dish, input_data.get("dishCategory"))

    if not prompt:
        draft = load_draft(draft_id)
        if draft is not None:
            try:
                prompt_data = _upstream_data(draft, str(job.get("node_id") or ""), "prompt")
            except ValueError:
                prompt_data = {}
            if prompt_data:
                prompt, _negative_prompt, _keyframe_mode = _prompt_from_node(prompt_data)

    if not dish:
        raise ValueError("恢复 Kling 任务缺少菜品信息，无法写入片段库")
    if not category:
        category = infer_category(dish, None)
    if duration < 3 or duration > 15:
        duration = VIDEO_DURATION
    return dish, category, duration, prompt


def _job_output_path(job: dict[str, Any], dish: str, duration: int) -> Path:
    filename = str(job.get("output_filename") or "").strip()
    if not filename:
        filename = f"{_safe_name(dish)}_{_safe_name(str(job.get('node_id') or 'generator'))}_{str(job['job_id'])[:8]}_{duration}s.mp4"
        job["output_filename"] = filename
    if Path(filename).name != filename or Path(filename).suffix.lower() != ".mp4":
        raise ValueError("恢复任务的输出文件名无效")
    return CANVAS_CLIP_ROOT / filename


def _complete_generation_job(
    draft_id: str,
    job: dict[str, Any],
    video_url: str | None,
    session: Any,
    dish: str,
    category: str,
    duration: int,
    prompt: str,
) -> None:
    output_path = _job_output_path(job, dish, duration)
    if not output_path.is_file():
        if not video_url:
            raise RuntimeError("Kling 任务完成但未返回视频地址")
        from pipeline.kling import download_video

        download_video(session, video_url, str(output_path))
    clip = _build_clip(job, output_path, dish, category)
    _append_manifest({**clip, "videoTaskId": job.get("task_id"), "prompt": prompt})
    _update_job(draft_id, job, status="done", stage="已下载到本地片段库", clip=clip, output_filename=output_path.name)
    _persist_generated_clip(draft_id, str(job.get("node_id") or ""), clip)


def _run_generation_job(draft_id: str, job: dict[str, Any]) -> None:
    """Poll one persisted Kling task and finish it idempotently after restart."""
    try:
        from pipeline.kling import session_with_retry, wait_for_video

        dish, category, duration, prompt = _job_context(draft_id, job)
        _update_job(draft_id, job, status="running", stage="恢复 Kling 任务轮询", dish=dish, dish_category=category, duration=duration, prompt=prompt)
        output_path = _job_output_path(job, dish, duration)
        session = session_with_retry()
        if output_path.is_file():
            video_url = None
        else:
            video_url, info = wait_for_video(session, str(job.get("task_id") or ""))
            if not video_url:
                raise RuntimeError(str(info.get("error") or "Kling 生成失败"))
        _complete_generation_job(draft_id, job, video_url, session, dish, category, duration, prompt)
    except Exception as exc:
        _update_job(draft_id, job, status="error", stage="恢复任务失败", error=str(exc))
        _persist_generator_status(draft_id, str(job.get("node_id") or ""), "生成失败")


def _iter_generation_jobs() -> list[tuple[str, dict[str, Any]]]:
    root = canvas_state.CANVAS_DRAFT_ROOT
    if not root.is_dir():
        return []
    jobs: list[tuple[str, dict[str, Any]]] = []
    for path in root.glob("*/generate-*.json"):
        draft_id = path.parent.name
        job_id = path.stem.removeprefix("generate-")
        if not _JOB_ID_RE.fullmatch(job_id):
            continue
        try:
            with _JOB_LOCK:
                with path.open("r", encoding="utf-8") as stream:
                    job = json.load(stream)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(job, dict):
            jobs.append((draft_id, job))
    return jobs


def recover_generation_jobs() -> int:
    """Schedule unfinished Kling tasks once during each backend process lifetime."""
    scheduled = 0
    for draft_id, job in _iter_generation_jobs():
        if job.get("status") not in {"queued", "running"}:
            continue
        job_id = str(job.get("job_id") or "")
        key = f"{draft_id}:{job_id}"
        with _RECOVERY_LOCK:
            if key in _RECOVERED_JOB_KEYS:
                continue
            _RECOVERED_JOB_KEYS.add(key)
        if not str(job.get("task_id") or "").strip():
            _update_job(draft_id, job, status="error", stage="服务重启后无法恢复", error="任务尚未保存 Kling task_id，无法安全恢复，请重新生成")
            _persist_generator_status(draft_id, str(job.get("node_id") or ""), "生成失败")
            continue
        threading.Thread(target=_run_generation_job, args=(draft_id, job), name=f"canvas-recover-{job_id}", daemon=True).start()
        scheduled += 1
    return scheduled


def _persist_generator_status(draft_id: str, node_id: str, status: str) -> None:
    """Keep the persisted canvas node in sync when the browser is no longer open."""
    draft = load_draft(draft_id)
    if draft is None:
        return
    changed = False
    for node in draft.get("nodes", []):
        if node.get("id") != node_id or node.get("data", {}).get("kind") != "generator":
            continue
        if node["data"].get("status") != status:
            node["data"]["status"] = status
            changed = True
        break
    if changed:
        save_draft(draft_id, draft)


def _persist_generated_clip(draft_id: str, node_id: str, clip: dict[str, Any]) -> None:
    """Replace the node's pending clip in the draft with the downloaded MP4."""
    draft = load_draft(draft_id)
    if draft is None:
        return

    candidates = list(draft.get("candidateClips") or draft.get("timeline") or [])
    existing = next((item for item in candidates if item.get("generatorNodeId") == node_id), None)
    persisted_clip = {**clip, "id": existing.get("id", clip["id"]) if existing else clip["id"]}

    if existing is None:
        candidates.append(persisted_clip)
    else:
        candidates = [persisted_clip if item.get("generatorNodeId") == node_id else item for item in candidates]

    def replace_linked(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            persisted_clip if item.get("generatorNodeId") == node_id else item
            for item in items
        ]

    draft["candidateClips"] = candidates
    draft["timeline"] = replace_linked(list(draft.get("timeline") or []))
    draft["composeWorkspaces"] = [
        {**workspace, "clips": replace_linked(list(workspace.get("clips") or []))}
        for workspace in draft.get("composeWorkspaces") or []
    ]
    for node in draft.get("nodes", []):
        if node.get("id") == node_id and node.get("data", {}).get("kind") == "generator":
            node["data"]["status"] = "已生成"
            break
    save_draft(draft_id, draft)


def start_generation(draft_id: str, node_id: str, force: bool = False) -> dict[str, Any]:
    draft = load_draft(draft_id)
    if draft is None:
        raise ValueError("画布草稿不存在，请先保存草稿")
    node = next((item for item in draft.get("nodes", []) if item.get("id") == node_id), None)
    if not node or node.get("data", {}).get("kind") != "generator":
        raise ValueError("生成节点不存在")
    if not ((KLING_ACCESS_KEY and KLING_SECRET_KEY) or KLING_API_KEY):
        raise ValueError("未配置 Kling 鉴权信息")

    input_data = _upstream_data(draft, node_id, "input")
    processing_data = _upstream_data(draft, node_id, "image_process", allow_legacy_fallback=False)
    prompt_data = _upstream_data(draft, node_id, "prompt")
    image_path = _uploaded_image(draft_id, processing_data.get("processedImagePreview"))
    if image_path is None:
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

    input_dish = str(input_data.get("dishName") or "待配置菜品")
    category = infer_category(input_dish, input_data.get("dishCategory"))

    job_id = uuid.uuid4().hex
    output_filename = f"{_safe_name(input_dish)}_{_safe_name(node_id)}_{job_id[:8]}_{duration}s.mp4"
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
        "dish": input_dish,
        "dish_category": category,
        "duration": duration,
        "prompt": prompt,
        "output_filename": output_filename,
    }
    with _JOB_LOCK:
        _save_job(draft_id, job)
        _persist_generator_status(draft_id, node_id, "生成中")

    def worker() -> None:
        try:
            from pipeline.kling import create_task, download_video, image_to_base64, session_with_retry, wait_for_video

            _update_job(draft_id, job, status="running", stage="准备图片和提示词")
            session = session_with_retry()
            image_base64 = image_to_base64(str(image_path))
            tail_base64 = image_to_base64(str(tail_path)) if tail_path else None
            task_id = create_task(session, image_base64, prompt, negative_prompt, duration=duration, image_tail_base64=tail_base64)
            _update_job(draft_id, job, task_id=task_id, stage="Kling 生成中")
            video_url, info = wait_for_video(session, task_id)
            if not video_url:
                raise RuntimeError(str(info.get("error") or "Kling 生成失败"))
            _complete_generation_job(draft_id, job, video_url, session, input_dish, category, duration, prompt)
        except Exception as exc:
            _update_job(draft_id, job, status="error", stage="生成失败", error=str(exc))
            _persist_generator_status(draft_id, node_id, "生成失败")

    threading.Thread(target=worker, name=f"canvas-generate-{job_id}", daemon=True).start()
    return job
