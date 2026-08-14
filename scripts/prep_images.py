# -*- coding: utf-8 -*-
"""
图片预处理：大图 → API 可接受尺寸 + 9:16 竖版裁切
==========================================

阿里 wan2.6-i2v-flash 对输入图片的限制（实测）：
  - 长边 ≤ 2048，短边 ≥ 512 （否则会报错或忽略图片）
  - 1080P 输出推荐输入接近 9:16 比例（1080×1920 或其 2/3 倍 720×1280）

本脚本：
  1. 读取原图（支持 jpg/png/佳能 RAW 侧车的 jpg）
  2. 自动判断构图方式 → 9:16 cover_crop 或 letterbox 加背景
  3. 缩放到目标尺寸（默认 720×1280，可设 1080×1920），保证长边 ≤ 1536
  4. 保存为 JPEG (quality=95)

用法：
  # 单张测试
  python scripts/prep_images.py --image "D:/素材库/菜品照片/XXX.jpg" --out "output/"

  # 批量处理某菜品文件夹（取最清晰的 N 张）
  python scripts/prep_images.py --src "D:/素材库/菜品照片/蒲烧鳗鱼" \
                                 --out "pipeline/batches/test/images/" --limit 3

  # 整个素材库预览尺寸分布（不处理，只分析）
  python scripts/prep_images.py --analyze "D:/素材库/菜品照片"
"""
import argparse
import os
import glob
import sys
from pathlib import Path

from PIL import Image, ImageOps, ImageFilter

# ── 常量 ─────────────────────────────────────────────────────────────
TARGET_SHORT = 720   # 目标短边（720×1280，9:16），如要1080p改1080
TARGET_RATIO = 9/16  # 9:16 竖版
MAX_LONG_SIDE = 1536 # API 允许的最大长边（留安全余量，不顶到2048）
JPEG_QUALITY = 95
SHARPEN_AMOUNT = 1.3 # 缩图后轻微锐化，避免模型误判模糊

# 颜色方案：letterbox 时的背景填充色
BKGD_LIGHT = (248, 246, 244)  # 暖米白
BKGD_DARK = (28, 26, 24)       # 深褐黑


def open_image(path):
    """打开图片，处理 EXIF 旋转 + PNG alpha 转白底"""
    im = Image.open(path)
    # EXIF 旋转修正（手机/相机竖拍照片常见）
    im = ImageOps.exif_transpose(im)
    if im.mode in ('RGBA', 'LA'):
        bg = Image.new('RGB', im.size, BKGD_LIGHT)
        bg.paste(im, mask=im.split()[-1])
        im = bg
    elif im.mode != 'RGB':
        im = im.convert('RGB')
    return im


def pick_crop_strategy(w, h):
    """根据原图比例选裁切策略。返回 'cover' 或 'letterbox' 或 'pad_top'。"""
    src_ratio = w / h

    if abs(src_ratio - TARGET_RATIO) < 0.05:
        # 比例已经接近9:16，直接缩放
        return 'cover'

    if src_ratio < TARGET_RATIO:
        # 原图比9:16还"瘦高"（更竖）。宽够宽不够，只能缩放+letterbox上下留白
        return 'letterbox'

    # 原图比9:16"胖"（横图或方图）。9:16 cover_crop 裁上下或取中间
    # 但餐饮图一般主体在中下，所以用 'cover_middle_lower' —— 偏下裁切
    return 'cover_middle_lower'


def crop_to_9_16(im, strategy='cover_middle_lower'):
    """把任意比例的图处理成 9:16。"""
    w, h = im.size
    target_w, target_h = TARGET_SHORT, int(TARGET_SHORT / TARGET_RATIO)
    # target_h = 720 * 16/9 = 1280

    src_ratio = w / h
    want_ratio = target_w / target_h  # 9/16

    if strategy.startswith('cover'):
        # cover：填满不留白，可能裁切
        if abs(src_ratio - want_ratio) < 0.001:
            pass  # 比例对了
        elif src_ratio > want_ratio:
            # 原图更宽 → 左右裁
            new_w = int(h * want_ratio)
            left = (w - new_w) // 2
            im = im.crop((left, 0, left + new_w, h))
        else:
            # 原图更高 → 上下裁
            new_h = int(w / want_ratio)
            if strategy == 'cover_middle_lower':
                # 偏下 1/3：保留中下部分（食物图一般餐盘在中下）
                top = int((h - new_h) * 0.35)  # 顶部留35%（默认50%）
            else:
                top = (h - new_h) // 2
            im = im.crop((0, top, w, top + new_h))
        # 缩到目标尺寸（用 LANCZOS 高质量）
        return im.resize((target_w, target_h), Image.LANCZOS)

    elif strategy == 'letterbox':
        # 原图瘦高（比9:16还瘦），整体缩+左右留白填背景
        new_h = target_h
        new_w = int(w * (target_h / h))
        im = im.resize((new_w, target_h), Image.LANCZOS)

        # 判断主色调深浅选背景色
        # 取四角像素平均判断深浅
        px = im.load()
        cornor_px = [px[0, 0], px[new_w-1, 0], px[0, new_h-1], px[new_w-1, new_h-1]]
        avg_lum = sum((0.299*r + 0.587*g + 0.114*b) for r,g,b in cornor_px) / 4
        bkgd = BKGD_DARK if avg_lum < 128 else BKGD_LIGHT

        canvas = Image.new('RGB', (target_w, target_h), bkgd)
        left = (target_w - new_w) // 2
        canvas.paste(im, (left, 0))
        return canvas

    return im


def enforce_size_limit(im):
    """确保长边不超过 API 限制，短边不小于 512。"""
    w, h = im.size
    long_side = max(w, h)
    short_side = min(w, h)

    if long_side > MAX_LONG_SIDE:
        scale = MAX_LONG_SIDE / long_side
        new_w = int(w * scale)
        new_h = int(h * scale)
        im = im.resize((new_w, new_h), Image.LANCZOS)
        w, h = new_w, new_h

    # 短边太小的话放大（一般不会）
    short_side = min(w, h)
    if short_side < 512:
        scale = 512 / short_side
        new_w = int(w * scale)
        new_h = int(h * scale)
        im = im.resize((new_w, new_h), Image.LANCZOS)

    return im


def sharp(im):
    """轻微锐化，抵消缩略图模糊"""
    return im.filter(ImageFilter.UnsharpMask(radius=1.0, percent=int(SHARPEN_AMOUNT*100), threshold=2))


def process_one(src_path, out_dir, want_1080=False):
    """处理单张图片。返回输出路径或 None。"""
    try:
        im = open_image(src_path)
    except Exception as e:
        print(f'  [跳过] 无法打开 {os.path.basename(src_path)}: {e}')
        return None

    w, h = im.size

    global TARGET_SHORT
    original_short = TARGET_SHORT
    if want_1080:
        TARGET_SHORT = 1080

    strategy = pick_crop_strategy(w, h)
    im = crop_to_9_16(im, strategy)
    im = enforce_size_limit(im)
    im = sharp(im)
    TARGET_SHORT = original_short

    os.makedirs(out_dir, exist_ok=True)
    base = Path(src_path).stem
    out_name = f"{base}_9x16.jpg"
    out_path = os.path.join(out_dir, out_name)
    im.save(out_path, 'JPEG', quality=JPEG_QUALITY, optimize=True)

    final_w, final_h = im.size
    size_kb = os.path.getsize(out_path) / 1024
    tag = {
        'cover_middle_lower': '裁切(偏下)',
        'cover': '直接缩放',
        'letterbox': '留边'
    }.get(strategy, strategy)
    print(f'  [OK] {os.path.basename(src_path):<40} {w}x{h:<12} → {final_w}x{final_h:<10} {size_kb:.0f}KB  {tag}')
    return out_path


def process_folder(src_dir, out_dir, limit=1, want_1080=False):
    """处理文件夹：取 JPEG 质量最佳 / 最大的 N 张。"""
    exts = ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']
    files = []
    for ext in exts:
        files.extend(glob.glob(os.path.join(src_dir, '**', ext), recursive=True))

    if not files:
        print(f'  文件夹 {src_dir} 内无图片')
        return []

    # 按文件大小降序（大图一般清晰度高）
    files.sort(key=lambda f: -os.path.getsize(f))
    picked = files[:limit]

    print(f'\n📁 {os.path.basename(src_dir) or src_dir} （共{len(files)}张，取{len(picked)}张最大的）')
    outs = []
    for f in picked:
        outs.append(process_one(f, out_dir, want_1080))
    return [o for o in outs if o]


def main():
    ap = argparse.ArgumentParser(description='图片预处理：大图压缩+9:16裁切→API可用')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--image', help='单张图片路径')
    g.add_argument('--src', action='append', help='菜品图片文件夹（可重复）')
    g.add_argument('--analyze', help='仅分析尺寸分布，不处理')
    ap.add_argument('--out', default='pipeline/input_images', help='输出目录')
    ap.add_argument('--limit', type=int, default=1, help='每文件夹取几张（默认1）')
    ap.add_argument('--1080', action='store_true', dest='want_1080',
                    help='输出 1080×1920（默认 720×1280，更省带宽，API 内部会升采样）')
    args = ap.parse_args()

    if args.analyze:
        # 分析：直接复用 check_image_sizes 的逻辑
        cmd = f'python scripts/check_image_sizes.py'
        print(f'执行: {cmd}')
        os.system(cmd)
        return

    out_dir = args.out
    print(f'输出目录: {out_dir}')
    print(f'目标比例: 9:16，目标短边: {1080 if args.want_1080 else 720}')
    print()

    if args.image:
        r = process_one(args.image, out_dir, args.want_1080)
        if r:
            print(f'\n完成：{r}')
        else:
            sys.exit(1)
    else:
        all_outs = []
        for s in args.src:
            outs = process_folder(s, out_dir, args.limit, args.want_1080)
            all_outs.extend(outs)
        print(f'\n共处理 {len(all_outs)} 张 → {out_dir}')


if __name__ == '__main__':
    main()
