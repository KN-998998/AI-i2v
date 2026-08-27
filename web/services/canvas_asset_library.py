"""Build reviewable canvas workflows from a folder-based dish library."""
from __future__ import annotations

import random
import shutil
import uuid
from pathlib import Path
from typing import Any, Mapping

from web.services.canvas_state import CANVAS_BACKGROUND_ROOT, draft_directory

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ASSET_CATEGORIES = ("寿司", "刺身", "甜品", "主食", "水果", "其他")

_CATEGORY_KEYWORDS = {
    "寿司": ("寿司", "卷寿司", "手卷", "握寿司", "军舰"),
    "刺身": ("刺身", "生鱼片"),
    "甜品": ("甜品", "甜点", "蛋糕", "布丁", "冰淇淋", "慕斯", "奶油"),
    "主食": ("主食", "米饭", "炒饭", "拉面", "乌冬", "面", "丼", "饭"),
    "水果": ("水果", "草莓", "西瓜", "芒果", "葡萄", "苹果", "柠檬"),
}


def infer_library_category(dish_name: str) -> str:
    name = dish_name.strip().lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword.lower() in name for keyword in keywords):
            return category
    return "其他"


def infer_food_type(dish_name: str, category: str) -> str:
    if category in {"刺身", "水果"} or any(word in dish_name for word in ("刺身", "生鱼", "冷", "沙拉")):
        return "冷食"
    if category in {"寿司", "甜品"}:
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
            grouped[infer_library_category(dish_dir.name)].append((dish_dir, images))
    backgrounds = _images(background_path)
    if not backgrounds:
        raise ValueError("背景素材库中没有 JPG、PNG 或 WEBP 图片")

    selected: list[dict[str, Any]] = []
    warnings: list[str] = []
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
            })
    if not selected:
        raise ValueError("没有按分类数量抽取到菜品图片，请检查文件夹结构和分类名称")
    return {
        "assetRoot": str(root),
        "backgroundRoot": str(background_path),
        "selected": selected,
        "warnings": warnings,
        "categoryCounts": counts,
    }
