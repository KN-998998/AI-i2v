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

from pipeline.config import OUTPUT_ROOT, batch_subdirs
from web.services.canvas_state import draft_directory, load_draft

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
    if not dish or not OUTPUT_ROOT.exists():
        return None
    candidates = []
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


def start_compose(draft_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    draft = load_draft(draft_id)
    if draft is None:
        raise ValueError("画布草稿不存在，请先保存草稿")
    workspace = next((item for item in draft.get("composeWorkspaces", []) if item.get("id") == workspace_id), None) if workspace_id else None
    timeline = (workspace or {}).get("clips") if workspace is not None else draft.get("timeline") or []
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
                duration = float(clip.get("timelineDuration") or 2.5)
                duration = max(0.1, min(duration, 60.0))
                trimmed_path = output_dir / f"segment_{index:03d}.mp4"
                trim_clip(str(source), str(trimmed_path), start=0.5, duration=duration)
                trimmed_paths.append(str(trimmed_path))
                temporary_paths.append(str(trimmed_path))

            output_path = output_dir / "canvas_composed.mp4"
            concat_clips(trimmed_paths, str(output_path), subtitles=[], brand_info=None)
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
    path = draft_directory(draft_id) / "compositions" / job_id / "canvas_composed.mp4"
    return path if path.exists() and path.is_file() else None
