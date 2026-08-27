"""Build reviewable canvas workflows from a folder-based dish library."""
from __future__ import annotations

import json
import random
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Mapping

from web.services.canvas_state import CANVAS_BACKGROUND_ROOT, draft_directory

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ASSET_CATEGORIES = ("寿司", "刺身", "前菜/小菜", "主菜", "主食", "汤品", "甜品", "水果", "饮品", "其他")
_RULES_PATH = CANVAS_BACKGROUND_ROOT.parent / "canvas_asset_category_rules.json"
_RULES_LOCK = threading.RLock()

_CATEGORY_KEYWORDS = {
    "寿司": ("寿司", "卷寿司", "手卷", "握寿司", "军舰", "卷物", "巻き寿司", "握り", "にぎり", "軍艦", "手巻き", "ちらし寿司", "押し寿司", "稲荷寿司", "すし", "sushi"),
    "刺身": ("刺身", "生鱼片", "生鱼", "海鲜刺身", "お造り", "造り", "sashimi", "刺し身"),
    "前菜/小菜": ("前菜", "小菜", "开胃菜", "开胃", "沙拉", "色拉", "毛豆", "玉子烧", "茶碗蒸し", "冷菜", "凉菜", "泡菜", "腌菜", "配菜", "下酒菜", "小吃", "先付", "お通し", "おつまみ", "サラダ", "枝豆", "だし巻き", "冷奴", "appetizer", "side dish"),
    "主菜": ("主菜", "烧鸟", "烤鱼", "烤肉", "牛排", "天妇罗", "炸物", "唐扬", "炸鸡", "煮物", "锅物", "火锅", "鳗鱼", "猪排", "炸猪排", "焼き鳥", "焼魚", "天ぷら", "揚げ", "唐揚げ", "とんかつ", "うなぎ", "ステーキ", "主菜", "main dish", "entree"),
    "主食": ("主食", "米饭", "炒饭", "拉面", "乌冬", "荞麦", "面条", "盖饭", "饭团", "炒面", "ご飯", "ライス", "チャーハン", "ラーメン", "うどん", "そば", "麺", "丼", "おにぎり", "焼きそば", "rice", "noodle", "donburi"),
    "汤品": ("汤品", "味噌汤", "味噌汁", "清汤", "浓汤", "海鲜汤", "汤羹", "お吸い物", "潮汁", "豚汁", "スープ", "soup"),
    "甜品": ("甜品", "甜点", "饭后甜点", "蛋糕", "布丁", "冰淇淋", "雪糕", "慕斯", "奶油", "大福", "和果子", "可丽露", "马卡龙", "巧克力", "果冻", "芭菲", "パフェ", "和菓子", "どら焼き", "羊羹", "アイス", "デザート", "dessert", "cake", "pudding", "ice cream", "gelato", "sorbet"),
    # Beverage is checked before fruit so names such as grape wine are not classified as fruit.
    "饮品": ("饮品", "饮料", "酒水", "清酒", "日本酒", "啤酒", "威士忌", "葡萄酒", "红酒", "白酒", "梅酒", "烧酒", "高球", "茶饮", "绿茶", "乌龙茶", "红茶", "抹茶", "咖啡", "果汁", "汽水", "苏打", "饮用水", "ドリンク", "日本酒", "ビール", "ワイン", "焼酎", "梅酒", "ハイボール", "お茶", "抹茶", "コーヒー", "ジュース", "drink", "beverage", "sake", "beer", "wine", "coffee", "juice"),
    "水果": ("水果", "鲜果", "果盘", "草莓", "西瓜", "芒果", "葡萄", "苹果", "柠檬", "橙子", "橙", "桃", "梨", "蓝莓", "樱桃", "菠萝", "凤梨", "香蕉", "柚子", "柑橘", "いちご", "苺", "すいか", "ぶどう", "りんご", "みかん", "フルーツ", "fruit", "strawberry", "watermelon", "mango", "grape", "apple", "lemon", "orange", "peach", "banana"),
}


def _searchable_name(value: str) -> str:
    return re.sub(r"[\s_\-—–/\\·・]+", "", value.casefold())


def _load_category_rules() -> dict[str, str]:
    if not _RULES_PATH.is_file():
        return {}
    try:
        payload = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(key): str(value) for key, value in payload.items() if str(value) in ASSET_CATEGORIES} if isinstance(payload, dict) else {}


def save_category_rule(dish_name: str, category: str) -> dict[str, str]:
    normalized_name = _searchable_name(dish_name)
    if not normalized_name:
        raise ValueError("菜品名称不能为空")
    if category not in ASSET_CATEGORIES:
        raise ValueError("不支持的菜品分类")
    with _RULES_LOCK:
        rules = _load_category_rules()
        rules[normalized_name] = category
        _RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = _RULES_PATH.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(_RULES_PATH)
    return {"dishName": dish_name, "category": category}


def _category_candidates(dish_name: str) -> list[str]:
    name = _searchable_name(dish_name)
    return [category for category, keywords in _CATEGORY_KEYWORDS.items() if any(_searchable_name(keyword) in name for keyword in keywords)]


def classify_library_name(dish_name: str) -> dict[str, Any]:
    normalized_name = _searchable_name(dish_name)
    rules = _load_category_rules()
    if normalized_name in rules:
        category = rules[normalized_name]
        return {"category": category, "candidates": [category], "reviewRequired": False, "reason": "已使用人工确认规则"}

    name = normalized_name
    candidates = _category_candidates(dish_name)
    # These describe a package or a serving format, not one dish category.
    combination_words = ("定食", "套餐", "拼盘", "拼盤", "盛合", "盛り合わせ", "组合", "組み合わせ", "set", "combo", "platter", "assortment")
    is_combination = any(_searchable_name(word) in name for word in combination_words)

    # The finished product wins over a preparation or topping word. This makes
    # 天妇罗乌冬 a staple, while 天妇罗拼盘 remains a main dish review case.
    staple_words = ("乌冬", "拉面", "荞麦", "面条", "炒面", "盖饭", "饭团", "米饭", "丼", "うどん", "ラーメン", "そば", "麺", "丼", "ご飯", "おにぎり", "noodle", "donburi", "rice")
    dessert_words = ("冰淇淋", "雪糕", "蛋糕", "布丁", "甜点", "甜品", "大福", "パフェ", "アイス", "デザート", "cake", "pudding", "ice cream", "gelato", "dessert")
    beverage_words = ("拿铁", "奶茶", "咖啡", "茶饮", "绿茶", "乌龙茶", "红茶", "果汁", "酒", "啤酒", "清酒", "饮料", "ラテ", "コーヒー", "ドリンク", "sake", "beer", "wine", "coffee", "juice")
    if not is_combination and any(_searchable_name(word) in name for word in dessert_words):
        candidates = ["甜品"]
    elif not is_combination and any(_searchable_name(word) in name for word in beverage_words):
        candidates = ["饮品"]
    elif not is_combination and any(_searchable_name(word) in name for word in staple_words):
        candidates = ["主食"]

    if is_combination or len(candidates) > 1 or not candidates:
        suggested = candidates[0] if len(candidates) == 1 else "其他"
        reason = "组合菜名，需确认成品主体" if is_combination else "名称命中多个分类" if len(candidates) > 1 else "未匹配到分类词"
        return {"category": suggested, "candidates": candidates, "reviewRequired": True, "reason": reason}
    return {"category": candidates[0], "candidates": candidates, "reviewRequired": False, "reason": "本地规则匹配"}


def infer_library_category(dish_name: str) -> str:
    return str(classify_library_name(dish_name)["category"])


def infer_food_type(dish_name: str, category: str) -> str:
    if category in {"刺身", "前菜/小菜", "甜品", "水果", "饮品"} or any(word in dish_name for word in ("刺身", "生鱼", "冷", "沙拉")):
        return "冷食"
    if category == "寿司":
        return "冷食"
    return "热食"


def _images(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def _normalize_category_counts(category_counts: Mapping[str, int]) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for category in ASSET_CATEGORIES:
        try:
            value = int(category_counts.get(category, 0) or 0)
        except (TypeError, ValueError):
            value = 0
        normalized[category] = max(0, min(50, value))
    return normalized


def _copy_into_draft(source: Path, draft_id: str) -> tuple[str, str]:
    destination_dir = draft_directory(draft_id) / "files"
    destination_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"library_{uuid.uuid4().hex}{source.suffix.lower()}"
    shutil.copy2(source, destination_dir / stored_name)
    return stored_name, f"/api/canvas/drafts/{draft_id}/files/{stored_name}"


def _copy_background(source: Path) -> dict[str, str]:
    CANVAS_BACKGROUND_ROOT.mkdir(parents=True, exist_ok=True)
    stored_name = f"library_{uuid.uuid4().hex}{source.suffix.lower()}"
    shutil.copy2(source, CANVAS_BACKGROUND_ROOT / stored_name)
    return {
        "id": stored_name,
        "name": source.name,
        "url": f"/api/canvas/backgrounds/{stored_name}",
        "source": "local",
    }


def build_asset_plan(
    draft_id: str,
    asset_root: str,
    background_root: str,
    category_counts: Mapping[str, int],
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Select images and backgrounds, copying selected files into project storage."""
    root = Path(asset_root).expanduser().resolve()
    background_path = Path(background_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("菜品素材库路径不存在或不是文件夹")
    if not background_path.is_dir():
        raise ValueError("背景素材库路径不存在或不是文件夹")
    counts = _normalize_category_counts(category_counts)
    generator = rng or random.Random()
    dish_dirs = [path for path in root.iterdir() if path.is_dir()]
    grouped: dict[str, list[tuple[Path, list[Path]]]] = {category: [] for category in ASSET_CATEGORIES}
    for dish_dir in dish_dirs:
        images = _images(dish_dir)
        if images:
            classification = classify_library_name(dish_dir.name)
            grouped[str(classification["category"])].append((dish_dir, images))
    backgrounds = _images(background_path)
    if not backgrounds:
        raise ValueError("背景素材库中没有 JPG、PNG 或 WEBP 图片")

    selected: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    warnings: list[str] = []
    for dish_dir in dish_dirs:
        images = _images(dish_dir)
        if not images:
            continue
        classification = classify_library_name(dish_dir.name)
        if classification["reviewRequired"]:
            review_items.append({
                "dishName": dish_dir.name,
                "sourceCategory": str(classification["category"]),
                "classificationReason": str(classification["reason"]),
                "categoryCandidates": list(classification["candidates"]),
                "suggestedCategory": str(classification["category"]),
            })
    for category in ASSET_CATEGORIES:
        count = counts[category]
        candidates = list(grouped[category])
        generator.shuffle(candidates)
        if count > len(candidates):
            warnings.append(f"{category} 只找到 {len(candidates)} 个菜品文件夹，无法满足 {count} 张")
        for dish_dir, images in candidates[:count]:
            source = generator.choice(images)
            stored_name, image_url = _copy_into_draft(source, draft_id)
            background = _copy_background(generator.choice(backgrounds))
            app_category = "甜品" if category == "甜品" else "水果" if category == "水果" else "正餐"
            food_type = infer_food_type(dish_dir.name, category)
            classification = classify_library_name(dish_dir.name)
            selected.append({
                "dishName": dish_dir.name,
                "sourceCategory": category,
                "dishCategory": app_category,
                "foodType": food_type,
                "imageName": source.name,
                "imagePreview": image_url,
                "sourcePath": str(source),
                "storedName": stored_name,
                "background": background,
                "reviewRequired": bool(classification["reviewRequired"]),
                "classificationReason": str(classification["reason"]),
                "categoryCandidates": list(classification["candidates"]),
                "suggestedCategory": str(classification["category"]),
            })
    if not selected:
        raise ValueError("没有按分类数量抽取到菜品图片，请检查文件夹结构和分类名称")
    return {
        "assetRoot": str(root),
        "backgroundRoot": str(background_path),
        "selected": selected,
        "warnings": warnings,
        "categoryCounts": counts,
        "reviewItems": review_items,
    }
