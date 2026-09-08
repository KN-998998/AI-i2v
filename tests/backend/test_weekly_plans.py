from __future__ import annotations

import sqlite3
from pathlib import Path

from PIL import Image

from web.services import canvas_state, weekly_plans


def _image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 32), "#cc7755").save(path)


def _template() -> dict:
    return {
        "nodes": [
            {"id": "assets", "type": "workflow", "position": {"x": 0, "y": 0}, "data": {"kind": "input"}},
            {"id": "image_process", "type": "workflow", "position": {"x": 0, "y": 0}, "data": {"kind": "image_process"}},
            {"id": "prompt", "type": "workflow", "position": {"x": 0, "y": 0}, "data": {"kind": "prompt", "promptConfig": {}}},
            {"id": "clips", "type": "workflow", "position": {"x": 0, "y": 0}, "data": {"kind": "generator"}},
            {"id": "output", "type": "workflow", "position": {"x": 0, "y": 0}, "data": {"kind": "output"}},
            {"id": "sound", "type": "workflow", "position": {"x": 0, "y": 0}, "data": {"kind": "sound"}},
        ],
        "edges": [], "timeline": [], "candidateClips": [], "composeWorkspaces": [], "bgmName": "", "bgmUrl": "",
    }


def test_existing_weekly_plan_database_adds_duration_days(monkeypatch, tmp_path):
    database = tmp_path / "weekly.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("""
            CREATE TABLE weekly_plans (
                id TEXT PRIMARY KEY,
                week_start TEXT NOT NULL,
                asset_root TEXT NOT NULL,
                background_root TEXT NOT NULL,
                template_draft_id TEXT NOT NULL,
                run_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
    monkeypatch.setattr(weekly_plans, "WEEKLY_PLAN_DB", database)

    weekly_plans.initialize()

    with weekly_plans._connect() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(weekly_plans)")}
    assert "duration_days" in columns


def test_weekly_plan_reserves_dish_folders_without_three_day_repeats(monkeypatch, tmp_path):
    monkeypatch.setattr(weekly_plans, "WEEKLY_PLAN_DB", tmp_path / "weekly.sqlite3")
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    asset_root = tmp_path / "assets"
    background_root = tmp_path / "backgrounds"
    _image(background_root / "bg.png")
    for index in range(120):
        _image(asset_root / "寿司" / f"寿司{index:03d}" / "source.png")
    canvas_state.save_draft("template", _template())

    plan = weekly_plans.create_plan({
        "start_date": "2026-09-09", "duration_days": 7, "asset_root": str(asset_root), "background_root": str(background_root),
        "template_draft_id": "template", "run_at": "09:00",
        "defaults": {"candidate_count": 40, "video_count": 10, "clips_per_video": 4, "category_counts": {}},
    })

    assert len(plan["days"]) == 7
    assert plan["startDate"] == "2026-09-09"
    assert plan["durationDays"] == 7
    assert all(len(day["reservations"]) == 40 for day in plan["days"])
    selected = [{item["dish_key"] for item in day["reservations"]} for day in plan["days"]]
    for index in range(1, len(selected)):
        assert not selected[index].intersection(selected[index - 1])
    for index in range(2, len(selected)):
        assert not selected[index].intersection(selected[index - 2])
    assert selected[0].intersection(selected[3])


def test_daily_plan_rejects_edit_after_execution_has_started(monkeypatch, tmp_path):
    monkeypatch.setattr(weekly_plans, "WEEKLY_PLAN_DB", tmp_path / "weekly.sqlite3")
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    asset_root = tmp_path / "assets"
    background_root = tmp_path / "backgrounds"
    _image(background_root / "bg.png")
    for index in range(6):
        _image(asset_root / "寿司" / f"寿司{index}" / "source.png")
    canvas_state.save_draft("template", _template())
    plan = weekly_plans.create_plan({
        "start_date": "2026-09-09", "duration_days": 3, "asset_root": str(asset_root), "background_root": str(background_root),
        "template_draft_id": "template", "run_at": "09:00",
        "defaults": {"candidate_count": 2, "video_count": 1, "clips_per_video": 2, "category_counts": {}},
    })
    assert len(plan["days"]) == 3
    first_day = plan["days"][0]
    with weekly_plans._connect() as connection:
        connection.execute("UPDATE daily_plans SET status='generating' WHERE id=?", (first_day["id"],))
    try:
        weekly_plans.update_daily_plan(first_day["id"], {"candidate_count": 2, "video_count": 1, "clips_per_video": 2, "category_counts": {}})
    except ValueError as exc:
        assert "不能编辑" in str(exc)
    else:
        raise AssertionError("started daily plan unexpectedly accepted an edit")
