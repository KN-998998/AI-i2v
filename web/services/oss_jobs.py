"""Durable asynchronous OSS material-selection jobs."""
from __future__ import annotations

import json
import random
import re
import shutil
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from pipeline.config import FINAL_RESOLUTION, PREP_JPEG_QUALITY
from web.core.settings import (
    OSS_JOB_ROOT,
    OSS_MAX_ASSETS_PER_CATEGORY,
    OSS_MAX_CATEGORIES,
    OSS_MAX_CONCURRENT_JOBS,
    OSS_MAX_REQUESTS_PER_MINUTE,
    OSS_JOB_RETENTION_HOURS,
    OSS_MAX_TOTAL_ASSETS,
)
from web.services.oss_asset_provider import (
    OssAssetProvider,
    InsufficientAssetsError,
    OssProviderError,
    asset_filename,
)
from web.services.task_contract import is_recoverable, task_metadata, update_task

_JOB_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_ASSET_ID_RE = re.compile(r"^asset_\d{3}$")
_JOB_LOCK = threading.RLock()
_JOB_SEMAPHORE = threading.BoundedSemaphore(OSS_MAX_CONCURRENT_JOBS)
_RATE_LIMIT_LOCK = threading.Lock()
_SUBMISSIONS: dict[str, deque[float]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _job_path(job_id: str) -> Path:
    if not _JOB_ID_RE.fullmatch(job_id or ""):
        raise ValueError("任务 ID 无效")
    return OSS_JOB_ROOT / f"{job_id}.json"


def job_directory(job_id: str) -> Path:
    _job_path(job_id)
    return OSS_JOB_ROOT / job_id


def _save_job(job: dict[str, Any]) -> None:
    OSS_JOB_ROOT.mkdir(parents=True, exist_ok=True)
    destination = _job_path(str(job["job_id"]))
    temporary = destination.with_suffix(f".{uuid.uuid4().hex}.tmp")
    with _JOB_LOCK:
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(job, stream, ensure_ascii=False, indent=2)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)


def _load_job(job_id: str) -> dict[str, Any] | None:
    path = _job_path(job_id)
    if not path.is_file():
        return None
    with _JOB_LOCK:
        with path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    return payload if isinstance(payload, dict) else None


def _update_job(job: dict[str, Any], *, status: str | None = None, stage: str | None = None, **changes: Any) -> None:
    update_task(job, status=status, stage=stage, **changes)
    _save_job(job)


def allow_submission(client_key: str) -> bool:
    """Apply a small in-process IP rate limit before a new job is queued."""
    now = time.monotonic()
    with _RATE_LIMIT_LOCK:
        timestamps = _SUBMISSIONS.setdefault(client_key or "unknown", deque())
        while timestamps and now - timestamps[0] >= 60:
            timestamps.popleft()
        if len(timestamps) >= OSS_MAX_REQUESTS_PER_MINUTE:
            return False
        timestamps.append(now)
        return True


def normalize_selections(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("selections 必须是非空数组")
    if len(raw) > OSS_MAX_CATEGORIES:
        raise ValueError(f"一次最多选择 {OSS_MAX_CATEGORIES} 个分类")

    selections: list[dict[str, Any]] = []
    categories: set[str] = set()
    total = 0
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("每个分类选择必须是对象")
        category = str(item.get("category") or "").strip()
        if not category or "/" in category or "\\" in category or category in {".", ".."}:
            raise ValueError("分类名称无效")
        if category in categories:
            raise ValueError(f"分类“{category}”不能重复提交")
        categories.add(category)
        count = item.get("count")
        if isinstance(count, bool):
            raise ValueError("分类数量必须是正整数")
        try:
            count = int(count)
        except (TypeError, ValueError) as exc:
            raise ValueError("分类数量必须是正整数") from exc
        if count < 1 or count > OSS_MAX_ASSETS_PER_CATEGORY:
            raise ValueError(f"每个分类数量必须在 1 到 {OSS_MAX_ASSETS_PER_CATEGORY} 之间")
        total += count
        selections.append({"category": category, "count": count})
    if total > OSS_MAX_TOTAL_ASSETS:
        raise ValueError(f"单个任务最多抽取 {OSS_MAX_TOTAL_ASSETS} 张图片")
    return selections


def create_oss_job(raw_selections: Any, seed: Any | None = None) -> dict[str, Any]:
    selections = normalize_selections(raw_selections)
    job_id = uuid.uuid4().hex
    try:
        normalized_seed = int(seed) if seed is not None else random.SystemRandom().randrange(1, 2**63)
    except (TypeError, ValueError) as exc:
        raise ValueError("seed 必须是整数") from exc
    job: dict[str, Any] = {
        "job_id": job_id,
        "task_type": "oss_asset_ingestion",
        "status": "queued",
        "stage": "等待任务",
        "created_at": _now(),
        "updated_at": _now(),
        "selections": selections,
        "seed": normalized_seed,
        "assets": [],
        "skipped_assets": [],
        "job_directory": str(job_directory(job_id)),
        **task_metadata("oss_asset_ingestion"),
    }
    # task_metadata is intentionally shared with older jobs and does not own
    # the public status field; the OSS job sets it explicitly above.
    _save_job(job)
    threading.Thread(target=_run_job, args=(job_id,), name=f"oss-assets-{job_id[:8]}", daemon=True).start()
    return job


def get_oss_job(job_id: str) -> dict[str, Any] | None:
    try:
        return _load_job(job_id)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _normalize_image(source: Path, destination: Path) -> None:
    target_width, target_height = FINAL_RESOLUTION
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
        normalized = ImageOps.fit(
            image,
            (target_width, target_height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        normalized.save(destination, "JPEG", quality=PREP_JPEG_QUALITY, optimize=True, progressive=True)


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _normalized_filename(index: int, dish_name: str) -> str:
    safe_name = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", dish_name).strip("._-")[:80] or "asset"
    return f"{index:03d}_{safe_name}.jpg"


def _mark_failed(job: dict[str, Any], error: Exception) -> None:
    _update_job(job, status="error", stage="素材任务失败", error=str(error), error_type=type(error).__name__)
    shutil.rmtree(job_directory(str(job["job_id"])), ignore_errors=True)
    _update_job(job, cleanup="temporary_files_removed")


def _cancelled(job_id: str) -> bool:
    current = get_oss_job(job_id)
    return bool(current and current.get("status") == "cancelled")


def _run_job(job_id: str) -> None:
    job = get_oss_job(job_id)
    if job is None:
        return
    with _JOB_SEMAPHORE:
        try:
            _update_job(job, status="selecting_materials", stage="从 OSS 抽取不重复菜品")
            if _cancelled(job_id):
                return
            provider = OssAssetProvider()
            selected = provider.select_unique_assets(job["selections"], random.Random(int(job["seed"])))
            job["assets"] = selected
            _save_job(job)

            root = job_directory(job_id)
            source_root = root / "source"
            normalized_root = root / "normalized"
            _update_job(job, status="downloading", stage="下载 OSS 图片", total=len(selected), completed=0)
            for index, asset in enumerate(selected, start=1):
                if _cancelled(job_id):
                    return
                destination = source_root / asset_filename(asset, index)
                try:
                    provider.download_asset(asset, destination)
                    asset["source_path"] = _relative_path(destination, root)
                    asset["status"] = "downloaded"
                except Exception as exc:
                    asset["status"] = "skipped"
                    asset["skip_reason"] = str(exc)
                    job.setdefault("skipped_assets", []).append({**asset, "skip_reason": str(exc)})
                _update_job(job, completed=index)

            _update_job(job, status="preprocessing", stage="修正 EXIF 并转换为 9:16", completed=0)
            for index, asset in enumerate(selected, start=1):
                if _cancelled(job_id):
                    return
                if asset.get("status") != "downloaded":
                    continue
                source = root / str(asset["source_path"])
                destination = normalized_root / _normalized_filename(index, str(asset.get("dish_name") or "asset"))
                try:
                    _normalize_image(source, destination)
                    asset["normalized_path"] = _relative_path(destination, root)
                    asset["normalized_width"], asset["normalized_height"] = FINAL_RESOLUTION
                    asset["status"] = "ready_for_review"
                except Exception as exc:
                    asset["status"] = "skipped"
                    asset["skip_reason"] = f"图片无法处理: {exc}"
                    job.setdefault("skipped_assets", []).append({**asset, "skip_reason": asset["skip_reason"]})
                _update_job(job, completed=index)

            required = {str(item["category"]): int(item["count"]) for item in job["selections"]}
            available = {
                category: sum(1 for asset in selected if asset.get("category") == category and asset.get("status") == "ready_for_review")
                for category in required
            }
            insufficient = [(category, required[category], available[category]) for category in required if available[category] < required[category]]
            if insufficient:
                detail = "；".join(f"{category} 可用 {available_count}/{requested}" for category, requested, available_count in insufficient)
                raise ValueError(f"图片预处理后可用数量不足：{detail}")

            _update_job(
                job,
                status="awaiting_review",
                stage="等待人工审查",
                completed=len(selected),
                asset_count=sum(available.values()),
                output_resolution={"width": FINAL_RESOLUTION[0], "height": FINAL_RESOLUTION[1]},
            )
        except (InsufficientAssetsError, OssProviderError, OSError, ValueError) as exc:
            _mark_failed(job, exc)
        except Exception as exc:  # keep unexpected failures persisted without leaking credentials
            _mark_failed(job, RuntimeError(f"OSS 任务内部错误: {exc}"))


def approve_oss_job(job_id: str) -> dict[str, Any]:
    job = get_oss_job(job_id)
    if job is None:
        raise ValueError("素材任务不存在")
    if job.get("status") != "awaiting_review":
        raise ValueError("只有等待人工审查的任务可以确认")
    _update_job(job, status="completed", stage="人工审查通过", approved_at=_now())
    return job


def cancel_oss_job(job_id: str) -> dict[str, Any]:
    job = get_oss_job(job_id)
    if job is None:
        raise ValueError("素材任务不存在")
    if job.get("status") in {"completed", "error", "cancelled"}:
        raise ValueError("当前任务无法取消")
    _update_job(job, status="cancelled", stage="任务已取消", cancelled_at=_now())
    shutil.rmtree(job_directory(job_id), ignore_errors=True)
    return job


def mark_oss_asset_for_regeneration(job_id: str, asset_id: str) -> dict[str, Any]:
    """Record the human-review decision for a single asset.

    Actual Kling regeneration still uses the existing draft/node generation
    endpoint.  This marker keeps the OSS manifest auditable until that node is
    connected by the frontend workflow.
    """
    if not _ASSET_ID_RE.fullmatch(asset_id or ""):
        raise ValueError("素材 ID 无效")
    job = get_oss_job(job_id)
    if job is None:
        raise ValueError("素材任务不存在")
    if job.get("status") not in {"awaiting_review", "completed"}:
        raise ValueError("当前任务不在人工审查阶段")
    for asset in job.get("assets", []):
        if isinstance(asset, dict) and asset.get("asset_id") == asset_id:
            asset["review_decision"] = "regenerate"
            asset["reviewed_at"] = _now()
            _update_job(job, status="awaiting_review", stage="单个片段待重新生成")
            return job
    raise ValueError("素材不存在")


def asset_file(job_id: str, asset_id: str, kind: str) -> Path | None:
    if not _ASSET_ID_RE.fullmatch(asset_id or "") or kind not in {"source", "normalized"}:
        return None
    job = get_oss_job(job_id)
    if not job:
        return None
    for asset in job.get("assets", []):
        if isinstance(asset, dict) and asset.get("asset_id") == asset_id:
            relative = asset.get(f"{kind}_path")
            if not relative:
                return None
            root = job_directory(job_id).resolve()
            candidate = (root / str(relative)).resolve()
            if root not in candidate.parents or not candidate.is_file():
                return None
            return candidate
    return None


def recover_oss_jobs() -> int:
    if not OSS_JOB_ROOT.is_dir():
        return 0
    recovered = 0
    for path in OSS_JOB_ROOT.glob("*.json"):
        try:
            job = get_oss_job(path.stem)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if job and is_recoverable(job.get("status")):
            threading.Thread(target=_run_job, args=(path.stem,), name=f"oss-assets-recover-{path.stem[:8]}", daemon=True).start()
            recovered += 1
    return recovered


def cleanup_expired_oss_jobs() -> int:
    """Remove only terminal OSS job directories after the retention window."""
    if not OSS_JOB_ROOT.is_dir():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=OSS_JOB_RETENTION_HOURS)
    removed = 0
    for path in OSS_JOB_ROOT.glob("*.json"):
        try:
            job = get_oss_job(path.stem)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not job or job.get("status") not in {"completed", "error", "cancelled"}:
            continue
        try:
            updated_at = datetime.fromisoformat(str(job.get("updated_at")).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            updated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if updated_at >= cutoff:
            continue
        shutil.rmtree(job_directory(path.stem), ignore_errors=True)
        path.unlink(missing_ok=True)
        removed += 1
    return removed
