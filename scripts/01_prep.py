# -*- coding: utf-8 -*-
"""
阶段 01 · 备料（素材管理）
============================

功能：
  1. 读入用户指定的 5-6 道菜（每道菜一个文件夹）
  2. 每道菜自动选最清晰的 1 张大图
  3. 压缩裁切为 720×1280 9:16（wan2.6 API 接受范围内）
  4. 按菜品类型自动匹配提示词（热菜/烤物/刺身/煲类…）
  5. 输出批次清单 JSON，后续所有阶段都读它

用法：
  # 示例：6 道菜（5 道菜 + 1 个氛围收尾）
  python scripts/01_prep.py --batch "demo1" \
     --dish "蒲烧鳗鱼|D:/素材库/菜品照片/蒲烧鳗鱼|烤物" \
     --dish "天妇罗|D:/素材库/菜品照片/天妇罗|炸物" \
     --dish "矶煮鲍鱼|D:/素材库/菜品照片/矶煮鲍鱼|热菜" \
     --dish "红酒鹅肝|D:/素材库/菜品照片/红酒鹅肝|烤物" \
     --dish "角切鱼生饭|D:/素材库/菜品照片/角切鱼生饭|刺身饭" \
     --dish "时令沙拉|D:/素材库/菜品照片/时令沙拉|前菜" \
     --store "示例店(XX路店)" --city "示例城市"

  # 简写：用 CSV 批量导（菜名|路径|类型，一行一道）
  python scripts/01_prep.py --batch "demo1" --csv "dishes.csv" --store "示例店"

输出：
  batches/<batch>/manifest.json   ← 全流程共用的清单
  batches/<batch>/01_images/      ← 预处理好的 720×1280 jpg
"""
import argparse
import json
import os
import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

# 复用 prep_images.py 里的处理逻辑
sys.path.insert(0, os.path.dirname(__file__))
from prep_images import (
    open_image, pick_crop_strategy, crop_to_9_16,
    enforce_size_limit, sharp, JPEG_QUALITY
)

ROOT = Path(__file__).resolve().parent.parent
BATCHES_DIR = ROOT / "batches"

# ── 提示词模板（对齐 05_提示词模板/即梦餐饮图生视频提示词.md）───────────────
PROMPT_STYLE = "高端餐饮广告镜头，菜品保持原样，镜头缓慢推进，柔和暖色灯光，浅景深，餐具质感清晰，食物光泽自然，画面稳定，干净高级，不生成文字，不生成Logo，不出现人物手部"

DISH_TYPE_PROMPTS = {
    "热菜": "热气持续升起，镜头快速推近特写，暖色灯光，食欲感拉满，画面稳定，高清",
    "煲类": "热气持续升起，锅边微微沸腾，汤面油光闪烁，镜头推近，食欲感强，高清",
    "面食": "筷子已夹起面条正在拉升，汤汁滴落，热气腾腾，镜头轻微环绕，画面稳定",
    "粉类": "筷子已夹起粉正在拉升，汤汁清亮，热气腾腾，镜头轻微环绕，画面稳定",
    "淋酱": "酱汁正在从上方淋下，慢动作特写，镜头微微下移，油润光泽，高清",
    "饮品": "镜头环绕旋转，光线柔和，质感细腻，背景轻微虚化，画面干净",
    "甜品": "镜头环绕旋转，光线柔和，质感细腻，背景轻微虚化，画面干净",
    "烤物": "表面油光闪烁，热气微微升腾，镜头快速推近，暖色灯光，食欲感强",
    "炸物": "表面油光闪烁，热气微微升腾，镜头快速推近，暖色灯光，酥脆质感清晰",
    "刺身": "鱼肉纹理清晰，光泽水润冰凉，镜头缓慢推进，高级感，浅景深，画面稳定",
    "刺身饭": "海胆鱼籽光泽诱人，食材纹理清晰，镜头缓慢推进，高级感，浅景深",
    "寿司": "醋饭颗粒分明，鱼料纹理清晰，镜头缓慢推进，高级感，浅景深，画面稳定",
    "前菜": "食材色彩鲜艳，摆盘精致，镜头缓慢推进，浅景深，高级感，画面稳定",
    "沙拉": "食材新鲜，色彩鲜艳，镜头缓慢环绕，水滴光泽，清爽质感，画面稳定",
    "套餐": "多种食材错落有致，整体展示，镜头缓慢推进，高级感，浅景深",
    "氛围": "餐厅环境氛围感，灯光柔和温暖，画面轻微缓慢运动，高级日料店质感",
    "飘雪": "干冰雾气缓缓扩散，飘雪效果，镜头缓慢推近，高级感，浅景深，画面稳定",
}

NEGATIVE_PROMPT = "不要改变菜品主体，不要让食物变形，不要凭空增加新食材，不要生成文字，不要生成Logo，不要生成二维码，不要出现人物手部，不要夸张动画，不要卡通风格，不要低清画质"


def pick_best_image(folder):
    """在菜文件夹里挑"最清晰最大"的 1 张：用拉普拉斯方差 + 文件大小加权"""
    import glob
    exts = ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"]
    files = []
    for e in exts:
        files.extend(glob.glob(os.path.join(folder, "**", e), recursive=True))
    if not files:
        return None
    try:
        import cv2
        import numpy as np
    except ImportError:
        # 没有 opencv 就按文件大小挑
        files.sort(key=lambda f: -os.path.getsize(f))
        return files[0]

    scored = []
    for f in files[:30]:  # 只评估前 30 张大图，省时间
        try:
            size = os.path.getsize(f)
            img = cv2.imdecode(np.fromfile(f, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if img is None: continue
            # 缩到统一尺寸再比清晰度（公平）
            img = cv2.resize(img, (800, 800))
            lap = cv2.Laplacian(img, cv2.CV_64F).var()
            score = lap + size / 100000  # 清晰度为主，文件大小辅助
            scored.append((score, f))
        except Exception:
            pass
    if not scored:
        files.sort(key=lambda f: -os.path.getsize(f))
        return files[0]
    scored.sort(reverse=True)
    return scored[0][1]


def process_image(src_path, out_path):
    """处理一张图：9:16裁切 + 缩到720短边 + 锐化"""
    im = open_image(src_path)
    w, h = im.size
    strategy = pick_crop_strategy(w, h)
    im = crop_to_9_16(im, strategy)
    im = enforce_size_limit(im)
    im = sharp(im)
    im.save(out_path, 'JPEG', quality=JPEG_QUALITY, optimize=True)
    return im.size


def dish_name_to_type(dish_name, user_hint=None):
    """从菜名猜类型（用户没写类型时用），匹配不到返回通用型"""
    if user_hint and user_hint in DISH_TYPE_PROMPTS:
        return user_hint
    name = dish_name
    rules = [
        ("刺身|鱼生|海鲜杯|北极贝|象拔蚌|松叶蟹|甜虾|海胆", "刺身"),
        ("寿司|饭|丼|塔可|三明治|蛋糕|盒|拼盘", "刺身饭"),
        ("天妇罗|炸|吉列|酥|脆饼", "炸物"),
        ("烤|炙|烧|灸|鳗鱼|鹅肝|牛小排|安格斯", "烤物"),
        ("煮|矶煮|鲍鱼|味噌|汁煮|穴子|塩|盐", "热菜"),
        ("沙拉|沙律|前菜|渍|醋冻|百香果", "前菜"),
        ("淋|浇|酱|渍油|膏|蛋黄", "淋酱"),
        ("卷|手卷|千层|寿司", "寿司"),
        ("雾|干冰|飘雪|霜烫|熟成", "飘雪"),
        ("面|粉|乌冬|拉面|荞麦", "面食"),
        ("饮品|茶|酒|咖啡|苏打", "饮品"),
        ("甜|布丁|雪糕|拿破仑|蛋糕|慕斯", "甜品"),
        ("套餐|拼盘|定食|box|BOX", "套餐"),
        ("氛围|门店|环境|店内|餐厅", "氛围"),
    ]
    for pat, t in rules:
        if re.search(pat, name):
            return t
    return "热菜"  # 默认，最通用


def build_prompt(dish_name, dish_type, style="高级感"):
    type_tip = DISH_TYPE_PROMPTS.get(dish_type, DISH_TYPE_PROMPTS["热菜"])
    style_tip = PROMPT_STYLE
    return f"{dish_name}，{style_tip}，{type_tip}"


def parse_dish_arg(arg):
    """解析 --dish "菜名|路径|类型"。类型可省略。"""
    parts = arg.split("|")
    if len(parts) == 2:
        name, path = parts
        return name.strip(), path.strip(), None
    elif len(parts) >= 3:
        name, path = parts[0].strip(), parts[1].strip()
        return name, path, "|".join(parts[2:]).strip()
    raise ValueError(f"--dish 参数格式错误: {arg}，应为 菜名|路径 或 菜名|路径|类型")


def main():
    ap = argparse.ArgumentParser(description="阶段01·备料：选图+预处理+生成批次清单")
    ap.add_argument("--batch", required=True, help="批次名（英文/数字，如 demo1）")
    ap.add_argument("--dish", action="append", default=[], help='重复传入，格式："菜名|文件夹路径|类型(可选)"')
    ap.add_argument("--csv", help="从CSV读取菜品，格式同 --dish，一行一道")
    ap.add_argument("--store", default="", help="门店名称（出现在成片结尾）")
    ap.add_argument("--city", default="", help="所在城市")
    ap.add_argument("--style", default="高级感", choices=["高级感", "烟火气", "促销引流"])
    ap.add_argument("--n-per-dish", type=int, default=1, help="每道菜选几张（默认1）")
    args = ap.parse_args()

    # 读 CSV
    if args.csv and os.path.exists(args.csv):
        for line in open(args.csv, encoding='utf-8'):
            line = line.strip()
            if not line or line.startswith('#'): continue
            args.dish.append(line)

    if not args.dish:
        print("[错误] 请用 --dish 或 --csv 提供至少 1 道菜")
        sys.exit(1)
    if len(args.dish) < 3:
        print(f"[警告] 仅 {len(args.dish)} 道菜，成片可能太短（建议 5-6 道）")

    batch_dir = BATCHES_DIR / args.batch
    img_dir = batch_dir / "01_images"
    img_dir.mkdir(parents=True, exist_ok=True)

    print(f"📦 批次: {args.batch}")
    print(f"📁 目录: {batch_dir}")
    print(f"🍣 菜数: {len(args.dish)} 道")
    if args.store:
        print(f"🏪 门店: {args.store} ({args.city})")
    print()

    dishes = []
    for idx, darg in enumerate(args.dish, 1):
        name, folder, hint = parse_dish_arg(darg)
        dtype = dish_name_to_type(name, hint)

        print(f"[{idx}/{len(args.dish)}] 第{idx}道 · {name}  [类型:{dtype}]")
        best = pick_best_image(folder)
        if not best:
            print(f"    ❌ 文件夹内无图片: {folder}")
            sys.exit(1)
        print(f"    原图: {os.path.basename(best)}  {os.path.getsize(best)/1024/1024:.1f}MB")

        out_name = f"d{idx:02d}_{name}_9x16.jpg"
        out_path = img_dir / out_name
        final_size = process_image(best, str(out_path))
        size_kb = os.path.getsize(out_path) / 1024
        print(f"    输出: {out_name}  {final_size[0]}x{final_size[1]}  {size_kb:.0f}KB ✓")

        dishes.append({
            "index": idx,
            "name": name,
            "type": dtype,
            "original_image": best,
            "prep_image": str(out_path),
            "prompt": build_prompt(name, dtype, args.style),
            "negative_prompt": NEGATIVE_PROMPT,
        })
        print()

    manifest = {
        "batch": args.batch,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "store": args.store,
        "city": args.city,
        "style": args.style,
        "n_dishes": len(dishes),
        "dishes": dishes,
        "stages": {
            "01_prep": {"done": True, "output_dir": str(img_dir)},
            "02_generate": {"done": False},
            "03_copywriting": {"done": False},
            "04_dub": {"done": False},
            "05_compose": {"done": False},
        }
    }

    manifest_path = batch_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"✅ 备料完成")
    print(f"   批次清单: {manifest_path}")
    print(f"   图片目录: {img_dir}")
    print(f"   提示词预览（第1道）:")
    print(f"   {dishes[0]['prompt'][:80]}...")
    print("=" * 60)


if __name__ == "__main__":
    main()
