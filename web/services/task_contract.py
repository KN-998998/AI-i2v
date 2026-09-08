"""Shared persistence contract for long-running canvas jobs.

This module intentionally contains no worker or HTTP code.  It standardises
the persisted state used by image processing, Kling generation and composition
so restart recovery and future queue backends can use the same contract.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

TaskStatus = Literal[
    "queued", "running", "polling", "downloading", "analyzing",
    "retrying", "done", "error",
]

TASK_STATUSES: frozenset[str] = frozenset({
    "queued", "running", "polling", "downloading", "analyzing",
    "retrying", "done", "error",
})
RECOVERABLE_TASK_STATUSES: frozenset[str] = frozenset({
    "queued", "running", "polling", "downloading", "analyzing", "retrying",
})
_MAX_EVENTS = 40


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def task_metadata(task_type: str) -> dict[str, Any]:
    """Fields shared by newly created persisted jobs."""
    now = utc_now()
    return {
        "task_type": task_type,
        "status_version": 1,
        "phase": "queued",
        "retry_count": 0,
        "max_retries": 0,
        "events": [{"at": now, "status": "queued", "stage": "等待任务"}],
    }


def update_task(
    task: dict[str, Any],
    *,
    status: str | None = None,
    stage: str | None = None,
    **changes: Any,
) -> dict[str, Any]:
    """Apply a canonical update and retain a short state transition history."""
    if status is not None and status not in TASK_STATUSES:
        raise ValueError(f"unknown task status: {status}")
    previous_status = str(task.get("status") or "queued")
    previous_stage = str(task.get("stage") or "等待任务")
    current_status = status or previous_status
    current_stage = stage if stage is not None else previous_stage
    task.update(changes)
    task.update({
        "status": current_status,
        "stage": current_stage,
        "status_version": task.get("status_version", 1),
        "retry_count": task.get("retry_count", 0),
        "max_retries": task.get("max_retries", 0),
        "phase": _phase_for(current_status),
    })
    task["updated_at"] = utc_now()
    events = task.get("events") if isinstance(task.get("events"), list) else []
    if current_status != previous_status or current_stage != previous_stage or not events:
        events.append({"at": task["updated_at"], "status": current_status, "stage": current_stage})
    task["events"] = [event for event in events if isinstance(event, dict)][-_MAX_EVENTS:]
    return task


def is_recoverable(status: Any) -> bool:
    return str(status or "") in RECOVERABLE_TASK_STATUSES


def _phase_for(status: str) -> str:
    return {
        "queued": "queued", "running": "processing", "polling": "polling",
        "downloading": "downloading", "analyzing": "analyzing",
        "retrying": "retrying", "done": "completed", "error": "failed",
    }.get(status, "unknown")
