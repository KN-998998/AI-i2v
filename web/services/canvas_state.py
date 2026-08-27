# -*- coding: utf-8 -*-
"""Durable storage for visual workflow drafts and their uploaded files."""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from web.core.settings import CANVAS_BACKGROUND_ROOT, CANVAS_DRAFT_ROOT, MAX_UPLOAD_SIZE

DRAFT_VERSION = 1
_DRAFT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CHUNK_SIZE = 1024 * 1024
_DRAFT_LOCK = threading.RLock()
_ALLOWED_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".gif"},
    "audio": {".mp3", ".wav", ".m4a", ".aac", ".ogg"},
}
_BACKGROUND_EXTENSIONS = _ALLOWED_EXTENSIONS["image"]


def _validate_draft_id(draft_id: str) -> str:
    if not _DRAFT_ID_RE.fullmatch(draft_id):
        raise ValueError("草稿 ID 无效")
    return draft_id


def draft_directory(draft_id: str) -> Path:
    return CANVAS_DRAFT_ROOT / _validate_draft_id(draft_id)


def draft_file(draft_id: str) -> Path:
    return draft_directory(draft_id) / "draft.json"


def load_draft(draft_id: str) -> dict[str, Any] | None:
    path = draft_file(draft_id)
    if not path.exists():
        return None
    # Windows editors may write the persisted draft with a UTF-8 BOM.
    with _DRAFT_LOCK:
        with path.open("r", encoding="utf-8-sig") as stream:
            payload = json.load(stream)
    if not isinstance(payload, dict) or payload.get("version") != DRAFT_VERSION:
        raise ValueError("草稿版本不受支持")
    return payload


def _stable_json(value: Any, *, drop_timing: bool = False) -> str:
    def normalize(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                key: normalize(child)
                for key, child in sorted(item.items())
                if not (drop_timing and key in {"startSeconds", "endSeconds"})
            }
        if isinstance(item, list):
            return [normalize(child) for child in item]
        return item

    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _compose_job_matches_workspace(workspace: dict[str, Any], job: Any, field: str) -> bool:
    if not isinstance(job, dict):
        return False
    timeline = job.get("timeline")
    if isinstance(timeline, list) and _stable_json(workspace.get("clips", [])) != _stable_json(timeline):
        return False
    if field == "finalJob":
        saved_sound = job.get("sound")
        current_sound = workspace.get("soundConfig")
        if isinstance(saved_sound, dict) and isinstance(current_sound, dict):
            if _stable_json(saved_sound, drop_timing=True) != _stable_json(current_sound, drop_timing=True):
                return False
    return True


def _newer_job(current: Any, previous: Any) -> Any:
    if not isinstance(previous, dict):
        return current
    if not isinstance(current, dict):
        return previous
    if str(previous.get("updated_at") or "") > str(current.get("updated_at") or ""):
        return previous
    return current


def _merge_compose_jobs(payload: dict[str, Any], existing: dict[str, Any] | None) -> list[dict[str, Any]]:
    incoming = payload.get("composeWorkspaces")
    if not isinstance(incoming, list):
        incoming = []
    previous_by_id = {
        str(item.get("id")): item
        for item in (existing or {}).get("composeWorkspaces", [])
        if isinstance(item, dict) and item.get("id")
    }
    merged: list[dict[str, Any]] = []
    for item in incoming:
        if not isinstance(item, dict):
            continue
        workspace = dict(item)
        previous = previous_by_id.get(str(workspace.get("id")))
        if isinstance(previous, dict):
            for field in ("job", "finalJob"):
                previous_job = previous.get(field)
                if _compose_job_matches_workspace(workspace, previous_job, field):
                    workspace[field] = _newer_job(workspace.get(field), previous_job)
        merged.append(workspace)
    return merged


def save_draft(draft_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload.get("nodes"), list) or not isinstance(payload.get("edges"), list):
        raise ValueError("草稿必须包含 nodes 和 edges 数组")
    if not isinstance(payload.get("timeline"), list):
        raise ValueError("草稿必须包含 timeline 数组")

    existing: dict[str, Any] | None = None
    try:
        existing = load_draft(draft_id)
    except (OSError, ValueError, json.JSONDecodeError):
        existing = None
    compose_workspaces = _merge_compose_jobs(payload, existing)
    compose_job = payload.get("composeJob")
    for workspace in compose_workspaces:
        for field in ("job", "finalJob"):
            candidate = workspace.get(field)
            if isinstance(candidate, dict):
                compose_job = _newer_job(candidate, compose_job)
    directory = draft_directory(draft_id)
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    persisted = {
        "version": DRAFT_VERSION,
        "draft_id": draft_id,
        "updated_at": now,
        "activePanel": payload.get("activePanel", "prompt"),
        "nextNodeNumber": payload.get("nextNodeNumber", 1),
        "nodes": payload["nodes"],
        "edges": payload["edges"],
        "timeline": payload["timeline"],
        "candidateClips": payload.get("candidateClips", payload["timeline"]),
        "composeBatchCount": payload.get("composeBatchCount", 1),
        "composeClipCount": payload.get("composeClipCount", len(payload["timeline"])),
        "composeWorkspaces": compose_workspaces or [{"id": "compose_1", "title": "成片 1", "clips": payload["timeline"], "job": payload.get("composeJob")}],
        "activeComposeWorkspaceId": payload.get("activeComposeWorkspaceId"),
        "bgmName": payload.get("bgmName", "默认 BGM"),
        "bgmUrl": payload.get("bgmUrl", ""),
        "composeJob": compose_job,
    }
    temporary = directory / f"draft.{uuid.uuid4().hex}.tmp"
    try:
        with _DRAFT_LOCK:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(persisted, stream, ensure_ascii=False, indent=2)
            temporary.replace(draft_file(draft_id))
    finally:
        temporary.unlink(missing_ok=True)
    return persisted


async def save_upload(draft_id: str, upload: UploadFile, kind: str) -> dict[str, Any]:
    extensions = _ALLOWED_EXTENSIONS.get(kind)
    if extensions is None:
        raise ValueError("文件类型不受支持")
    original_name = Path(upload.filename or "upload").name
    extension = Path(original_name).suffix.lower()
    if extension not in extensions:
        raise ValueError("文件扩展名不受支持")

    directory = draft_directory(draft_id) / "files"
    directory.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    destination = directory / stored_name
    total = 0
    try:
        with destination.open("wb") as stream:
            while chunk := await upload.read(_CHUNK_SIZE):
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE:
                    raise ValueError(f"文件不能超过 {MAX_UPLOAD_SIZE // (1024 * 1024)} MB")
                stream.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return {
        "kind": kind,
        "original_name": original_name,
        "stored_name": stored_name,
        "size": total,
        "content_type": upload.content_type or "application/octet-stream",
    }


def uploaded_file(draft_id: str, stored_name: str) -> Path | None:
    safe_name = Path(stored_name).name
    if safe_name != stored_name or not safe_name:
        return None
    path = draft_directory(draft_id) / "files" / safe_name
    return path if path.exists() and path.is_file() else None


def generated_file_path(draft_id: str, suffix: str = ".png") -> Path:
    """Reserve a private draft file path for a server-generated image."""
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    if suffix.lower() not in _BACKGROUND_EXTENSIONS:
        raise ValueError("Unsupported generated image format")
    directory = draft_directory(draft_id) / "files"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"generated_{uuid.uuid4().hex}{suffix.lower()}"


async def save_background_upload(upload: UploadFile) -> dict[str, Any]:
    """Persist a reusable background template outside an individual draft."""
    original_name = Path(upload.filename or "background").name
    extension = Path(original_name).suffix.lower()
    if extension not in _BACKGROUND_EXTENSIONS:
        raise ValueError("背景模板仅支持 JPG、PNG、WEBP 或 GIF 图片")

    CANVAS_BACKGROUND_ROOT.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    destination = CANVAS_BACKGROUND_ROOT / stored_name
    total = 0
    try:
        with destination.open("wb") as stream:
            while chunk := await upload.read(_CHUNK_SIZE):
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE:
                    raise ValueError(f"文件不能超过 {MAX_UPLOAD_SIZE // (1024 * 1024)} MB")
                stream.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return {
        "original_name": original_name,
        "stored_name": stored_name,
        "size": total,
        "content_type": upload.content_type or "application/octet-stream",
    }


def background_file(stored_name: str) -> Path | None:
    safe_name = Path(stored_name).name
    if safe_name != stored_name or not safe_name:
        return None
    path = CANVAS_BACKGROUND_ROOT / safe_name
    return path if path.exists() and path.is_file() else None


def list_background_files() -> list[Path]:
    if not CANVAS_BACKGROUND_ROOT.exists():
        return []
    return sorted(
        (path for path in CANVAS_BACKGROUND_ROOT.iterdir() if path.is_file() and path.suffix.lower() in _BACKGROUND_EXTENSIONS),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
