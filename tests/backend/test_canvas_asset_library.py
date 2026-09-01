import json
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from web.services import canvas_asset_library, canvas_state


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


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


def test_traditional_chinese_food_names_are_normalized_before_matching():
    result = canvas_asset_library.classify_library_name("青花魚壽司")

    assert result["category"] == "寿司"
    assert result["reviewRequired"] is False


def test_sushi_product_name_wins_over_ingredient_keywords():
    for name in ("青鱼天妇罗寿司", "柚子胡椒左口鱼寿司", "柚子胡椒金鲷壽司"):
        result = canvas_asset_library.classify_library_name(name)
        assert result["category"] == "寿司"
        assert result["reviewRequired"] is False


def test_batch_classification_prefers_qwen_when_configured(monkeypatch):
    names = ["ramen-special", "seasonal-dessert"]
    content = json.dumps({
        "items": [
            {"dish_name": names[0], "category": canvas_asset_library.ASSET_CATEGORIES[4], "confidence": 0.96, "reason": "面食"},
            {"dish_name": names[1], "category": canvas_asset_library.ASSET_CATEGORIES[6], "confidence": 0.94, "reason": "甜点"},
        ],
    }, ensure_ascii=False)
    body = json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False).encode()
    monkeypatch.setattr(canvas_asset_library, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(canvas_asset_library, "QWEN_LLM_ENABLED", True)
    monkeypatch.setattr(canvas_asset_library, "QWEN_LLM_BASE_URL", "https://example.invalid/v1")

    with patch.object(canvas_asset_library.urllib.request, "urlopen", return_value=_Response(body)) as urlopen:
        result, mode, warning = canvas_asset_library.classify_library_names(names)

    assert mode == "qwen"
    assert warning is None
    assert result[names[0]]["category"] == canvas_asset_library.ASSET_CATEGORIES[4]
    assert result[names[0]]["reviewRequired"] is False
    assert urlopen.call_args.args[0].full_url.endswith("/v1/chat/completions")


def test_invalid_batch_classification_falls_back_to_local(monkeypatch):
    names = ["unknown-dish"]
    content = json.dumps({"items": [{"dish_name": "renamed-dish", "category": canvas_asset_library.ASSET_CATEGORIES[4], "confidence": 0.99}]}, ensure_ascii=False)
    body = json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False).encode()
    monkeypatch.setattr(canvas_asset_library, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(canvas_asset_library, "QWEN_LLM_ENABLED", True)

    with patch.object(canvas_asset_library.urllib.request, "urlopen", return_value=_Response(body)):
        result, mode, warning = canvas_asset_library.classify_library_names(names)

    assert mode == "local_fallback"
    assert warning
    assert result[names[0]]["category"] == canvas_asset_library.classify_library_name(names[0])["category"]


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


def test_asset_library_finds_nested_dish_folders_from_parent_root(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_asset_library, "QWEN_API_KEY", "")
    monkeypatch.setattr(canvas_asset_library, "CANVAS_BACKGROUND_ROOT", tmp_path / "backgrounds")
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    asset_root = tmp_path / "library-root"
    background_root = tmp_path / "background-source"
    _write_image(asset_root / "brand" / "寿司" / "三文鱼寿司" / "dish.png", "#d97979")
    _write_image(asset_root / "brand" / "甜品" / "抹茶布丁" / "dish.png", "#e3c36f")
    _write_image(asset_root / "archive-a" / "神秘菜" / "dish.png", "#7aa879")
    _write_image(asset_root / "archive-b" / "神秘菜" / "dish.png", "#7aa879")
    _write_image(background_root / "wood.png", "#806040")

    plan = canvas_asset_library.build_asset_plan(
        "nested",
        str(asset_root),
        str(background_root),
        {"寿司": 1, "甜品": 0},
    )

    assert len(plan["selected"]) == 1
    assert plan["selected"][0]["dishName"] == "三文鱼寿司"
    assert plan["selected"][0]["sourceCategory"] == "寿司"
    assert len(plan["reviewItems"]) == 1
    assert plan["reviewItems"][0]["dishName"] == "神秘菜"
    assert plan["reviewItems"][0]["folderCount"] == 2
