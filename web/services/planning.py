# -*- coding: utf-8 -*-
"""Dish planning and review selection helpers."""
import csv
import os
import random
from pathlib import Path
from typing import Any

from pipeline.config import TEMPLATE_3_DISH, TEMPLATE_5_DISH
from web.services.state import load_manifest


def ordered_selected_dishes(state: dict[str, Any], selected: dict[str, str]) -> list[str]:
    names = []
    for dish in state.get("dishes", []):
        name = dish.get("name", "")
        if name in selected and name not in names:
            names.append(name)
    for name in selected:
        if name not in names:
            names.append(name)
    return names


def is_dessert_dish(dish: dict[str, Any]) -> bool:
    if dish.get("is_dessert") is True or dish.get("dessert") is True:
        return True
    text = f"{dish.get('name', '')} {dish.get('category', '')}".lower()
    keywords = [
        "甜品", "甜点", "甜食", "dessert", "cake", "蛋糕", "布丁", "冰淇淋",
        "慕斯", "奶酪", "糖水", "点心", "泡芙", "芋圆", "千层", "提拉米苏",
    ]
    return any(k.lower() in text for k in keywords)


def get_video_template(dish_count: int) -> dict[str, Any]:
    if dish_count >= 6:
        return {
            "total_duration": 10,
            "segments": [
                {"index": 0, "duration": 2.5, "role": "hook"},
                {"index": 1, "duration": 1.3, "role": "body"},
                {"index": 2, "duration": 1.3, "role": "body"},
                {"index": 3, "duration": 1.3, "role": "body"},
                {"index": 4, "duration": 1.3, "role": "body"},
                {"index": 5, "duration": 1.3, "role": "body"},
                {"index": 6, "duration": 1.0, "role": "outro"},
            ],
        }
    return TEMPLATE_5_DISH


def build_video_plan(state: dict[str, Any], selected: dict[str, str], video_config: dict[str, Any]) -> list[dict[str, Any]]:
    explicit = video_config.get("videos") or []
    if explicit:
        plan = []
        for i, item in enumerate(explicit, 1):
            dishes = [d for d in item.get("dishes", []) if d in selected]
            if not dishes:
                continue
            template_key = item.get("template") or ("5_dish" if len(dishes) >= 4 else "3_dish")
            plan.append({
                "id": item.get("id") or f"v{i:02d}",
                "dishes": dishes,
                "hook_dish": item.get("hook_dish") or dishes[0],
                "template": template_key,
            })
        return plan

    order = video_config.get("dish_order") or ordered_selected_dishes(state, selected)
    order = [d for d in order if d in selected]
    if not order:
        return []

    count = max(1, min(int(video_config.get("count") or 10), 50))
    min_dishes = max(1, min(int(video_config.get("min_dishes") or 5), 20))
    max_dishes = max(min_dishes, min(int(video_config.get("max_dishes") or 6), 20))

    dish_meta = {d.get("name", ""): d for d in state.get("dishes", []) if d.get("name")}
    candidates = []
    for name in order:
        meta = dict(dish_meta.get(name, {}))
        meta.setdefault("name", name)
        candidates.append(meta)

    dessert_pool = [d for d in candidates if is_dessert_dish(d)]
    main_pool = [d for d in candidates if not is_dessert_dish(d)] or list(candidates)

    plan = []
    seen = set()
    for i in range(count):
        dish_count = min(random.randint(min_dishes, max_dishes), len(candidates))
        if dish_count <= 0:
            continue

        include_dessert = bool(dessert_pool) and dish_count >= 5 and random.random() < 0.7
        if include_dessert and len(main_pool) >= dish_count - 1:
            dishes = random.sample(main_pool, dish_count - 1) + [random.choice(dessert_pool)]
        else:
            pool = main_pool if len(main_pool) >= dish_count else candidates
            dishes = random.sample(pool, dish_count)

        if any(is_dessert_dish(d) for d in dishes):
            non_desserts = [d for d in dishes if not is_dessert_dish(d)]
            dessert = [d for d in dishes if is_dessert_dish(d)][0]
            random.shuffle(non_desserts)
            dishes = non_desserts + [dessert]
        else:
            random.shuffle(dishes)

        signature = tuple(d["name"] for d in dishes)
        attempts = 0
        while signature in seen and attempts < 5:
            attempts += 1
            if include_dessert and len(main_pool) >= dish_count - 1 and dessert_pool:
                dishes = random.sample(main_pool, dish_count - 1) + [random.choice(dessert_pool)]
            else:
                pool = main_pool if len(main_pool) >= dish_count else candidates
                dishes = random.sample(pool, dish_count)
            if any(is_dessert_dish(d) for d in dishes):
                non_desserts = [d for d in dishes if not is_dessert_dish(d)]
                dessert = [d for d in dishes if is_dessert_dish(d)][0]
                random.shuffle(non_desserts)
                dishes = non_desserts + [dessert]
            else:
                random.shuffle(dishes)
            signature = tuple(d["name"] for d in dishes)
        seen.add(signature)

        dish_names = [d["name"] for d in dishes]
        plan.append({
            "id": f"v{i + 1:02d}",
            "type": "auto_batch",
            "template": "6_dish" if len(dish_names) >= 6 else "5_dish",
            "dishes": dish_names,
            "hook_dish": next((d["name"] for d in dishes if not is_dessert_dish(d)), dish_names[0]),
        })
    return plan


def write_selection_csv(dirs: dict[str, Path], selected: dict[str, str]) -> Path:
    clips = load_manifest(dirs, "clips") or []
    csv_path = dirs["selected"] / "checklist.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["dish", "roll", "filename", "selected", "notes"])
        for clip in clips:
            if clip.get("status") != "ok":
                continue
            filename = os.path.basename(clip["output"])
            writer.writerow([
                clip["dish"],
                clip.get("roll", ""),
                filename,
                "y" if selected.get(clip["dish"]) == filename else "",
                "",
            ])
    return csv_path