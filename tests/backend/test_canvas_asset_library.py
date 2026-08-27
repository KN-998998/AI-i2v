from pathlib import Path

from PIL import Image

from web.services import canvas_asset_library, canvas_state


def _write_image(path: Path, color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 120), color).save(path, "PNG")


def test_asset_library_selects_by_category_and_copies_files(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    monkeypatch.setattr(canvas_asset_library, "CANVAS_BACKGROUND_ROOT", tmp_path / "backgrounds")
    asset_root = tmp_path / "鮨政exp"
    background_root = tmp_path / "backgrounds-source"
    _write_image(asset_root / "寿司-三文鱼" / "dish.png", "#d97979")
    _write_image(asset_root / "甜品-布丁" / "dish.png", "#e3c36f")
    _write_image(background_root / "wood.png", "#806040")

    plan = canvas_asset_library.build_asset_plan(
        "default",
        str(asset_root),
        str(background_root),
        {"寿司": 1, "甜品": "1", "刺身": "invalid"},
    )

    assert {item["sourceCategory"] for item in plan["selected"]} == {"寿司", "甜品"}
    assert plan["categoryCounts"]["刺身"] == 0
    for item in plan["selected"]:
        assert (canvas_state.draft_directory("default") / "files" / item["storedName"]).is_file()
        assert (tmp_path / "backgrounds" / item["background"]["id"]).is_file()
