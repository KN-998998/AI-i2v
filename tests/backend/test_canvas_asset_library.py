from pathlib import Path

from PIL import Image

from web.services import canvas_asset_library, canvas_state


def _write_image(path: Path, color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 120), color).save(path, "PNG")


def test_classification_surfaces_compound_names_for_review_and_remembers_rules(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_asset_library, "_RULES_PATH", tmp_path / "rules.json")

    staple = canvas_asset_library.classify_library_name("天妇罗乌冬")
    assert staple["category"] == "主食"
    assert staple["reviewRequired"] is False

    combination = canvas_asset_library.classify_library_name("刺身定食")
    assert combination["reviewRequired"] is True
    assert combination["category"] == "刺身"

    canvas_asset_library.save_category_rule("刺身定食", "主菜")
    remembered = canvas_asset_library.classify_library_name("刺身定食")
    assert remembered["category"] == "主菜"
    assert remembered["reviewRequired"] is False


def test_infer_library_category_supports_common_multilingual_names():
    cases = {
        "サーモン刺身": "刺身",
        "Tuna Sushi": "寿司",
        "天ぷら盛り合わせ": "主菜",
        "味噌ラーメン": "主食",
        "抹茶ラテ": "饮品",
        "葡萄酒": "饮品",
        "フルーツ盛り": "水果",
        "草莓大福": "甜品",
        "茶碗蒸し": "前菜/小菜",
    }
    for name, expected in cases.items():
        assert canvas_asset_library.infer_library_category(name) == expected


def test_asset_library_selects_by_category_and_copies_files(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    monkeypatch.setattr(canvas_asset_library, "CANVAS_BACKGROUND_ROOT", tmp_path / "backgrounds")
    asset_root = tmp_path / "鮨政exp"
    background_root = tmp_path / "backgrounds-source"
    _write_image(asset_root / "寿司-三文鱼" / "dish.png", "#d97979")
    _write_image(asset_root / "甜品-布丁" / "dish.png", "#e3c36f")
    _write_image(asset_root / "季节限定" / "dish.png", "#7aa879")
    _write_image(background_root / "wood.png", "#806040")

    plan = canvas_asset_library.build_asset_plan(
        "default",
        str(asset_root),
        str(background_root),
        {"寿司": 1, "甜品": "1", "刺身": "invalid"},
    )

    assert {item["sourceCategory"] for item in plan["selected"]} == {"寿司", "甜品"}
    assert {item["dishName"] for item in plan["reviewItems"]} == {"季节限定"}
    assert plan["categoryCounts"]["刺身"] == 0
    for item in plan["selected"]:
        assert (canvas_state.draft_directory("default") / "files" / item["storedName"]).is_file()
        assert (tmp_path / "backgrounds" / item["background"]["id"]).is_file()
