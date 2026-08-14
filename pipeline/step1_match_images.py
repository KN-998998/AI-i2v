# -*- coding: utf-8 -*-
"""
Step 1: 菜品清单 → 匹配素材图片 → 预处理为 9:16 / 1080p
========================================================

输入：batch.yaml 中的菜品清单
输出：01_images/ 目录下每道菜的预处理图片

用法：
  python pipeline/step1_match_images.py --config pipeline/batch_20260814.yaml
  python pipeline/step1_match_images.py --config pipeline/batch_20260814.yaml --limit 2  # 每菜取2张
"""
import argparse
import glob
import os
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageOps, ImageFilter

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import (
    IMAGE_LIBRARY, EXTRA_IMAGE_LIBS,
    PREP_TARGET_SHORT, PREP_MAX_LONG, PREP_JPEG_QUALITY,
    get_batch_dir, batch_subdirs,
)

TARGET_RATIO = 9 / 16
BKGD_LIGHT = (248, 246, 244)
BKGD_DARK  = (28, 26, 24)


def find_dish_images(dish_name: str, image_dirs: list, limit: int = 1) -> list:
    """在素材库中按菜名匹配图片文件夹，返回最大的 N 张图片路径。"""
    exts = ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"]
    candidates = []

    for lib_dir in image_dirs:
        if not lib_dir.exists():
            continue
        # 1. 精确匹配文件夹名 == 菜名
        exact = lib_dir / dish_name
        if exact.is_dir():
            for ext in exts:
                candidates.extend(glob.glob(str(exact / "**" / ext), recursive=True))

        # 2. 模糊匹配文件夹名包含菜名
        if not candidates:
            for sub in lib_dir.iterdir():
                if sub.is_dir() and dish_name in sub.name:
                    for ext in exts:
                        candidates.extend(glob.glob(str(sub / "**" / ext), recursive=True))

        # 3. 在所有子文件夹中搜索文件名包含菜名的图片
        if not candidates:
            for ext in exts:
                candidates.extend(glob.glob(str(lib_dir / "**" / ext), recursive=True))
            candidates = [f for f in candidates if dish_name in Path(f).stem]

    # 去重
    candidates = list(set(candidates))
    if not candidates:
        return []

    # 按文件大小降序（大图通常清晰度更高）
    candidates.sort(key=lambda f: -os.path.getsize(f))
    return candidates[:limit]


def open_image(path):
    """打开图片，处理 EXIF 旋转 + PNG alpha 转白底。"""
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", im.size, BKGD_LIGHT)
        bg.paste(im, mask=im.split()[-1])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")
    return im


def crop_to_9_16(im, target_short=PREP_TARGET_SHORT):
    """把任意比例图片裁切为 9:16 竖版。"""
    w, h = im.size
    target_w = target_short
    target_h = int(target_short / TARGET_RATIO)  # 1080→1920

    src_ratio = w / h
    want_ratio = target_w / target_h  # 9/16

    if abs(src_ratio - want_ratio) < 0.05:
        # 比例接近，直接缩放
        return im.resize((target_w, target_h), Image.LANCZOS)

    if src_ratio > want_ratio:
        # 原图更宽（横图）→ 左右裁切，偏下保留食物主体
        new_w = int(h * want_ratio)
        left = (w - new_w) // 2
        im = im.crop((left, 0, left + new_w, h))
    else:
        # 原图更高 → 上下裁切，偏下 35%
        new_h = int(w / want_ratio)
        top = int((h - new_h) * 0.35)
        im = im.crop((0, top, w, top + new_h))

    return im.resize((target_w, target_h), Image.LANCZOS)


def enforce_size_limit(im):
    """确保长边不超过 API 限制。"""
    w, h = im.size
    if max(w, h) > PREP_MAX_LONG:
        scale = PREP_MAX_LONG / max(w, h)
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return im


def sharpen(im):
    """轻微锐化，抵消缩略图模糊。"""
    return im.filter(ImageFilter.UnsharpMask(radius=1.0, percent=130, threshold=2))


def preprocess_one(src_path, out_path):
    """处理单张图片：打开→9:16裁切→尺寸限制→锐化→保存。"""
    im = open_image(src_path)
    w, h = im.size
    im = crop_to_9_16(im)
    im = enforce_size_limit(im)
    im = sharpen(im)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.save(out_path, "JPEG", quality=PREP_JPEG_QUALITY, optimize=True)

    final_w, final_h = im.size
    size_kb = os.path.getsize(out_path) / 1024
    print(f"  [OK] {os.path.basename(src_path):<40} {w}x{h} → {final_w}x{final_h}  {size_kb:.0f}KB")
    return out_path


def run(config_path: str, limit: int = 1):
    """主入口：读取 batch.yaml → 匹配图片 → 预处理。"""
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    batch_date = cfg["batch"]["date"]
    batch_dir = get_batch_dir(batch_date)
    dirs = batch_subdirs(batch_dir)

    dishes = cfg["dishes"]
    all_image_dirs = [IMAGE_LIBRARY] + EXTRA_IMAGE_LIBS

    print(f"{'='*60}")
    print(f"Step 1: 匹配素材图片 + 预处理")
    print(f"  批次日期: {batch_date}")
    print(f"  菜品数量: {len(dishes)}")
    print(f"  每菜取图: {limit} 张")
    print(f"  输出目录: {dirs['images']}")
    print(f"{'='*60}")

    results = []
    for i, dish in enumerate(dishes, 1):
        name = dish["name"]
        image_dir = dish.get("image_dir", "")

        # 优先用手动指定的路径
        search_dirs = [Path(image_dir)] if image_dir else all_image_dirs

        print(f"\n[{i}/{len(dishes)}] {name} ({dish.get('category', '')})")

        images = find_dish_images(name, search_dirs, limit=limit)

        if not images:
            print(f"  [警告] 未找到匹配图片！请手动指定 image_dir")
            results.append({"dish": name, "status": "not_found", "images": []})
            continue

        processed = []
        for img_path in images:
            base = Path(img_path).stem
            out_name = f"{name}_{base}_9x16.jpg"
            out_path = str(dirs["images"] / out_name)
            # 避免文件名重复
            if os.path.exists(out_path):
                out_path = str(dirs["images"] / f"{name}_{base}_{i}_9x16.jpg")
            processed.append(preprocess_one(img_path, out_path))

        results.append({
            "dish": name,
            "status": "ok",
            "images": processed,
            "category": dish.get("category", ""),
            "highlight": dish.get("highlight", ""),
        })

    # 输出清单
    manifest_path = dirs["images"] / "manifest.json"
    import json
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n{'='*60}")
    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"完成: {ok}/{len(dishes)} 道菜找到图片")
    print(f"清单: {manifest_path}")
    print(f"{'='*60}")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Step 1: 匹配素材图片 + 预处理")
    ap.add_argument("--config", required=True, help="batch.yaml 路径")
    ap.add_argument("--limit", type=int, default=1, help="每道菜取几张图（默认1）")
    args = ap.parse_args()
    run(args.config, args.limit)
