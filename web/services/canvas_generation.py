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
from pipeline.prompt_presets import effective_prompt_config
from web.services import canvas_state
from web.services.canvas_state import draft_directory, load_draft, save_draft, uploaded_file
from web.services.canvas_quality import analyze_video, infer_category
from web.services.task_contract import is_recoverable, retry_delay_seconds, retry_plan, task_metadata, update_task

_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_JOB_LOCK = threading.RLock()
_MANIFEST_LOCK = threading.RLock()
_RECOVERY_LOCK = threading.RLock()
_RECOVERED_JOB_KEYS: set[str] = set()
_VISUAL_SUBJECT_TYPES = {"菜品主体", "手部", "厨师上半身", "手部+厨师上半身"}


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
    status = changes.pop("status", None)
    stage = changes.pop("stage", None)
    if status is None and changes.get("task_id"):
        status = "polling"
    if status == "running" and job.get("task_id"):
        status = "polling"
    job.setdefault("task_type", "kling_generation")
    update_task(job, status=status, stage=stage, **changes)
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


def _prompt_data_for_asset(prompt_data: dict[str, Any], input_data: dict[str, Any]) -> dict[str, Any]:
    """按这道菜自己的冷热和画面主体推导配置，不照搬提示词节点里存着的那一份。

    分步流程和批量生产都从这里出指令，所以两条路径拿到的是同一套规则。原来这里只是把
    food_type 改成这道菜的，主运动还留着模板里的热菜写法——冷的玉子寿司于是拿到了
    「仅表面油光随镜头角度缓慢流动」。补人物那段逻辑搬进了 prompt_presets 的自定义模式。
    """
    visual = str(input_data.get("visualSubjectType") or "菜品主体")
    if visual not in _VISUAL_SUBJECT_TYPES:
        raise ValueError("素材画面主体类型无效，请重新选择")
    return {**prompt_data, "promptConfig": effective_prompt_config(prompt_data, input_data), "visualSubjectType": visual}


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
        food_type=str(raw.get("food_type") or data.get("foodType") or ""),
        visual_subject_type=str(raw.get("visual_subject_type") or data.get("visualSubjectType") or "菜品主体"),
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


def _manifest_records() -> list[dict[str, Any]]:
    path = CANVAS_CLIP_ROOT / "manifest.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _next_clip_version(asset_id: str) -> int:
    versions = [
        int(item.get("clipVersion"))
        for item in _manifest_records()
        if item.get("assetId") == asset_id and str(item.get("clipVersion", "")).isdigit()
    ]
    return max(versions, default=0) + 1


def _build_clip(job: dict[str, Any], path: Path, dish: str, category: str) -> dict[str, Any]:
    # 深度检查（逐帧统计 + freezedetect）要两三秒，但生成本身要一分多钟，值得当场把
    # 「整段不动 / 闪烁 / 边缘长出新东西」判出来，免得拖到第二天人工审片才发现。
    analysis = analyze_video(path, dish, category, True)
    duration = float(analysis.get("durationSeconds") or VIDEO_DURATION)
    # 默认只用逐帧分析挑出来的那段「动得最多的 1.8 秒」，参考片的单镜头中位就是 1.53 秒，
    # 原来固定截 2.5 秒明显更拖。拿不到窗口（浅分析、cv2 读不出帧）时保持老行为，
    # 不凭空编一个区间出来。人在第 5 步仍然可以手动改。
    window_start = analysis.get("bestWindowStart")
    window_end = analysis.get("bestWindowEnd")
    if window_start is None or window_end is None:
        start_seconds = min(0.5, max(0.0, duration - 0.1))
        end_seconds = round(duration, 2)
        timeline_duration = min(round(duration, 2), 2.5)
    else:
        start_seconds = round(float(window_start), 2)
        end_seconds = round(float(window_end), 2)
        timeline_duration = round(end_seconds - start_seconds, 2)
    filename = path.name
    asset_id = str(job.get("asset_id") or f"asset_{job.get('node_id', 'generator')}")
    clip_version = int(job.get("clip_version") or _next_clip_version(asset_id))
    return {
        "id": f"clip_canvas_{job.get('job_id') or filename}",
        "clipId": f"clip_canvas_{job.get('job_id') or filename}",
        "assetId": asset_id,
        # 哪份草稿生成的：前端靠它把别的草稿的片段挡在候选池外面（每份草稿都有一个
        # 叫 "clips" 的生成节点，光看节点 id 会认错人）。
        "draftId": job.get("draft_id"),
        "clipVersion": clip_version,
        "isSelected": True,
        "filename": filename,
        "dish": dish,
        "label": "生成片段",
        "tone": "#355e62",
        "durationSeconds": round(duration, 2),
        "timelineDuration": timeline_duration,
        "sourceDurationSeconds": round(duration, 2),
        "sourceStartSeconds": start_seconds,
        "sourceEndSeconds": end_seconds,
        "status": "generated",
        "sourcePath": str(path.resolve()),
        "sourceUrl": f"/api/canvas/clips/library/{filename}",
        "dishCategory": category,
        "foodType": "混合/多温" if category == "套餐" else str(job.get("food_type") or "") or None,
        "visualSubjectType": str(job.get("visual_subject_type") or "菜品主体"),
        "generatorNodeId": job["node_id"],
        "generationJobId": job["job_id"],
        "qualityScore": analysis.get("qualityScore", 50),
        "qualityLabel": analysis.get("qualityLabel", "warning"),
        "qualityWarnings": analysis.get("qualityWarnings", []),
        "analysisMode": analysis.get("analysisMode", "technical_rules"),
        "redoRecommended": bool(analysis.get("redoRecommended")),
        "redoReasons": analysis.get("redoReasons", []),
    }


def _job_context(draft_id: str, job: dict[str, Any]) -> tuple[str, str, str, str, int, str]:
    """Recover metadata from the job first, then the current connected graph."""
    dish = str(job.get("dish") or "").strip()
    category = str(job.get("dish_category") or "").strip()
    food_type = str(job.get("food_type") or "").strip()
    visual_subject_type = str(job.get("visual_subject_type") or "").strip()
    prompt = str(job.get("prompt") or "")
    duration_match = re.search(r"(\d+)", str(job.get("duration") or ""))
    duration = int(duration_match.group(1)) if duration_match else VIDEO_DURATION
    input_data: dict[str, Any] = {}

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
            food_type = food_type or str(related_clip.get("foodType") or "").strip()
            visual_subject_type = visual_subject_type or str(related_clip.get("visualSubjectType") or "").strip()
            try:
                input_data = _upstream_data(draft, str(job.get("node_id") or ""), "input")
            except ValueError:
                input_data = {}
            dish = dish or str(input_data.get("dishName") or "").strip()
            category = category or infer_category(dish, input_data.get("dishCategory"))

    if not input_data:
        draft = load_draft(draft_id)
        if draft is not None:
            try:
                input_data = _upstream_data(draft, str(job.get("node_id") or ""), "input")
            except ValueError:
                input_data = {}

    if not visual_subject_type:
        visual_subject_type = str(input_data.get("visualSubjectType") or "").strip()

    if not prompt:
        draft = load_draft(draft_id)
        if draft is not None:
            try:
                prompt_data = _upstream_data(draft, str(job.get("node_id") or ""), "prompt")
            except ValueError:
                prompt_data = {}
            if prompt_data:
                prompt, _negative_prompt, _keyframe_mode = _prompt_from_node(_prompt_data_for_asset(prompt_data, input_data))

    if not food_type:
        draft = load_draft(draft_id)
        if draft is not None:
            try:
                input_data = _upstream_data(draft, str(job.get("node_id") or ""), "input")
            except ValueError:
                input_data = {}
            food_type = str(input_data.get("foodType") or "").strip()
            visual_subject_type = str(input_data.get("visualSubjectType") or "").strip()

    if not visual_subject_type:
        draft = load_draft(draft_id)
        if draft is not None:
            try:
                input_data = input_data or _upstream_data(draft, str(job.get("node_id") or ""), "input")
            except ValueError:
                input_data = input_data or {}
            visual_subject_type = str(input_data.get("visualSubjectType") or "").strip()

    if not dish:
        raise ValueError("恢复 Kling 任务缺少菜品信息，无法写入片段库")
    if not category:
        category = infer_category(dish, None)
    if category == "套餐":
        food_type = "混合/多温"
    elif food_type not in {"冷食", "热食"}:
        food_type = ""
    if visual_subject_type not in _VISUAL_SUBJECT_TYPES:
        visual_subject_type = "菜品主体"
    if duration < 3 or duration > 15:
        duration = VIDEO_DURATION
    return dish, category, food_type, visual_subject_type, duration, prompt


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

        _update_job(draft_id, job, status="downloading", stage="下载 Kling 视频到本地片段库")
        download_video(session, video_url, str(output_path))
    _update_job(draft_id, job, status="analyzing", stage="分析视频质量并写入片段库")
    clip = _build_clip(job, output_path, dish, category)
    _append_manifest({**clip, "videoTaskId": job.get("task_id"), "prompt": prompt})
    _update_job(draft_id, job, status="done", stage="已下载到本地片段库", clip=clip, output_filename=output_path.name)
    _persist_generated_clip(draft_id, str(job.get("node_id") or ""), clip)


def _retry_download_or_analysis(
    draft_id: str,
    job: dict[str, Any],
    video_url: str | None,
    session: Any,
    dish: str,
    category: str,
    duration: int,
    prompt: str,
) -> bool:
    plan = retry_plan(job)
    if plan is None:
        return False
    update_task(job, status="retrying", stage=f"下载或分析失败，{plan['delay_seconds']} 秒后第 {plan['retry_count']} 次重试", retry_count=plan["retry_count"], next_retry_at=plan["next_retry_at"])
    _save_job(draft_id, job)
    threading.Timer(
        plan["delay_seconds"],
        _run_generation_postprocess,
        args=(draft_id, job, video_url, session, dish, category, duration, prompt),
    ).start()
    return True


def _run_generation_postprocess(
    draft_id: str,
    job: dict[str, Any],
    video_url: str | None,
    session: Any,
    dish: str,
    category: str,
    duration: int,
    prompt: str,
) -> None:
    try:
        _complete_generation_job(draft_id, job, video_url, session, dish, category, duration, prompt)
    except Exception as exc:
        if not _retry_download_or_analysis(draft_id, job, video_url, session, dish, category, duration, prompt):
            _update_job(draft_id, job, status="error", stage="下载或分析失败", error=str(exc))
            _persist_generator_status(draft_id, str(job.get("node_id") or ""), "生成失败")


def _schedule_generation_postprocess(
    draft_id: str,
    job: dict[str, Any],
    video_url: str | None,
    session: Any,
    dish: str,
    category: str,
    duration: int,
    prompt: str,
) -> None:
    delay = retry_delay_seconds(job)
    if delay <= 0:
        _run_generation_postprocess(draft_id, job, video_url, session, dish, category, duration, prompt)
        return
    threading.Timer(
        delay,
        _run_generation_postprocess,
        args=(draft_id, job, video_url, session, dish, category, duration, prompt),
    ).start()


def _run_generation_job(draft_id: str, job: dict[str, Any]) -> None:
    """Poll one persisted Kling task and finish it idempotently after restart."""
    try:
        from pipeline.kling import session_with_retry, wait_for_video

        dish, category, food_type, visual_subject_type, duration, prompt = _job_context(draft_id, job)
        _update_job(draft_id, job, status="running", stage="恢复 Kling 任务轮询", dish=dish, dish_category=category, food_type=food_type, visual_subject_type=visual_subject_type, duration=duration, prompt=prompt)
        output_path = _job_output_path(job, dish, duration)
        session = session_with_retry()
        if output_path.is_file():
            video_url = None
        else:
            video_url, info = wait_for_video(session, str(job.get("task_id") or ""))
            if not video_url:
                raise RuntimeError(str(info.get("error") or "Kling 生成失败"))
        _schedule_generation_postprocess(draft_id, job, video_url, session, dish, category, duration, prompt)
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
        if not is_recoverable(job.get("status")):
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
        delay = retry_delay_seconds(job) if job.get("status") == "retrying" else 0
        if delay > 0:
            threading.Timer(
                delay,
                _run_generation_job,
                args=(draft_id, job),
            ).start()
        else:
            threading.Thread(target=_run_generation_job, args=(draft_id, job), name=f"canvas-recover-{job_id}", daemon=True).start()
        scheduled += 1
    return scheduled


def _persist_generator_status(draft_id: str, node_id: str, status: str, generation_job_id: str | None = None) -> None:
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
        if generation_job_id is not None and node["data"].get("generationJobId") != generation_job_id:
            node["data"]["generationJobId"] = generation_job_id
            changed = True
        elif status in {"已生成", "生成失败"} and node["data"].get("generationJobId") is not None:
            node["data"].pop("generationJobId", None)
            changed = True
        break
    if changed:
        save_draft(draft_id, draft)


def _persist_generated_clip(draft_id: str, node_id: str, clip: dict[str, Any]) -> None:
    """Persist a generated version and discard every superseded pending placeholder."""
    draft = load_draft(draft_id)
    if draft is None:
        return

    candidates = list(draft.get("candidateClips") or draft.get("timeline") or [])
    linked = [item for item in candidates if item.get("generatorNodeId") == node_id]
    pending_placeholders = [
        item
        for item in linked
        if item.get("status") == "pending" and not item.get("sourcePath")
    ]
    existing_result = next(
        (
            item
            for item in linked
            if item.get("sourcePath")
            and (
                (
                    bool(clip.get("generationJobId"))
                    and item.get("generationJobId") == clip.get("generationJobId")
                )
                or (
                    bool(clip.get("filename"))
                    and item.get("filename") == clip.get("filename")
                )
            )
        ),
        None,
    )
    persisted_clip = {
        **clip,
        "id": (pending_placeholders[0].get("id") if pending_placeholders else None)
        or (existing_result.get("id") if existing_result else None)
        or clip["id"],
        "isSelected": True,
    }
    pending_ids = {str(item.get("id") or "") for item in pending_placeholders}
    candidates = [
        {**item, "isSelected": False}
        if item.get("generatorNodeId") == node_id else item
        for item in candidates
        if str(item.get("id") or "") not in pending_ids
        and item is not existing_result
    ]
    candidates.append(persisted_clip)

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
            node["data"]["selectedClipId"] = persisted_clip["id"]
            node["data"]["assetId"] = persisted_clip.get("assetId")
            node["data"].pop("generationJobId", None)
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
    if image_path is None or not image_path.is_file():
        raise ValueError("请先完成该菜品的图片处理")
    input_food_type = str(input_data.get("foodType") or "").strip()
    visual_subject_type = str(input_data.get("visualSubjectType") or "菜品主体")
    prompt, negative_prompt, keyframe_mode = _prompt_from_node(_prompt_data_for_asset(prompt_data, input_data))
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
    food_type = "混合/多温" if category == "套餐" else input_food_type if input_food_type in {"冷食", "热食"} else ""
    asset_id = str(input_data.get("assetId") or f"asset_{node_id}")

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
        "food_type": food_type,
        "visual_subject_type": visual_subject_type,
        "duration": duration,
        "prompt": prompt,
        "output_filename": output_filename,
        "asset_id": asset_id,
        "clip_version": _next_clip_version(asset_id),
    }
    job.update(task_metadata("kling_generation"))
    with _JOB_LOCK:
        _save_job(draft_id, job)
        _persist_generator_status(draft_id, node_id, "生成中", generation_job_id=job_id)

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
            _schedule_generation_postprocess(draft_id, job, video_url, session, input_dish, category, duration, prompt)
        except Exception as exc:
            _update_job(draft_id, job, status="error", stage="生成失败", error=str(exc))
            _persist_generator_status(draft_id, node_id, "生成失败")

    threading.Thread(target=worker, name=f"canvas-generate-{job_id}", daemon=True).start()
    return job
