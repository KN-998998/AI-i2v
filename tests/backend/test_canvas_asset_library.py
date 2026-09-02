import json
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import pytest

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

    canvas_asset_library.save_category_rule("刺身定食", "主菜", "热食")
    remembered = canvas_asset_library.classify_library_name("刺身定食")
    assert remembered["category"] == "主菜"
    assert remembered["reviewRequired"] is False


def test_category_rules_can_be_listed_for_management(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_asset_library, "_RULES_PATH", tmp_path / "rules.json")

    canvas_asset_library.save_category_rule("烤龙虾", "主菜", "热食")
    canvas_asset_library.save_category_rule("角切鱼生饭", "主食", "热食")

    assert canvas_asset_library.list_category_rules() == [
        {"dishName": "烤龙虾", "category": "主菜", "foodType": "热食"},
        {"dishName": "角切鱼生饭", "category": "主食", "foodType": "热食"},
    ]


def test_category_rule_requires_food_type_except_for_dessert_and_fruit(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_asset_library, "_RULES_PATH", tmp_path / "rules.json")

    with pytest.raises(ValueError, match="冷食或热食"):
        canvas_asset_library.save_category_rule("烤龙虾", "主菜")

    saved = canvas_asset_library.save_category_rule("蜜瓜", "水果")
    assert saved["foodType"] == "冷食"


def test_legacy_category_rule_without_food_type_requires_review(monkeypatch, tmp_path):
    rules_path = tmp_path / "rules.json"
    monkeypatch.setattr(canvas_asset_library, "_RULES_PATH", rules_path)
    rules_path.write_text(json.dumps({"烤龙虾": "主菜"}, ensure_ascii=False), encoding="utf-8")

    result = canvas_asset_library.classify_library_name("烤龙虾")

    assert result["category"] == "主菜"
    assert result["foodType"] is None
    assert result["reviewRequired"] is True


def test_infer_library_category_supports_common_multilingual_names():
    cases = {
        "サーモン刺身": "刺身",
        "Tuna Sushi": "寿司",
        "天ぷら盛り合わせ": "炸物",
        "味噌ラーメン": "主食",
        "抹茶ラテ": "饮品",
        "葡萄酒": "饮品",
        "フルーツ盛り": "水果",
        "草莓大福": "甜品",
        "茶碗蒸し": "前菜/小菜",
    }
    for name, expected in cases.items():
        assert canvas_asset_library.infer_library_category(name) == expected


def test_fried_dishes_use_the_dedicated_fried_category():
    for name in ("天妇罗虾", "炸鸡", "唐揚げ", "炸猪排"):
        result = canvas_asset_library.classify_library_name(name)
        assert result["category"] == "炸物"
        assert result["foodType"] == "热食"


def test_traditional_chinese_food_names_are_normalized_before_matching():
    result = canvas_asset_library.classify_library_name("青花魚壽司")

    assert result["category"] == "寿司"
    assert result["reviewRequired"] is False
    assert canvas_asset_library.simplify_dish_name("鹽烤左口魚") == "盐烤左口鱼"
    assert canvas_asset_library._searchable_name("鹽烤左口魚") == canvas_asset_library._searchable_name("盐烤左口鱼")


def test_batch_classification_uses_one_canonical_name_for_traditional_aliases(monkeypatch):
    names = ["青花魚壽司", "青花鱼寿司"]
    content = json.dumps({
        "items": [{"dish_name": "青花鱼寿司", "category": "寿司", "confidence": 0.98, "reason": "寿司成品词"}],
    }, ensure_ascii=False)
    body = json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False).encode()
    monkeypatch.setattr(canvas_asset_library, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(canvas_asset_library, "QWEN_LLM_ENABLED", True)

    with patch.object(canvas_asset_library.urllib.request, "urlopen", return_value=_Response(body)) as urlopen:
        result, mode, warning = canvas_asset_library.classify_library_names(names)

    assert mode == "qwen"
    assert warning is None
    assert result[names[0]]["category"] == result[names[1]]["category"] == "寿司"
    request_payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert json.loads(request_payload["messages"][1]["content"])["dish_names"] == ["青花鱼寿司"]


def test_sushi_product_name_wins_over_ingredient_keywords():
    for name in ("青鱼天妇罗寿司", "柚子胡椒左口鱼寿司", "柚子胡椒金鲷壽司"):
        result = canvas_asset_library.classify_library_name(name)
        assert result["category"] == "寿司"
        assert result["reviewRequired"] is False


def test_seared_sushi_is_hot_food_but_regular_sushi_remains_cold():
    for name in ("火炙鹅肝金枪鱼寿司", "炙烧三文鱼寿司", "炙烤和牛寿司", "炙りサーモン寿司"):
        result = canvas_asset_library.classify_library_name(name)
        assert result["category"] == "寿司"
        assert result["foodType"] == "热食"

    regular = canvas_asset_library.classify_library_name("青花鱼寿司")
    assert regular["category"] == "寿司"
    assert regular["foodType"] == "冷食"


def test_qwen_sushi_food_type_respects_searing_process():
    assert canvas_asset_library.infer_food_type("炙烧三文鱼寿司", "寿司") == "热食"
    assert canvas_asset_library.infer_food_type("三文鱼寿司", "寿司") == "冷食"


def test_saved_cold_rule_cannot_override_a_hot_preparation(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_asset_library, "_RULES_PATH", tmp_path / "rules.json")
    canvas_asset_library.save_category_rule("火炙三文鱼寿司", "寿司", "冷食")

    result = canvas_asset_library.classify_library_name("火炙三文鱼寿司")

    assert result["category"] == "寿司"
    assert result["foodType"] == "热食"


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
    assert len(plan["classificationResults"]) == 3
    assert {item["dishName"] for item in plan["classificationResults"]} == {"寿司-三文鱼", "甜品-布丁", "季节限定"}
    assert next(item for item in plan["classificationResults"] if item["dishName"] == "寿司-三文鱼")["classificationSource"] == "本地规则"
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


def test_asset_library_classification_scan_returns_all_dishes_without_copying(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_asset_library, "_RULES_PATH", tmp_path / "rules.json")
    monkeypatch.setattr(canvas_asset_library, "QWEN_API_KEY", "")
    asset_root = tmp_path / "library-root"
    _write_image(asset_root / "寿司" / "三文鱼寿司" / "dish.png", "#d97979")
    _write_image(asset_root / "主菜" / "烤龙虾" / "dish.png", "#806040")
    _write_image(asset_root / "archive" / "神秘菜" / "dish.png", "#7aa879")

    result = canvas_asset_library.scan_asset_classifications(str(asset_root))

    assert len(result["classificationResults"]) == 3
    assert {item["dishName"] for item in result["classificationResults"]} == {"三文鱼寿司", "烤龙虾", "神秘菜"}
    assert next(item for item in result["classificationResults"] if item["dishName"] == "三文鱼寿司")["classificationSource"] == "本地规则"
    assert next(item for item in result["classificationResults"] if item["dishName"] == "神秘菜")["reviewRequired"] is True


def test_asset_library_merges_simplified_and_traditional_duplicate_folders(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_asset_library, "_RULES_PATH", tmp_path / "rules.json")
    monkeypatch.setattr(canvas_asset_library, "QWEN_API_KEY", "")
    monkeypatch.setattr(canvas_asset_library, "CANVAS_BACKGROUND_ROOT", tmp_path / "backgrounds")
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    asset_root = tmp_path / "library-root"
    background_root = tmp_path / "background-source"
    _write_image(asset_root / "烤鱼" / "simplified.png", "#d97979")
    _write_image(asset_root / "烤魚" / "traditional.png", "#4c4265")
    _write_image(background_root / "wood.png", "#806040")

    plan = canvas_asset_library.build_asset_plan(
        "aliases",
        str(asset_root),
        str(background_root),
        {"主菜": 2},
    )

    assert len(plan["selected"]) == 1
    assert plan["selected"][0]["dishName"] == "烤鱼"
    assert plan["selected"][0]["sourceFolderCount"] == 2
    assert set(plan["selected"][0]["sourceNames"]) == {"烤鱼", "烤魚"}
    assert any("主菜 只找到 1 个不同菜品" in warning for warning in plan["warnings"])


def test_manual_asset_review_scans_without_classification_and_organizes_after_confirmation(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_asset_library, "_MANUAL_REVIEW_ROOT", tmp_path / "review-scans")
    asset_root = tmp_path / "raw"
    target_root = tmp_path / "图片素材库"
    first = asset_root / "寿司" / "青花魚壽司"
    second = asset_root / "archive" / "青花鱼寿司"
    _write_image(first / "a.png", "#d97979")
    _write_image(second / "b.png", "#4c4265")
    monkeypatch.setattr(canvas_asset_library, "classify_library_names", lambda _names: (_ for _ in ()).throw(AssertionError("manual scan must not classify")))

    scan = canvas_asset_library.scan_manual_asset_library(str(asset_root))

    assert len(scan["items"]) == 1
    item = scan["items"][0]
    assert item["folderCount"] == 2
    with pytest.raises(ValueError, match="完成所有菜品"):
        canvas_asset_library.organize_manual_asset_library(scan["scanId"], str(target_root), [])

    result = canvas_asset_library.organize_manual_asset_library(scan["scanId"], str(target_root), [{
        "dishKey": item["dishKey"], "category": "寿司", "foodType": "冷食",
    }])

    assert result["dishCount"] == 1
    assert result["imageCount"] == 2
    assert (target_root / "寿司" / "青花鱼寿司" / "a.png").is_file()
    assert (target_root / "寿司" / "青花鱼寿司" / "b.png").is_file()
    assert (first / "a.png").is_file()
