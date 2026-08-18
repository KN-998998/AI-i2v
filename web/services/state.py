# -*- coding: utf-8 -*-
"""Batch state and manifest persistence."""
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline.config import OUTPUT_ROOT, batch_subdirs
from web.core.logging import get_logger

logger = get_logger(__name__)
_STATE_LOCK = threading.RLock()
BATCH_STATES: dict[str, dict[str, Any]] = {}


def default_state(batch_id: str) -> dict[str, Any]:
    return {
        "id": batch_id,
        "name": "",
        "date": "",
        "dishes": [],
        "status": "created",
        "current_step": 0,
        "step_progress": {},
        "selected_clips": {},
        "captions": {},
        "videos": [],
        "error": None,
        "created_at": datetime.now().isoformat(),
    }


def get_batch_state(batch_id: str) -> dict[str, Any]:
    with _STATE_LOCK:
        if batch_id in BATCH_STATES:
            return BATCH_STATES[batch_id]

        state_file = OUTPUT_ROOT / batch_id / "state.json"
        if state_file.exists():
            try:
                with open(state_file, encoding="utf-8") as f:
                    state = json.load(f)
                BATCH_STATES[batch_id] = state
                return state
            except Exception:
                logger.exception("Failed to load state file: %s", state_file)

        state = default_state(batch_id)
        BATCH_STATES[batch_id] = state
        return state


def load_manifest(dirs: dict[str, Path], step_name: str) -> Any:
    manifest_map = {
        "images": dirs["images"] / "manifest.json",
        "prompts": dirs["prompts"] / "manifest.json",
        "clips": dirs["clips"] / "manifest.json",
        "composed": dirs["composed"] / "manifest.json",
        "final": dirs["final"] / "manifest.json",
    }
    path = manifest_map.get(step_name)
    if path and path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def summarize_clip_results(results: list[dict[str, Any]]) -> tuple[int, int, str]:
    ok = sum(1 for r in results if r.get("status") == "ok")
    failed = len(results) - ok
    first_error = next((r.get("error") for r in results if r.get("status") != "ok" and r.get("error")), "")
    return ok, failed, first_error


def save_state(batch_id: str, state: dict[str, Any] | None = None) -> None:
    with _STATE_LOCK:
        if state is not None:
            BATCH_STATES[batch_id] = state
        state = BATCH_STATES.get(batch_id)
        if not state:
            return
        state_file = OUTPUT_ROOT / batch_id / "state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        safe = {}
        for key, value in state.items():
            try:
                json.dumps(value)
                safe[key] = value
            except TypeError:
                safe[key] = str(value)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(safe, f, ensure_ascii=False, indent=2, default=str)


def reconcile_step2_state(batch_id: str, state: dict[str, Any]) -> dict[str, Any]:
    prompts_step = state.setdefault("step_progress", {}).get("step2") or {}
    if prompts_step.get("status") == "done":
        return state

    batch_dir = OUTPUT_ROOT / batch_id
    dirs = batch_subdirs(batch_dir)
    prompts = load_manifest(dirs, "prompts") or []
    if not prompts:
        return state

    dish_names = {dish.get("name") for dish in state.get("dishes", []) if dish.get("name")}
    prompt_names = {prompt.get("dish") for prompt in prompts if prompt.get("dish")}
    if dish_names and not dish_names.issubset(prompt_names):
        return state

    state["step_progress"]["step2"] = {
        "status": "done",
        "total": len(dish_names) or len(prompts),
        "done": len(prompts),
        "result": prompts,
        "recovered": True,
    }
    state["error"] = None
    save_state(batch_id, state)
    return state


def reconcile_step3_state(batch_id: str, state: dict[str, Any]) -> dict[str, Any]:
    step3 = state.get("step_progress", {}).get("step3")
    if not step3 or step3.get("status") not in ("running", "error"):
        return state

    batch_dir = OUTPUT_ROOT / batch_id
    dirs = batch_subdirs(batch_dir)
    clips = load_manifest(dirs, "clips") or []
    total = step3.get("total") or len(clips)
    if not clips or len(clips) < total:
        return state

    ok, _failed, first_error = summarize_clip_results(clips)
    step3["done"] = len(clips)
    step3["results"] = clips
    if ok:
        step3["status"] = "done"
        state["status"] = "reviewing"
        state["error"] = None
    else:
        step3["status"] = "error"
        step3["error"] = first_error or "Kling 片段生成全部失败"
        state["status"] = "error"
        state["error"] = f"Kling 片段生成失败：{step3['error']}"
    save_state(batch_id, state)
    return state


def reconcile_state(batch_id: str, state: dict[str, Any]) -> dict[str, Any]:
    state = reconcile_step2_state(batch_id, state)
    state = reconcile_step3_state(batch_id, state)
    return state


def load_state(batch_id: str) -> dict[str, Any]:
    with _STATE_LOCK:
        cached = BATCH_STATES.get(batch_id)
    if cached is not None:
        state = reconcile_state(batch_id, cached)
        with _STATE_LOCK:
            BATCH_STATES[batch_id] = state
        return state

    state_file = OUTPUT_ROOT / batch_id / "state.json"
    if state_file.exists():
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)
        with _STATE_LOCK:
            BATCH_STATES[batch_id] = state
        state = reconcile_state(batch_id, state)
        with _STATE_LOCK:
            BATCH_STATES[batch_id] = state
        return state
    return get_batch_state(batch_id)