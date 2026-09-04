"""Build reviewable canvas workflows from a folder-based dish library."""
from __future__ import annotations

import json
import random
import re
import shutil
import threading
import unicodedata
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageOps

from pipeline.config import QWEN_API_KEY, QWEN_LLM_BASE_URL, QWEN_LLM_ENABLED, QWEN_LLM_MODEL
from web.services.canvas_state import CANVAS_BACKGROUND_ROOT, draft_directory

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ASSET_CATEGORIES = ("寿司", "刺身", "前菜/小菜", "炸物", "主菜", "主食", "汤品", "甜品", "水果", "饮品", "套餐", "其他")
FOOD_TYPES = ("冷食", "热食", "混合/多温")
VISUAL_SUBJECT_TYPES = ("菜品主体", "手部", "厨师上半身", "手部+厨师上半身")
DEFAULT_VISUAL_SUBJECT_TYPE = "菜品主体"
_ASSET_METADATA_FILENAME = "asset_metadata.json"
_HOT_PREPARATION_KEYWORDS = ("火炙", "炙烧", "炙烤", "炙り", "炙")
_RULES_PATH = CANVAS_BACKGROUND_ROOT.parent / "canvas_asset_category_rules.json"
_MANUAL_REVIEW_ROOT = CANVAS_BACKGROUND_ROOT.parent / "asset_library_manual_review"
_RULES_LOCK = threading.RLock()

_CATEGORY_KEYWORDS = {
    "寿司": ("寿司", "卷寿司", "手卷", "握寿司", "军舰", "卷物", "巻き寿司", "握り", "にぎり", "軍艦", "手巻き", "ちらし寿司", "押し寿司", "稲荷寿司", "すし", "sushi"),
    "刺身": ("刺身", "生鱼片", "生鱼", "海鲜刺身", "お造り", "造り", "sashimi", "刺し身"),
    "前菜/小菜": ("前菜", "小菜", "开胃菜", "开胃", "沙拉", "色拉", "毛豆", "玉子烧", "茶碗蒸し", "冷菜", "凉菜", "泡菜", "腌菜", "配菜", "下酒菜", "小吃", "先付", "お通し", "おつまみ", "サラダ", "枝豆", "だし巻き", "冷奴", "appetizer", "side dish"),
    "炸物": ("炸物", "天妇罗", "唐扬", "炸鸡", "炸虾", "炸猪排", "炸牛排", "炸", "天婦羅", "天ぷら", "揚げ", "唐揚げ", "とんかつ", "フライ", "カツ", "fry", "fried"),
    "主菜": ("主菜", "烧鸟", "烤鱼", "烤肉", "牛排", "煮物", "锅物", "火锅", "鳗鱼", "猪排", "焼き鳥", "焼魚", "うなぎ", "ステーキ", "主菜", "main dish", "entree"),
    "主食": ("主食", "米饭", "炒饭", "拉面", "乌冬", "荞麦", "面条", "盖饭", "饭团", "炒面", "ご飯", "ライス", "チャーハン", "ラーメン", "うどん", "そば", "麺", "丼", "おにぎり", "焼きそば", "rice", "noodle", "donburi"),
    "汤品": ("汤品", "味噌汤", "味噌汁", "清汤", "浓汤", "海鲜汤", "汤羹", "お吸い物", "潮汁", "豚汁", "スープ", "soup"),
    "甜品": ("甜品", "甜点", "饭后甜点", "蛋糕", "布丁", "冰淇淋", "雪糕", "慕斯", "奶油", "大福", "和果子", "可丽露", "马卡龙", "巧克力", "果冻", "芭菲", "パフェ", "和菓子", "どら焼き", "羊羹", "アイス", "デザート", "dessert", "cake", "pudding", "ice cream", "gelato", "sorbet"),
    # Beverage is checked before fruit so names such as grape wine are not classified as fruit.
    "饮品": ("饮品", "饮料", "酒水", "清酒", "日本酒", "啤酒", "威士忌", "葡萄酒", "红酒", "白酒", "梅酒", "烧酒", "高球", "茶饮", "绿茶", "乌龙茶", "红茶", "抹茶", "咖啡", "果汁", "汽水", "苏打", "饮用水", "ドリンク", "日本酒", "ビール", "ワイン", "焼酎", "梅酒", "ハイボール", "お茶", "抹茶", "コーヒー", "ジュース", "drink", "beverage", "sake", "beer", "wine", "coffee", "juice"),
    "水果": ("水果", "鲜果", "果盘", "草莓", "西瓜", "芒果", "葡萄", "苹果", "柠檬", "橙子", "橙", "桃", "梨", "蓝莓", "樱桃", "菠萝", "凤梨", "香蕉", "柚子", "柑橘", "いちご", "苺", "すいか", "ぶどう", "りんご", "みかん", "フルーツ", "fruit", "strawberry", "watermelon", "mango", "grape", "apple", "lemon", "orange", "peach", "banana"),
    "套餐": ("套餐", "定食", "套餐组合", "set menu", "set meal"),
}
_TRADITIONAL_TO_SIMPLIFIED = str.maketrans({
    "壽": "寿", "魚": "鱼", "鮭": "鲑", "鮪": "鲔", "鯛": "鲷", "鰻": "鳗",
    "鮑": "鲍", "鰹": "鲣", "鯖": "鲭", "魷": "鱿", "蝦": "虾", "貝": "贝",
    "烏": "乌", "龍": "龙", "麵": "面", "麪": "面", "飯": "饭", "飲": "饮",
    "湯": "汤", "鍋": "锅", "燒": "烧", "醬": "酱", "鹽": "盐", "餃": "饺",
    "點": "点", "後": "后", "氣": "气", "櫻": "樱", "蔥": "葱", "蘿": "萝",
    "蔔": "卜", "雞": "鸡", "豬": "猪", "槍": "枪", "漬": "渍", "黃": "黄",
    "雙": "双", "華": "华", "國": "国", "廣": "广", "門": "门", "臺": "台",
    "與": "与", "專": "专", "業": "业", "東": "东", "發": "发", "後": "后",
    "學": "学", "時": "时", "間": "间", "場": "场", "開": "开", "關": "关",
    "實": "实", "驗": "验", "製": "制", "選": "选", "進": "进", "還": "还",
    "這": "这", "個": "个", "種": "种", "類": "类", "別": "别", "點": "点",
    "滿": "满", "從": "从", "來": "来", "為": "为", "無": "无", "與": "与",
    "體": "体", "醫": "医", "藥": "药", "葉": "叶", "蘋": "苹", "檸": "柠",
    "橙": "橙", "莓": "莓", "菠": "菠", "鳳": "凤", "柚": "柚", "麥": "麦",
    "乾": "干", "鮮": "鲜", "凍": "冻", "冰": "冰", "裡": "里", "裾": "裙",
})


def simplify_dish_name(value: str) -> str:
    """Return a stable display name for matching simplified/traditional aliases."""
    return unicodedata.normalize("NFKC", str(value)).translate(_TRADITIONAL_TO_SIMPLIFIED).strip()


def _searchable_name(value: str) -> str:
    normalized = simplify_dish_name(value).casefold()
    return re.sub(r"[\s_\-—–·/\\]+", "", normalized)


def _load_category_rules() -> dict[str, dict[str, str | None]]:
    if not _RULES_PATH.is_file():
        return {}
    try:
        payload = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    rules: dict[str, dict[str, str | None]] = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            category = str(value.get("category") or "")
            food_type = str(value.get("foodType") or "") or None
        else:
            category = str(value)
            food_type = None
        if category in ASSET_CATEGORIES:
            visual_subject_type = str(value.get("visualSubjectType") or DEFAULT_VISUAL_SUBJECT_TYPE) if isinstance(value, dict) else DEFAULT_VISUAL_SUBJECT_TYPE
            rules[_searchable_name(str(key))] = {
                "category": category,
                "foodType": food_type if food_type in FOOD_TYPES else None,
                "visualSubjectType": visual_subject_type if visual_subject_type in VISUAL_SUBJECT_TYPES else DEFAULT_VISUAL_SUBJECT_TYPE,
            }
    return rules


def save_category_rule(dish_name: str, category: str, food_type: str | None = None, visual_subject_type: str | None = None) -> dict[str, str | None]:
    normalized_name = _searchable_name(dish_name)
    if not normalized_name:
        raise ValueError("菜品名称不能为空")
    if category not in ASSET_CATEGORIES:
        raise ValueError("不支持的菜品分类")
    if category in {"甜品", "水果"}:
        food_type = "冷食"
    elif category == "套餐" and food_type != "混合/多温":
        raise ValueError("套餐必须选择混合/多温")
    elif food_type not in FOOD_TYPES:
        raise ValueError("该菜品分类必须选择冷食或热食")
    visual_subject_type = visual_subject_type or DEFAULT_VISUAL_SUBJECT_TYPE
    if visual_subject_type not in VISUAL_SUBJECT_TYPES:
        raise ValueError("不支持的画面主体类型")
    with _RULES_LOCK:
        rules = _load_category_rules()
        rules[normalized_name] = {"category": category, "foodType": food_type, "visualSubjectType": visual_subject_type}
        _RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = _RULES_PATH.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(_RULES_PATH)
    return {"dishName": simplify_dish_name(dish_name), "category": category, "foodType": food_type, "visualSubjectType": visual_subject_type}


def list_category_rules() -> list[dict[str, str | None]]:
    """Return the saved dish classification rules for the management UI."""
    saved_rules = _load_category_rules()
    rules = []
    for dish_name, rule in saved_rules.items():
        if str(rule.get("category")) not in ASSET_CATEGORIES or not str(dish_name).strip():
            continue
        item = {"dishName": simplify_dish_name(str(dish_name)), "category": str(rule["category"]), "foodType": rule.get("foodType")}
        visual_subject_type = rule.get("visualSubjectType")
        if visual_subject_type and visual_subject_type != DEFAULT_VISUAL_SUBJECT_TYPE:
            item["visualSubjectType"] = visual_subject_type
        rules.append(item)
    return sorted(rules, key=lambda item: (ASSET_CATEGORIES.index(item["category"]), item["dishName"].casefold()))


def _category_candidates(dish_name: str) -> list[str]:
    name = _searchable_name(dish_name)
    return [category for category, keywords in _CATEGORY_KEYWORDS.items() if any(_searchable_name(keyword) in name for keyword in keywords)]


def _has_hot_preparation(dish_name: str) -> bool:
    name = _searchable_name(dish_name)
    return any(_searchable_name(token) in name for token in _HOT_PREPARATION_KEYWORDS)


def classify_library_name(dish_name: str) -> dict[str, Any]:
    normalized_name = _searchable_name(dish_name)
    rules = _load_category_rules()
    if normalized_name in rules:
        rule = rules[normalized_name]
        category = str(rule["category"])
        food_type = "混合/多温" if category == "套餐" else "热食" if _has_hot_preparation(dish_name) else rule.get("foodType") or ("冷食" if category in {"甜品", "水果"} else None)
        visual_subject_type = str(rule.get("visualSubjectType") or DEFAULT_VISUAL_SUBJECT_TYPE)
        reason = "人工规则中的加热工序优先" if _has_hot_preparation(dish_name) else "已使用人工确认规则" if food_type else "分类规则已确认，还需确认冷食或热食"
        return {"category": category, "foodType": food_type, "visualSubjectType": visual_subject_type, "candidates": [category], "reviewRequired": food_type is None, "reason": reason}

    name = normalized_name
    if any(token in name for token in ("寿司", "すし", "sushi")):
        is_hot_sushi = _has_hot_preparation(dish_name)
        return {
            "category": "寿司",
            "foodType": "热食" if is_hot_sushi else "冷食",
            "visualSubjectType": DEFAULT_VISUAL_SUBJECT_TYPE,
            "candidates": ["寿司"],
            "reviewRequired": False,
            "reason": "寿司含加热工序词" if is_hot_sushi else "寿司成品词优先",
        }
    candidates = _category_candidates(dish_name)
    # These describe a package or a serving format, not one dish category.
    combination_words = ("定食", "套餐", "拼盘", "拼盤", "盛合", "盛り合わせ", "组合", "組み合わせ", "set", "combo", "platter", "assortment")
    is_combination = any(_searchable_name(word) in name for word in combination_words)
    if is_combination and len(candidates) > 1 and "套餐" in candidates:
        candidates = [category for category in candidates if category != "套餐"]

    # The finished product wins over a preparation or topping word. This makes
    # 天妇罗乌冬 a staple, while 天妇罗拼盘 remains a main dish review case.
    staple_words = ("乌冬", "拉面", "荞麦", "面条", "炒面", "盖饭", "饭团", "米饭", "丼", "うどん", "ラーメン", "そば", "麺", "丼", "ご飯", "おにぎり", "noodle", "donburi", "rice")
    dessert_words = ("冰淇淋", "雪糕", "蛋糕", "布丁", "甜点", "甜品", "大福", "パフェ", "アイス", "デザート", "cake", "pudding", "ice cream", "gelato", "dessert")
    beverage_words = ("拿铁", "奶茶", "咖啡", "茶饮", "绿茶", "乌龙茶", "红茶", "果汁", "酒", "啤酒", "清酒", "饮料", "ラテ", "コーヒー", "ドリンク", "sake", "beer", "wine", "coffee", "juice")
    fried_words = ("炸物", "天妇罗", "唐扬", "炸鸡", "炸虾", "炸猪排", "炸牛排", "天婦羅", "天ぷら", "揚げ", "唐揚げ", "とんかつ", "フライ", "カツ", "fry", "fried")
    if not is_combination and any(_searchable_name(word) in name for word in dessert_words):
        candidates = ["甜品"]
    elif not is_combination and any(_searchable_name(word) in name for word in beverage_words):
        candidates = ["饮品"]
    elif not is_combination and any(_searchable_name(word) in name for word in staple_words):
        candidates = ["主食"]
    elif not is_combination and any(_searchable_name(word) in name for word in fried_words):
        candidates = ["炸物"]

    if is_combination or len(candidates) > 1 or not candidates:
        suggested = candidates[0] if len(candidates) == 1 else "其他"
        reason = "组合菜名，需确认成品主体" if is_combination else "名称命中多个分类" if len(candidates) > 1 else "未匹配到分类词"
        return {"category": suggested, "foodType": "混合/多温" if suggested == "套餐" else "冷食" if suggested in {"甜品", "水果"} else None, "visualSubjectType": DEFAULT_VISUAL_SUBJECT_TYPE, "candidates": candidates, "reviewRequired": True, "reason": reason}
    category = candidates[0]
    return {"category": category, "foodType": "冷食" if category in {"甜品", "水果", "寿司", "刺身", "前菜/小菜"} else "热食", "visualSubjectType": DEFAULT_VISUAL_SUBJECT_TYPE, "candidates": candidates, "reviewRequired": False, "reason": "本地规则匹配"}


def _qwen_message_content(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("Qwen 返回了无效的分类结果")
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ValueError("Qwen 返回了无效的分类内容")
    return str(message["content"])


def _classify_with_qwen(dish_names: list[str]) -> dict[str, dict[str, Any]]:
    categories = "、".join(ASSET_CATEGORIES)
    system_prompt = (
        "你是餐饮素材库分类助手。根据菜品文件夹名称判断它最适合的一个分类。"
        f"允许的分类只有：{categories}。"
        "必须保留每个 dish_name 原样，不得改写、遗漏或新增名称。"
        "只返回 JSON：{\"items\":[{\"dish_name\":\"原名称\",\"category\":\"分类\",\"confidence\":0.0,\"reason\":\"简短理由\"}]}。"
        "confidence 必须是 0 到 1 的数字；无法确定、套餐或组合菜请降低置信度。"
    )
    payload = json.dumps({
        "model": QWEN_LLM_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({"dish_names": dish_names}, ensure_ascii=False)},
        ],
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{QWEN_LLM_BASE_URL.rstrip('/')}/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError("Qwen 菜品分类请求失败") from exc
    if not isinstance(body, dict):
        raise ValueError("Qwen 返回了无效的分类响应")
    content = _qwen_message_content(body).strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Qwen 返回的分类不是有效 JSON") from exc
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list) or len(items) != len(dish_names):
        raise ValueError("Qwen 分类结果数量与菜品数量不一致")
    expected = set(dish_names)
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Qwen 分类结果格式无效")
        name = item.get("dish_name")
        category = item.get("category")
        if not isinstance(name, str) or name not in expected or name in result or category not in ASSET_CATEGORIES:
            raise ValueError("Qwen 返回了未要求的菜品名称或非法分类")
        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Qwen 返回了无效的分类置信度") from exc
        if not 0 <= confidence <= 1:
            raise ValueError("Qwen 返回了超出范围的分类置信度")
        result[name] = {
            "category": category,
            "candidates": [category],
            "foodType": infer_food_type(name, category),
            "visualSubjectType": DEFAULT_VISUAL_SUBJECT_TYPE,
            "reviewRequired": confidence < 0.85,
            "reason": f"Qwen 分类（置信度 {confidence:.0%}）：{str(item.get('reason') or '名称语义判断')}",
            "confidence": confidence,
        }
    if set(result) != expected:
        raise ValueError("Qwen 分类结果遗漏了菜品名称")
    return result


def classify_library_names(dish_names: list[str]) -> tuple[dict[str, dict[str, Any]], str, str | None]:
    """Classify a batch with Qwen when configured, while keeping local fallback and rules."""
    unique_names = list(dict.fromkeys(dish_names))
    canonical_names: dict[str, str] = {}
    for name in unique_names:
        canonical_names.setdefault(_searchable_name(name), simplify_dish_name(name))
    canonical_values = list(canonical_names.values())
    local_canonical = {name: classify_library_name(name) for name in canonical_values}
    if not unique_names:
        return {}, "local", None
    rules = _load_category_rules()
    llm_names = [name for name in canonical_values if _searchable_name(name) not in rules]
    if not llm_names:
        return {name: local_canonical[canonical_names[_searchable_name(name)]] for name in unique_names}, "manual_rules", None
    if not QWEN_LLM_ENABLED or not QWEN_API_KEY:
        return {name: local_canonical[canonical_names[_searchable_name(name)]] for name in unique_names}, "local", None
    try:
        ai_results = _classify_with_qwen(llm_names)
    except ValueError as exc:
        return {name: local_canonical[canonical_names[_searchable_name(name)]] for name in unique_names}, "local_fallback", str(exc)
    for name, result in ai_results.items():
        local_result = local_canonical[name]
        if local_result["reviewRequired"] and local_result["candidates"]:
            result["reviewRequired"] = True
            result["reason"] = f"{result['reason']}；本地规则识别为组合或多分类候选，需人工确认"
    classified = {**local_canonical, **ai_results}
    return {name: classified[canonical_names[_searchable_name(name)]] for name in unique_names}, "qwen", None


def infer_library_category(dish_name: str) -> str:
    return str(classify_library_name(dish_name)["category"])


def infer_food_type(dish_name: str, category: str) -> str:
    name = simplify_dish_name(dish_name)
    if category == "套餐":
        return "混合/多温"
    if _has_hot_preparation(dish_name):
        return "热食"
    if category in {"刺身", "前菜/小菜", "甜品", "水果", "饮品"} or any(word in name for word in ("刺身", "生鱼", "冷", "沙拉")):
        return "冷食"
    if category == "寿司":
        return "冷食"
    return "热食"


def _classification_results(
    dish_groups: list[dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rules = _load_category_rules()
    results: list[dict[str, Any]] = []
    for group in dish_groups:
        dish_name = str(group["dishName"])
        classification = classifications[dish_name]
        normalized_name = _searchable_name(dish_name)
        if normalized_name in rules:
            source = "人工规则"
        elif str(classification.get("reason") or "").startswith("Qwen"):
            source = "Qwen"
        else:
            source = "本地规则"
        results.append({
            "dishName": dish_name,
            "displayName": group["displayName"],
            "category": str(classification["category"]),
            "sourceCategory": str(classification["category"]),
            "foodType": classification.get("foodType"),
            "visualSubjectType": classification.get("visualSubjectType") or DEFAULT_VISUAL_SUBJECT_TYPE,
            "classificationReason": str(classification["reason"]),
            "categoryCandidates": list(classification["candidates"]),
            "suggestedCategory": str(classification["category"]),
            "reviewRequired": bool(classification["reviewRequired"]),
            "classificationSource": source,
            "folderCount": len(group["sourceFolders"]),
            "sourceNames": list(group["sourceNames"]),
        })
    return results


def scan_asset_classifications(asset_root: str) -> dict[str, Any]:
    """Scan and classify all deduplicated dish folders without copying files."""
    root = Path(asset_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("菜品素材库路径不存在或不是文件夹")
    dish_groups = _merge_duplicate_dish_directories(_dish_directories(root))
    classifications, classification_mode, classification_warning = classify_library_names([
        group["dishName"] for group in dish_groups
    ])
    asset_metadata = _load_asset_metadata(root)
    for group in dish_groups:
        classification = classifications[group["dishName"]]
        metadata = _metadata_for_dish(asset_metadata, str(classification["category"]), group["dishName"])
        if metadata:
            classification["visualSubjectType"] = metadata["visualSubjectType"]
    results = _classification_results(dish_groups, classifications)
    return {
        "assetRoot": str(root),
        "classificationResults": results,
        "classificationMode": classification_mode,
        "classificationWarning": classification_warning,
    }


def _images(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def _load_asset_metadata(root: Path) -> dict[str, dict[str, str]]:
    path = root / _ASSET_METADATA_FILENAME
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): value
        for key, value in payload.items()
        if isinstance(value, dict)
        and value.get("visualSubjectType") in VISUAL_SUBJECT_TYPES
        and value.get("category") in ASSET_CATEGORIES
    }


def _metadata_for_dish(metadata: dict[str, dict[str, str]], category: str, dish_name: str) -> dict[str, str]:
    return metadata.get(f"{category}/{_searchable_name(dish_name)}", {})


def _dish_directories(root: Path) -> list[tuple[Path, list[Path]]]:
    """Find leaf folders containing images, allowing a library root above category folders."""
    images_by_directory: dict[Path, list[Path]] = {}
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            images_by_directory.setdefault(path.parent, []).append(path)
    candidates = list(images_by_directory.items())
    leaf_candidates = [
        (path, images)
        for path, images in candidates
        if not any(path != other and path in other.parents for other, _ in candidates)
    ]
    return sorted(leaf_candidates, key=lambda item: str(item[0]).casefold())


def _merge_duplicate_dish_directories(
    dish_images: list[tuple[Path, list[Path]]],
) -> list[dict[str, Any]]:
    """Merge folders whose names identify the same dish after normalization."""
    grouped: dict[str, dict[str, Any]] = {}
    for dish_dir, images in dish_images:
        key = _searchable_name(dish_dir.name)
        if not key:
            continue
        group = grouped.setdefault(key, {
            "dishName": simplify_dish_name(dish_dir.name) or dish_dir.name,
            "sourceNames": [],
            "sourceFolders": [],
            "images": [],
        })
        if dish_dir.name not in group["sourceNames"]:
            group["sourceNames"].append(dish_dir.name)
        group["sourceFolders"].append(dish_dir)
        group["images"].extend(images)
    for group in grouped.values():
        source_names = list(dict.fromkeys(group["sourceNames"]))
        group["sourceNames"] = source_names
        group["displayName"] = "/".join(source_names) if len(source_names) > 1 else str(group["dishName"])
    return sorted(grouped.values(), key=lambda item: str(item["dishName"]).casefold())


def _manual_review_file(scan_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", scan_id):
        raise ValueError("人工整理扫描 ID 无效")
    return _MANUAL_REVIEW_ROOT / f"{scan_id}.json"


def manual_review_upload_directory() -> Path:
    return _MANUAL_REVIEW_ROOT / "uploads" / uuid.uuid4().hex


def _manual_review_groups(asset_root: str) -> list[dict[str, Any]]:
    root = Path(asset_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("菜品素材库路径不存在或不是文件夹")
    groups = _merge_duplicate_dish_directories(_dish_directories(root))
    return [
        {
            "dishKey": _searchable_name(str(group["dishName"])),
            "dishName": str(group["dishName"]),
            "displayName": str(group["displayName"]),
            "sourceNames": list(group["sourceNames"]),
            "sourceFolders": [str(path) for path in group["sourceFolders"]],
            "images": [str(path) for path in group["images"]],
        }
        for group in groups
    ]


def scan_manual_asset_library(asset_root: str) -> dict[str, Any]:
    """Create a pure-manual review manifest; no classifier is called here."""
    groups = _manual_review_groups(asset_root)
    if not groups:
        raise ValueError("没有找到包含图片的菜品文件夹")
    scan_id = uuid.uuid4().hex
    payload = {
        "scanId": scan_id,
        "assetRoot": str(Path(asset_root).expanduser().resolve()),
        "createdAt": uuid.uuid1().time,
        "groups": groups,
    }
    _MANUAL_REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = _MANUAL_REVIEW_ROOT / f"{scan_id}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(_manual_review_file(scan_id))
    finally:
        temporary.unlink(missing_ok=True)
    return manual_review_scan_response(payload)


def manual_review_scan_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    groups = payload.get("groups") if isinstance(payload.get("groups"), list) else []
    items = []
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        images = group.get("images") if isinstance(group.get("images"), list) else []
        dish_key = str(group.get("dishKey") or "")
        items.append({
            "dishKey": dish_key,
            "dishName": str(group.get("dishName") or ""),
            "displayName": str(group.get("displayName") or group.get("dishName") or ""),
            "sourceNames": [str(name) for name in group.get("sourceNames", [])],
            "folderCount": len(group.get("sourceFolders", [])),
            "imageCount": len(images),
            "visualSubjectType": str(group.get("visualSubjectType") or DEFAULT_VISUAL_SUBJECT_TYPE),
            "previewUrls": [f"/api/canvas/asset-library/manual-review/scans/{payload['scanId']}/previews/{dish_key}/{index}" for index in range(min(4, len(images)))],
        })
    review_state = payload.get("reviewState") if isinstance(payload.get("reviewState"), Mapping) else {}
    return {
        "scanId": str(payload.get("scanId") or ""),
        "assetRoot": str(payload.get("assetRoot") or ""),
        "items": items,
        "reviewState": {
            "selections": review_state.get("selections") if isinstance(review_state.get("selections"), Mapping) else {},
            "excludedDishKeys": review_state.get("excludedDishKeys") if isinstance(review_state.get("excludedDishKeys"), list) else [],
        },
    }


def load_manual_review_scan(scan_id: str) -> dict[str, Any]:
    path = _manual_review_file(scan_id)
    if not path.is_file():
        raise ValueError("人工整理扫描结果不存在或已过期")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("人工整理扫描结果无法读取") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("groups"), list):
        raise ValueError("人工整理扫描结果格式无效")
    return payload


def save_manual_review_state(scan_id: str, selections: Mapping[str, Any], excluded_dish_keys: list[str]) -> dict[str, Any]:
    """Persist the human review state with its scan manifest, independent of browser storage."""
    payload = load_manual_review_scan(scan_id)
    groups = {str(group.get("dishKey")) for group in payload["groups"] if isinstance(group, Mapping)}
    if not isinstance(selections, Mapping) or not isinstance(excluded_dish_keys, list):
        raise ValueError("人工整理状态格式无效")
    excluded = [str(key) for key in excluded_dish_keys]
    if len(excluded) != len(set(excluded)) or not set(excluded).issubset(groups):
        raise ValueError("排除的菜品不存在于当前扫描结果")
    normalized: dict[str, dict[str, str]] = {}
    for key, value in selections.items():
        key = str(key)
        if key not in groups or not isinstance(value, Mapping):
            raise ValueError("人工分类状态包含无效菜品")
        category = str(value.get("category") or "")
        food_type = str(value.get("foodType") or "")
        visual_subject_type = str(value.get("visualSubjectType") or DEFAULT_VISUAL_SUBJECT_TYPE)
        if category and category not in ASSET_CATEGORIES:
            raise ValueError("人工分类状态包含无效菜品分类")
        if food_type and food_type not in FOOD_TYPES:
            raise ValueError("人工分类状态包含无效冷热属性")
        if visual_subject_type not in VISUAL_SUBJECT_TYPES:
            raise ValueError("人工分类状态包含无效画面主体类型")
        normalized[key] = {"category": category, "foodType": food_type, "visualSubjectType": visual_subject_type}
    payload["reviewState"] = {"selections": normalized, "excludedDishKeys": excluded}
    path = _manual_review_file(scan_id)
    temporary = path.with_name(f"{path.stem}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return manual_review_scan_response(payload)


def manual_review_preview_path(scan_id: str, dish_key: str, image_index: int) -> Path:
    payload = load_manual_review_scan(scan_id)
    for group in payload["groups"]:
        if str(group.get("dishKey")) != dish_key:
            continue
        images = group.get("images") if isinstance(group.get("images"), list) else []
        if not isinstance(image_index, int) or image_index < 0 or image_index >= len(images):
            break
        path = Path(str(images[image_index])).resolve()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            thumbnail = _MANUAL_REVIEW_ROOT / "thumbnails" / scan_id / f"{dish_key}_{image_index}.jpg"
            if thumbnail.is_file():
                return thumbnail
            try:
                thumbnail.parent.mkdir(parents=True, exist_ok=True)
                temporary = thumbnail.with_name(f"{thumbnail.stem}.{uuid.uuid4().hex}.tmp.jpg")
                with Image.open(path) as image:
                    preview = ImageOps.exif_transpose(image).convert("RGB")
                    preview.thumbnail((480, 480), Image.Resampling.LANCZOS)
                    preview.save(temporary, format="JPEG", quality=78, optimize=True)
                temporary.replace(thumbnail)
                return thumbnail
            except (OSError, ValueError):
                # Keep the review page usable for unusual or partially corrupt files.
                return path
        break
    raise ValueError("人工整理预览图片不存在")


def organize_manual_asset_library(scan_id: str, target_root: str, classifications: list[Mapping[str, Any]], excluded_dish_keys: list[str] | None = None) -> dict[str, Any]:
    """Copy a completely human-confirmed scan into category/dish/image folders."""
    payload = load_manual_review_scan(scan_id)
    groups = {str(group.get("dishKey")): group for group in payload["groups"] if isinstance(group, Mapping)}
    if not groups:
        raise ValueError("人工整理扫描结果为空")
    excluded = set(excluded_dish_keys or [])
    if not excluded.issubset(groups):
        raise ValueError("排除的菜品不存在于当前扫描结果")
    active_groups = {key: group for key, group in groups.items() if key not in excluded}
    if not active_groups:
        raise ValueError("至少保留一个素材后才能整理入库")
    if not isinstance(classifications, list) or len(classifications) != len(active_groups):
        received = len(classifications) if isinstance(classifications, list) else 0
        raise ValueError(f"请完成所有菜品的人工分类和冷热标记（需要 {len(active_groups)} 个，收到 {received} 个）")
    confirmed: dict[str, tuple[str, str, str]] = {}
    for item in classifications:
        if not isinstance(item, Mapping):
            raise ValueError("人工分类结果格式无效")
        key = str(item.get("dishKey") or "")
        category = str(item.get("category") or "")
        food_type = str(item.get("foodType") or "")
        if key not in active_groups or key in confirmed or category not in ASSET_CATEGORIES or food_type not in FOOD_TYPES:
            raise ValueError("人工分类结果包含无效或重复菜品")
        if category == "套餐" and food_type != "混合/多温":
            raise ValueError("套餐必须选择混合/多温")
        if category in {"甜品", "水果"} and food_type != "冷食":
            raise ValueError("甜品和水果必须选择冷食")
        visual_subject_type = str(item.get("visualSubjectType") or DEFAULT_VISUAL_SUBJECT_TYPE)
        if visual_subject_type not in VISUAL_SUBJECT_TYPES:
            raise ValueError("人工分类结果包含无效的画面主体类型")
        confirmed[key] = (category, food_type, visual_subject_type)
    if set(confirmed) != set(active_groups):
        missing = len(set(active_groups) - set(confirmed))
        raise ValueError(f"请完成所有菜品的人工分类和冷热标记（缺少 {missing} 个）")
    target = Path(target_root).expanduser().resolve()
    if target == Path(payload["assetRoot"]).resolve() or Path(payload["assetRoot"]).resolve() in target.parents:
        raise ValueError("标准素材库不能位于原始素材库内部")
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    metadata: dict[str, dict[str, str]] = {}
    for key, group in active_groups.items():
        category, food_type, visual_subject_type = confirmed[key]
        category_dir = _safe_library_name(category)
        dish_dir = target / category_dir / _safe_library_name(str(group.get("dishName") or "未命名菜品"))
        dish_dir.mkdir(parents=True, exist_ok=True)
        for source_value in group.get("images", []):
            source = Path(str(source_value)).resolve()
            if not source.is_file() or source.suffix.lower() not in IMAGE_EXTENSIONS:
                raise ValueError(f"源图片不存在：{source.name}")
            destination = _unique_destination(dish_dir / source.name)
            shutil.copy2(source, destination)
            copied += 1
        metadata[f"{category}/{_searchable_name(str(group.get('dishName') or ''))}"] = {
            "category": category,
            "foodType": food_type,
            "visualSubjectType": visual_subject_type,
        }
    metadata_path = target / _ASSET_METADATA_FILENAME
    temporary = metadata_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(metadata_path)
    return {"scanId": scan_id, "targetRoot": str(target), "dishCount": len(active_groups), "imageCount": copied}


def _safe_library_name(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", simplify_dish_name(value)).strip(" .")
    return name or "未命名菜品"


def _unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10000):
        candidate = path.with_name(f"{path.stem}__{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise ValueError(f"图片重名过多：{path.name}")


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
    asset_metadata = _load_asset_metadata(root)
    grouped: dict[str, list[dict[str, Any]]] = {category: [] for category in ASSET_CATEGORIES}
    raw_dish_images = _dish_directories(root)
    dish_groups = _merge_duplicate_dish_directories(raw_dish_images)
    classifications, classification_mode, classification_warning = classify_library_names([
        group["dishName"] for group in dish_groups
    ])
    warnings: list[str] = []
    if classification_warning:
        warnings.append(f"{classification_warning}，已回退本地规则")
    for group in dish_groups:
        classification = classifications[group["dishName"]]
        metadata = _metadata_for_dish(asset_metadata, str(classification["category"]), group["dishName"])
        if metadata:
            classification["visualSubjectType"] = metadata["visualSubjectType"]
        if classification["category"] in grouped:
            grouped[str(classification["category"])].append(group)
    backgrounds = _images(background_path)
    if not backgrounds:
        raise ValueError("背景素材库中没有 JPG、PNG 或 WEBP 图片")

    selected: list[dict[str, Any]] = []
    review_by_name: dict[str, dict[str, Any]] = {}
    classification_results = _classification_results(dish_groups, classifications)
    for group in dish_groups:
        classification = classifications[group["dishName"]]
        if classification["reviewRequired"]:
            review_by_name[group["dishName"]] = {
                "dishName": group["dishName"],
                "displayName": group["displayName"],
                "sourceCategory": str(classification["category"]),
                "classificationReason": str(classification["reason"]),
                "categoryCandidates": list(classification["candidates"]),
                "suggestedCategory": str(classification["category"]),
                "foodType": classification.get("foodType") if classification["category"] in {"甜品", "水果", "套餐"} else None,
                "visualSubjectType": classification.get("visualSubjectType") or DEFAULT_VISUAL_SUBJECT_TYPE,
                "folderCount": len(group["sourceFolders"]),
                "sourceNames": list(group["sourceNames"]),
            }
    review_items = list(review_by_name.values())
    for category in ASSET_CATEGORIES:
        count = counts[category]
        candidates = list(grouped[category])
        generator.shuffle(candidates)
        if count > len(candidates):
            warnings.append(f"{category} 只找到 {len(candidates)} 个不同菜品，无法满足 {count} 张")
        for group in candidates[:count]:
            source = generator.choice(group["images"])
            stored_name, image_url = _copy_into_draft(source, draft_id)
            background = _copy_background(generator.choice(backgrounds))
            app_category = category
            classification = classifications[group["dishName"]]
            food_type = str(classification.get("foodType") or infer_food_type(group["dishName"], category))
            selected.append({
                "dishName": group["dishName"],
                "displayName": group["displayName"],
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
                "sourceFolderCount": len(group["sourceFolders"]),
                "sourceNames": list(group["sourceNames"]),
            })
    if not selected:
        raise ValueError("没有按分类数量抽取到菜品图片，请检查文件夹结构和分类名称")
    return {
        "assetRoot": str(root),
        "backgroundRoot": str(background_path),
        "selected": selected,
        "warnings": warnings,
        "categoryCounts": counts,
        "classificationResults": classification_results,
        "reviewItems": review_items,
        "classificationMode": classification_mode,
        "classificationWarning": classification_warning,
    }
