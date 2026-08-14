# -*- coding: utf-8 -*-
"""检查素材库图片尺寸分布

用法：
  python scripts/check_image_sizes.py <素材库根目录> [<更多目录>...]
"""
from PIL import Image
import os, glob, sys

folders = sys.argv[1:] if len(sys.argv) > 1 else ['.']
if not folders:
    print("用法: python check_image_sizes.py <目录1> [目录2] ...")
    sys.exit(1)

exts = ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']
imgs = []
for f in folders:
    for ext in exts:
        imgs.extend(glob.glob(os.path.join(f, '**', ext), recursive=True))

print(f'共找到 {len(imgs)} 张图片')
print()

stats = {'<1024': 0, '1024-2048': 0, '>2048': 0, '>3000': 0, '>4000': 0}
sizes = []
for p in imgs:
    try:
        with Image.open(p) as im:
            w, h = im.size
            long_side = max(w, h)
            sizes.append((long_side, w, h, p))
            if long_side < 1024: stats['<1024'] += 1
            elif long_side <= 2048: stats['1024-2048'] += 1
            elif long_side <= 3000: stats['>2048'] += 1
            elif long_side <= 4000: stats['>3000'] += 1
            else: stats['>4000'] += 1
    except Exception as e:
        print(f'打开失败 {p}: {e}')

print('{:<16} {:<8} 占比'.format('长边范围', '张数'))
print('-' * 40)
total = len(sizes)
for k, v in stats.items():
    pct = '{:.1f}%'.format(v/total*100) if total else '0%'
    print('{:<16} {:<8} {}'.format(k, v, pct))
print('{:<16} {:<8}'.format('合计', total))
print()

big = [s for s in sizes if s[0] > 2048]
if big:
    print(f'超过 2048 长边的共 {len(big)} 张，前 20 张:')
    for long_side, w, h, p in sorted(big, reverse=True)[:20]:
        name = os.path.relpath(p, folders[0])
        if len(name) > 57: name = '...' + name[-54:]
        print(f'  {long_side:<8} {w}x{h:<14}  {name}')
    print()
    print(f'最大的 10 张:')
    for long_side, w, h, p in sorted(sizes, reverse=True)[:10]:
        name = os.path.relpath(p, folders[0])
        if len(name) > 57: name = '...' + name[-54:]
        print(f'  {long_side:<8} {w}x{h:<14}  {name}')
else:
    print('所有图片长边均 ≤ 2048')
