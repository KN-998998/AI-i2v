# -*- coding: utf-8 -*-
"""Durable weekly production plans and three-day dish reservations.

The scheduler deliberately owns only plan execution.  Video assets remain in
the existing canvas draft and clip library so manual review and composition use
the same workflow as one-off productions.
"""
from __future__ import annotations

import copy
import json
import random
import sqlite3
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from web.core.settings import WEEKLY_PLAN_DB, WEEKLY_PLAN_TIMEZONE
from web.services import canvas_asset_library as asset_library
from web.services.canvas_generation import get_generation_job, start_generation
from web.services.canvas_image_processing import get_image_processing_job, start_image_processing
from web.services.canvas_state import load_draft, save_draft

_LOCK = threading.RLock()
_SCHEDULER_STARTED = False
_SCHEDULER_STOP = threading.Event()
_CATEGORIES = asset_library.ASSET_CATEGORIES


def _now() -> str:
    return datetime.now(ZoneInfo(WEEKLY_PLAN_TIMEZONE)).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    WEEKLY_PLAN_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(WEEKLY_PLAN_DB, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize() -> None:
    with _LOCK, _connect() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS weekly_plans (
                id TEXT PRIMARY KEY,
                week_start TEXT NOT NULL,
                duration_days INTEGER NOT NULL DEFAULT 7,
                asset_root TEXT NOT NULL,
                background_root TEXT NOT NULL,
                template_draft_id TEXT NOT NULL,
                run_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS daily_plans (
                id TEXT PRIMARY KEY,
                weekly_plan_id TEXT NOT NULL REFERENCES weekly_plans(id) ON DELETE CASCADE,
                run_date TEXT NOT NULL,
                candidate_count INTEGER NOT NULL,
                video_count INTEGER NOT NULL,
                clips_per_video INTEGER NOT NULL,
                category_counts TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled',
                draft_id TEXT,
                error TEXT,
                started_at TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(weekly_plan_id, run_date)
            );
            CREATE TABLE IF NOT EXISTS asset_reservations (
                id TEXT PRIMARY KEY,
                daily_plan_id TEXT NOT NULL REFERENCES daily_plans(id) ON DELETE CASCADE,
                run_date TEXT NOT NULL,
                dish_key TEXT NOT NULL,
                dish_name TEXT NOT NULL,
                category TEXT NOT NULL,
                food_type TEXT NOT NULL,
                visual_subject_type TEXT NOT NULL,
                image_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(daily_plan_id, dish_key)
            );
            CREATE INDEX IF NOT EXISTS idx_asset_reservations_window ON asset_reservations(run_date, dish_key);
            CREATE TABLE IF NOT EXISTS clip_reviews (
                id TEXT PRIMARY KEY,
                daily_plan_id TEXT NOT NULL REFERENCES daily_plans(id) ON DELETE CASCADE,
                clip_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                source_start REAL,
                source_end REAL,
                updated_at TEXT NOT NULL,
                UNIQUE(daily_plan_id, clip_id)
            );
        """)
        columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(weekly_plans)")}
        if "duration_days" not in columns:
            connection.execute("ALTER TABLE weekly_plans ADD COLUMN duration_days INTEGER NOT NULL DEFAULT 7")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("日期必须使用 YYYY-MM-DD") from exc


def _parse_run_at(value: Any) -> str:
    text = str(value or "09:00").strip()
    try:
        datetime.strptime(text, "%H:%M")
    except ValueError as exc:
        raise ValueError("执行时间必须使用 HH:MM") from exc
    return text


def _positive(value: Any, name: str, minimum: int = 1, maximum: int = 80) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}必须为整数") from exc
    if not minimum <= number <= maximum:
        raise ValueError(f"{name}必须在 {minimum}-{maximum} 之间")
    return number


def _normalize_counts(raw: Mapping[str, Any] | None, candidate_count: int) -> dict[str, int]:
    values = {category: max(0, int((raw or {}).get(category, 0) or 0)) for category in _CATEGORIES}
    if sum(values.values()) not in {0, candidate_count}:
        raise ValueError("分类数量合计必须等于候选片段数；留空则由系统自动分配")
    return values


def _dish_key(value: str) -> str:
    return asset_library.simplify_dish_name(value).casefold()


def _library_candidates(asset_root: str) -> list[dict[str, Any]]:
    root = Path(asset_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("菜品素材库路径不存在或不是文件夹")
    groups = asset_library._merge_duplicate_dish_directories(asset_library._dish_directories(root))
    classifications, _mode, _warning = asset_library._classify_library_dish_groups(root, groups)
    result: list[dict[str, Any]] = []
    for group in groups:
        classification = classifications[group["dishName"]]
        category = str(classification.get("category") or "")
        food_type = str(classification.get("foodType") or "")
        if category not in _CATEGORIES or not food_type:
            continue
        result.append({
            "dish_key": _dish_key(str(group["dishName"])),
            "dish_name": str(group["dishName"]),
            "category": category,
            "food_type": food_type,
            "visual_subject_type": str(classification.get("visualSubjectType") or asset_library.DEFAULT_VISUAL_SUBJECT_TYPE),
            "images": [str(path) for path in group["images"]],
        })
    return result


def _reserved_keys(connection: sqlite3.Connection, run_date: date, exclude_plan_id: str | None = None) -> set[str]:
    # Day N may not reuse a dish selected for N-1 or N-2.  Reservations on N
    # itself are also excluded so two active plans cannot silently collide.
    start = (run_date - timedelta(days=2)).isoformat()
    params: list[Any] = [start, run_date.isoformat()]
    clause = ""
    if exclude_plan_id:
        clause = " AND d.weekly_plan_id != ?"
        params.append(exclude_plan_id)
    rows = connection.execute(
        "SELECT DISTINCT r.dish_key FROM asset_reservations r "
        "JOIN daily_plans d ON d.id = r.daily_plan_id "
        "JOIN weekly_plans w ON w.id = d.weekly_plan_id "
        "WHERE r.run_date BETWEEN ? AND ? AND w.active = 1" + clause,
        params,
    ).fetchall()
    return {str(row["dish_key"]) for row in rows}


def _edit_blocked_keys(connection: sqlite3.Connection, daily_id: str, run_date: date) -> set[str]:
    """Keep an edited day compatible with already-reserved neighbouring days."""
    rows = connection.execute(
        "SELECT DISTINCT dish_key FROM asset_reservations WHERE run_date BETWEEN ? AND ? AND daily_plan_id != ?",
        ((run_date - timedelta(days=2)).isoformat(), (run_date + timedelta(days=2)).isoformat(), daily_id),
    ).fetchall()
    return {str(row["dish_key"]) for row in rows}


def _allocate_candidates(candidates: list[dict[str, Any]], target: int, category_counts: dict[str, int], blocked: set[str], rng: random.Random) -> list[dict[str, Any]]:
    eligible = [item for item in candidates if item["dish_key"] not in blocked]
    by_category = {category: [item for item in eligible if item["category"] == category] for category in _CATEGORIES}
    if sum(category_counts.values()) == 0:
        # Capacity-weighted random allocation.  Once a dish is drawn it is
        # removed, so a day never includes the same dish folder twice.
        pool = eligible[:]
        rng.shuffle(pool)
        selected = pool[:target]
        if len(selected) < target:
            raise ValueError(f"3天去重后仅有 {len(selected)} 个可用菜品文件夹，无法抽取 {target} 个候选片段")
        return selected
    selected: list[dict[str, Any]] = []
    for category in _CATEGORIES:
        pool = by_category[category][:]
        rng.shuffle(pool)
        need = category_counts[category]
        if len(pool) < need:
            raise ValueError(f"{category} 在3天去重后仅有 {len(pool)} 个可用菜品文件夹，缺少 {need - len(pool)} 个")
        selected.extend(pool[:need])
    return selected


def _serialise_daily(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    reservations = connection.execute(
        "SELECT dish_name, dish_key, category, image_path FROM asset_reservations WHERE daily_plan_id = ? ORDER BY category, dish_name",
        (row["id"],),
    ).fetchall()
    reviews = connection.execute(
        "SELECT decision, COUNT(*) AS count FROM clip_reviews WHERE daily_plan_id = ? GROUP BY decision", (row["id"],)
    ).fetchall()
    review_summary = {str(item["decision"]): int(item["count"]) for item in reviews}
    return {
        "id": row["id"], "runDate": row["run_date"], "candidateCount": row["candidate_count"],
        "videoCount": row["video_count"], "clipsPerVideo": row["clips_per_video"],
        "categoryCounts": json.loads(row["category_counts"]), "status": row["status"], "draftId": row["draft_id"],
        "error": row["error"], "updatedAt": row["updated_at"], "reservations": [dict(item) for item in reservations],
        "reviewSummary": review_summary,
    }


def get_plan(plan_id: str) -> dict[str, Any] | None:
    initialize()
    with _LOCK, _connect() as connection:
        plan = connection.execute("SELECT * FROM weekly_plans WHERE id = ?", (plan_id,)).fetchone()
        if plan is None:
            return None
        daily = connection.execute("SELECT * FROM daily_plans WHERE weekly_plan_id = ? ORDER BY run_date", (plan_id,)).fetchall()
        return {
            "id": plan["id"], "startDate": plan["week_start"], "weekStart": plan["week_start"],
            "durationDays": int(plan["duration_days"] or 7), "assetRoot": plan["asset_root"],
            "backgroundRoot": plan["background_root"], "templateDraftId": plan["template_draft_id"],
            "runAt": plan["run_at"], "active": bool(plan["active"]), "days": [_serialise_daily(connection, item) for item in daily],
        }


def list_plans() -> list[dict[str, Any]]:
    initialize()
    with _LOCK, _connect() as connection:
        ids = [str(row["id"]) for row in connection.execute("SELECT id FROM weekly_plans ORDER BY week_start DESC, created_at DESC")]
    return [plan for plan_id in ids if (plan := get_plan(plan_id)) is not None]


def create_plan(payload: Mapping[str, Any]) -> dict[str, Any]:
    initialize()
    week_start = _parse_date(str(payload.get("start_date") or payload.get("week_start") or ""))
    duration_days = _positive(payload.get("duration_days", 7), "持续天数", maximum=14)
    asset_root = str(payload.get("asset_root") or "").strip()
    background_root = str(payload.get("background_root") or "").strip()
    template_draft_id = str(payload.get("template_draft_id") or "").strip()
    if not asset_root or not background_root or not template_draft_id:
        raise ValueError("请提供菜品素材库、背景素材库和画布模板")
    if load_draft(template_draft_id) is None:
        raise ValueError("画布模板不存在；请先保存当前画布后再创建周计划")
    if not Path(background_root).expanduser().is_dir():
        raise ValueError("背景素材库路径不存在或不是文件夹")
    run_at = _parse_run_at(payload.get("run_at"))
    defaults = payload.get("defaults") if isinstance(payload.get("defaults"), Mapping) else {}
    days_raw = payload.get("days") if isinstance(payload.get("days"), list) else []
    by_date = {str(item.get("run_date")): item for item in days_raw if isinstance(item, Mapping)}
    plan_id = uuid.uuid4().hex
    now = _now()
    candidates = _library_candidates(asset_root)
    with _LOCK, _connect() as connection:
        connection.execute(
            "INSERT INTO weekly_plans (id, week_start, duration_days, asset_root, background_root, template_draft_id, run_at, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (plan_id, week_start.isoformat(), duration_days, asset_root, background_root, template_draft_id, run_at, now, now),
        )
        try:
            for offset in range(duration_days):
                run_date = week_start + timedelta(days=offset)
                source = by_date.get(run_date.isoformat(), defaults)
                candidate_count = _positive(source.get("candidate_count", 40), "候选片段数")
                video_count = _positive(source.get("video_count", 10), "成片数", maximum=30)
                clips_per_video = _positive(source.get("clips_per_video", 4), "每条成片片段数", maximum=8)
                counts = _normalize_counts(source.get("category_counts") if isinstance(source.get("category_counts"), Mapping) else {}, candidate_count)
                daily_id = uuid.uuid4().hex
                connection.execute(
                    "INSERT INTO daily_plans (id, weekly_plan_id, run_date, candidate_count, video_count, clips_per_video, category_counts, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (daily_id, plan_id, run_date.isoformat(), candidate_count, video_count, clips_per_video, json.dumps(counts, ensure_ascii=False), now),
                )
                selected = _allocate_candidates(candidates, candidate_count, counts, _reserved_keys(connection, run_date), random.Random(f"{plan_id}:{run_date}"))
                for item in selected:
                    connection.execute(
                        "INSERT INTO asset_reservations (id, daily_plan_id, run_date, dish_key, dish_name, category, food_type, visual_subject_type, image_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (uuid.uuid4().hex, daily_id, run_date.isoformat(), item["dish_key"], item["dish_name"], item["category"], item["food_type"], item["visual_subject_type"], random.Random(f"{plan_id}:{run_date}:{item['dish_key']}").choice(item["images"]), now),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return get_plan(plan_id) or {}


def update_daily_plan(daily_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Update an unstarted day, then reallocate this and later unstarted days."""
    initialize()
    with _LOCK, _connect() as connection:
        row = connection.execute("SELECT d.*, w.asset_root FROM daily_plans d JOIN weekly_plans w ON w.id = d.weekly_plan_id WHERE d.id = ?", (daily_id,)).fetchone()
        if row is None:
            raise ValueError("每日计划不存在")
        if row["status"] != "scheduled":
            raise ValueError("运行中或已完成的日期不能编辑")
        candidate_count = _positive(payload.get("candidate_count", row["candidate_count"]), "候选片段数")
        video_count = _positive(payload.get("video_count", row["video_count"]), "成片数", maximum=30)
        clips_per_video = _positive(payload.get("clips_per_video", row["clips_per_video"]), "每条成片片段数", maximum=8)
        raw_counts = payload.get("category_counts") if isinstance(payload.get("category_counts"), Mapping) else json.loads(row["category_counts"])
        counts = _normalize_counts(raw_counts, candidate_count)
        connection.execute("UPDATE daily_plans SET candidate_count=?, video_count=?, clips_per_video=?, category_counts=?, updated_at=? WHERE id=?", (candidate_count, video_count, clips_per_video, json.dumps(counts, ensure_ascii=False), _now(), daily_id))
        connection.execute("DELETE FROM asset_reservations WHERE daily_plan_id = ?", (daily_id,))
        candidates = _library_candidates(str(row["asset_root"]))
        run_date = _parse_date(str(row["run_date"]))
        selected = _allocate_candidates(candidates, candidate_count, counts, _edit_blocked_keys(connection, daily_id, run_date), random.Random(f"{daily_id}:{run_date}:edit"))
        for item in selected:
            connection.execute("INSERT INTO asset_reservations (id, daily_plan_id, run_date, dish_key, dish_name, category, food_type, visual_subject_type, image_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (uuid.uuid4().hex, daily_id, run_date.isoformat(), item["dish_key"], item["dish_name"], item["category"], item["food_type"], item["visual_subject_type"], random.choice(item["images"]), _now()))
        connection.commit()
        updated = connection.execute("SELECT * FROM daily_plans WHERE id = ?", (daily_id,)).fetchone()
        return _serialise_daily(connection, updated)


def _base_node(template: dict[str, Any], kind: str, fallback_id: str) -> dict[str, Any]:
    node = next((item for item in template.get("nodes", []) if item.get("data", {}).get("kind") == kind), None)
    if node is None:
        raise ValueError(f"画布模板缺少 {kind} 节点")
    copied = copy.deepcopy(node)
    copied["id"] = fallback_id
    return copied


def _create_daily_draft(connection: sqlite3.Connection, daily: sqlite3.Row, plan: sqlite3.Row) -> tuple[str, list[str]]:
    template = load_draft(str(plan["template_draft_id"]))
    if template is None:
        raise ValueError("画布模板已不存在")
    reservations = connection.execute("SELECT * FROM asset_reservations WHERE daily_plan_id = ? ORDER BY category, dish_name", (daily["id"],)).fetchall()
    if len(reservations) != int(daily["candidate_count"]):
        raise ValueError("当天素材预留不完整")
    draft_id = f"weekly_{daily['id']}"
    fixed_nodes = [_base_node(template, kind, node_id) for kind, node_id in (("output", "output"), ("sound", "sound"))]
    nodes = fixed_nodes
    edges: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    generator_ids: list[str] = []
    for index, reservation in enumerate(reservations, 1):
        base = index * 4
        input_node = _base_node(template, "input", f"weekly_input_{base}")
        process_node = _base_node(template, "image_process", f"weekly_process_{base + 1}")
        prompt_node = _base_node(template, "prompt", f"weekly_prompt_{base + 2}")
        generator_node = _base_node(template, "generator", f"weekly_generator_{base + 3}")
        source = Path(str(reservation["image_path"]))
        if not source.is_file():
            raise ValueError(f"预留素材已不存在：{reservation['dish_name']}")
        stored_name, image_url = asset_library._copy_into_draft(source, draft_id)
        backgrounds = asset_library._images(Path(str(plan["background_root"])).expanduser())
        if not backgrounds:
            raise ValueError("背景素材库中没有可用图片")
        background = asset_library._copy_background(random.choice(backgrounds))
        dish = str(reservation["dish_name"])
        category = str(reservation["category"])
        food_type = str(reservation["food_type"])
        visual = str(reservation["visual_subject_type"])
        asset_id = f"weekly_asset_{daily['id'][:8]}_{index:03d}"
        y = 80 + index * 170
        for node, x in ((input_node, 24), (process_node, 286), (prompt_node, 548), (generator_node, 810)):
            node["position"] = {"x": x, "y": y}
        input_node["data"].update({"assetId": asset_id, "title": dish, "dishName": dish, "sourceLibraryCategory": category, "dishCategory": category, "foodType": food_type, "visualSubjectType": visual, "imageName": source.name, "imagePreview": image_url, "status": "已就绪"})
        process_node["data"].update({"imagePreview": image_url, "visualSubjectType": visual, "processingMode": "preserve_original" if visual != asset_library.DEFAULT_VISUAL_SUBJECT_TYPE else "matting_composite", "backgroundTemplateId": background["id"], "backgroundTemplateName": background["name"], "backgroundPreview": background["url"], "status": "待处理"})
        config = dict(prompt_node["data"].get("promptConfig") or {})
        config["food_type"] = food_type
        config["visual_subject_type"] = visual
        prompt_node["data"].update({"title": f"{dish} 提示词", "promptConfig": config})
        generator_node["data"].update({"assetId": asset_id, "title": f"{dish} 视频片段", "status": "待生成", "duration": "3s", "resolution": "1080p"})
        nodes.extend((input_node, process_node, prompt_node, generator_node))
        edges.extend((
            {"id": f"{input_node['id']}-{process_node['id']}", "source": input_node["id"], "target": process_node["id"], "type": "smoothstep"},
            {"id": f"{process_node['id']}-{prompt_node['id']}", "source": process_node["id"], "target": prompt_node["id"], "type": "smoothstep"},
            {"id": f"{prompt_node['id']}-{generator_node['id']}", "source": prompt_node["id"], "target": generator_node["id"], "type": "smoothstep"},
            {"id": f"{generator_node['id']}-output", "source": generator_node["id"], "target": "output", "type": "smoothstep"},
        ))
        pending.append({"id": f"{generator_node['id']}_clip", "assetId": asset_id, "dish": dish, "label": "生成任务", "tone": "#355e62", "timelineDuration": 2.5, "sourceDurationSeconds": 3, "sourceStartSeconds": 0.5, "sourceEndSeconds": 3, "trimConfirmed": False, "dishCategory": category, "foodType": food_type, "status": "pending", "generatorNodeId": generator_node["id"], "isSelected": True})
        generator_ids.append(str(generator_node["id"]))
    workspace_count = int(daily["video_count"])
    payload = {
        "nodes": nodes, "edges": edges, "timeline": pending, "candidateClips": pending,
        "composeBatchCount": workspace_count, "composeClipCount": int(daily["clips_per_video"]),
        "composeWorkspaces": [{"id": f"compose_{index}", "title": f"成片 {index}", "clips": [], "job": None, "finalJob": None, "soundConfig": {"bgmName": template.get("bgmName", ""), "bgmUrl": template.get("bgmUrl", "")}} for index in range(1, workspace_count + 1)],
        "activeComposeWorkspaceId": "compose_1", "bgmName": template.get("bgmName", ""), "bgmUrl": template.get("bgmUrl", ""),
        "activePanel": "prompt", "nextNodeNumber": len(nodes) + 1,
    }
    save_draft(draft_id, payload)
    return draft_id, generator_ids


def _wait_for_image(draft_id: str, job_id: str, timeout_seconds: int = 900) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        job = get_image_processing_job(draft_id, job_id)
        if job and job.get("status") == "done":
            return True
        if not job or job.get("status") == "error":
            return False
        time.sleep(1)
    return False


def _launch_daily_run(daily_id: str) -> None:
    try:
        with _LOCK, _connect() as connection:
            daily = connection.execute("SELECT d.*, w.asset_root, w.background_root, w.template_draft_id FROM daily_plans d JOIN weekly_plans w ON w.id=d.weekly_plan_id WHERE d.id=?", (daily_id,)).fetchone()
            if daily is None or daily["status"] != "scheduled":
                return
            draft_id, generator_ids = _create_daily_draft(connection, daily, daily)
            connection.execute("UPDATE daily_plans SET status='processing_images', draft_id=?, started_at=?, updated_at=? WHERE id=?", (draft_id, _now(), _now(), daily_id))
            connection.commit()
        for generator_id in generator_ids:
            process_id = generator_id.replace("generator", "process")
            job = start_image_processing(draft_id, process_id)
            if not _wait_for_image(draft_id, str(job["job_id"])):
                raise RuntimeError(f"图片处理失败：{generator_id}")
            generation = start_generation(draft_id, generator_id)
            latest = load_draft(draft_id)
            if latest is not None:
                for node in latest.get("nodes", []):
                    if node.get("id") == generator_id:
                        node.setdefault("data", {})["generationJobId"] = generation["job_id"]
                        break
                save_draft(draft_id, latest)
        with _LOCK, _connect() as connection:
            connection.execute("UPDATE daily_plans SET status='generating', updated_at=? WHERE id=?", (_now(), daily_id))
            connection.commit()
    except Exception as exc:
        with _LOCK, _connect() as connection:
            connection.execute("UPDATE daily_plans SET status='error', error=?, updated_at=? WHERE id=?", (str(exc), _now(), daily_id))
            connection.commit()


def _refresh_generating_runs() -> None:
    with _LOCK, _connect() as connection:
        running = connection.execute("SELECT * FROM daily_plans WHERE status='generating' AND draft_id IS NOT NULL").fetchall()
        for daily in running:
            draft = load_draft(str(daily["draft_id"]))
            if draft is None:
                continue
            jobs = [get_generation_job(str(daily["draft_id"]), str(node.get("data", {}).get("generationJobId") or "")) for node in draft.get("nodes", []) if node.get("data", {}).get("kind") == "generator"]
            # The node holds a generationJobId only after submission; a missing
            # ID means the launcher has not yet reached the node.
            if not jobs or any(job is None or job.get("status") not in {"done", "error"} for job in jobs):
                continue
            status = "review" if any(job.get("status") == "done" for job in jobs if job) else "error"
            connection.execute("UPDATE daily_plans SET status=?, updated_at=? WHERE id=?", (status, _now(), daily["id"]))
        connection.commit()


def run_due_plans() -> int:
    initialize()
    now = datetime.now(ZoneInfo(WEEKLY_PLAN_TIMEZONE))
    today = now.date().isoformat()
    current_time = now.strftime("%H:%M")
    with _LOCK, _connect() as connection:
        due = connection.execute("SELECT d.id FROM daily_plans d JOIN weekly_plans w ON w.id=d.weekly_plan_id WHERE w.active=1 AND d.status='scheduled' AND d.run_date=? AND w.run_at <= ?", (today, current_time)).fetchall()
    for row in due:
        threading.Thread(target=_launch_daily_run, args=(str(row["id"]),), name=f"weekly-run-{str(row['id'])[:8]}", daemon=True).start()
    _refresh_generating_runs()
    return len(due)


def start_scheduler() -> None:
    global _SCHEDULER_STARTED
    if _SCHEDULER_STARTED:
        return
    _SCHEDULER_STARTED = True
    _SCHEDULER_STOP.clear()
    def worker() -> None:
        while not _SCHEDULER_STOP.wait(20):
            try:
                run_due_plans()
            except Exception:
                # Request logging is unavailable in this low-level service; the
                # next wakeup retries safe due-plan discovery.
                pass
    threading.Thread(target=worker, name="weekly-plan-scheduler", daemon=True).start()
    run_due_plans()


def stop_scheduler() -> None:
    global _SCHEDULER_STARTED
    _SCHEDULER_STOP.set()
    _SCHEDULER_STARTED = False


def get_daily_by_draft(draft_id: str) -> dict[str, Any] | None:
    initialize()
    with _LOCK, _connect() as connection:
        row = connection.execute("SELECT * FROM daily_plans WHERE draft_id = ?", (draft_id,)).fetchone()
        return _serialise_daily(connection, row) if row else None


def save_clip_review(daily_id: str, clip_id: str, decision: str, source_start: Any = None, source_end: Any = None) -> dict[str, Any]:
    if decision not in {"approved", "rejected"}:
        raise ValueError("审核结果仅支持 approved 或 rejected")
    initialize()
    with _LOCK, _connect() as connection:
        daily = connection.execute("SELECT * FROM daily_plans WHERE id=?", (daily_id,)).fetchone()
        if daily is None or not daily["draft_id"]:
            raise ValueError("片段审核任务不存在")
        draft = load_draft(str(daily["draft_id"]))
        clip = next((item for item in (draft or {}).get("candidateClips", []) if item.get("id") == clip_id and item.get("sourcePath")), None)
        if clip is None:
            raise ValueError("待审片段不存在或尚未生成完成")
        start = max(0.0, float(source_start)) if source_start is not None else float(clip.get("sourceStartSeconds") or 0)
        end = max(start + 0.1, float(source_end)) if source_end is not None else float(clip.get("sourceEndSeconds") or clip.get("sourceDurationSeconds") or 3)
        connection.execute("INSERT INTO clip_reviews (id, daily_plan_id, clip_id, decision, source_start, source_end, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(daily_plan_id, clip_id) DO UPDATE SET decision=excluded.decision, source_start=excluded.source_start, source_end=excluded.source_end, updated_at=excluded.updated_at", (uuid.uuid4().hex, daily_id, clip_id, decision, start, end, _now()))
        for collection in ("candidateClips", "timeline"):
            draft[collection] = [{**item, "reviewStatus": decision, "sourceStartSeconds": start, "sourceEndSeconds": end, "trimConfirmed": decision == "approved"} if item.get("id") == clip_id else item for item in draft.get(collection, [])]
        save_draft(str(daily["draft_id"]), draft)
        connection.commit()
        updated = connection.execute("SELECT * FROM daily_plans WHERE id=?", (daily_id,)).fetchone()
        return _serialise_daily(connection, updated)


def assert_ready_for_compose(draft_id: str) -> None:
    daily = get_daily_by_draft(draft_id)
    if daily is None:
        return
    draft = load_draft(draft_id) or {}
    completed = [clip for clip in draft.get("candidateClips", []) if clip.get("sourcePath")]
    decisions = int(daily["reviewSummary"].get("approved", 0)) + int(daily["reviewSummary"].get("rejected", 0))
    if not completed or decisions < len(completed):
        raise ValueError("请先完成所有已生成候选片段的人工审核，再合成无声成片")
    if int(daily["reviewSummary"].get("approved", 0)) < int(daily["clipsPerVideo"]):
        raise ValueError("审核通过的片段少于每条成片所需片段数，请补生成或调整计划")
