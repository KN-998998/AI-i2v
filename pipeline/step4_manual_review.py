# -*- coding: utf-8 -*-
"""
Step 4: 生成人工审核清单（HTML 接触表 + CSV）
==============================================

输入：03_clips/ 下的所有视频片段 + manifest.json
输出：04_selected/ 下的审核清单 HTML + CSV

运营打开 HTML 文件，逐道菜查看所有 roll 的视频，
在 CSV 中标记选用的片段（selected 列填 y）。

用法：
  python pipeline/step4_manual_review.py --config pipeline/batch_20260814.yaml
"""
import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import get_batch_dir, batch_subdirs


def get_video_thumbnail(video_path, out_path, time_offset=1.0):
    """用 ffmpeg 截取视频缩略图。"""
    cmd = [
        "ffmpeg", "-y", "-ss", str(time_offset), "-i", video_path,
        "-vframes", "1", "-vf", "scale=270:-1",
        "-q:v", "2", out_path,
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)


def generate_html(clips_data, dirs):
    """生成审核清单 HTML 页面。"""
    # 按菜品分组
    dishes = {}
    for clip in clips_data:
        if clip["status"] != "ok":
            continue
        dish = clip["dish"]
        if dish not in dishes:
            dishes[dish] = []
        dishes[dish].append(clip)

    html_parts = ["""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>视频片段审核清单</title>
<style>
  body { font-family: "Microsoft YaHei", sans-serif; background: #1a1a1a; color: #eee; margin: 20px; }
  h1 { color: #ff6b35; }
  h2 { color: #ffd700; border-bottom: 1px solid #444; padding-bottom: 8px; margin-top: 30px; }
  .dish-section { margin-bottom: 40px; }
  .clips { display: flex; flex-wrap: wrap; gap: 20px; }
  .clip-card { background: #2a2a2a; border-radius: 8px; padding: 12px; width: 300px; }
  .clip-card video { width: 100%; border-radius: 4px; }
  .clip-info { margin-top: 8px; font-size: 13px; color: #aaa; }
  .clip-name { color: #fff; font-weight: bold; }
  .badge { display: inline-block; background: #ff6b35; color: #fff; padding: 2px 8px;
           border-radius: 12px; font-size: 11px; margin-left: 8px; }
  .instructions { background: #2a2a2a; padding: 16px; border-radius: 8px; margin-bottom: 20px;
                  border-left: 4px solid #ff6b35; }
</style>
</head>
<body>
<h1>视频片段审核清单</h1>
<div class="instructions">
  <p><b>操作说明：</b></p>
  <p>1. 逐道菜查看下方的视频片段（每菜 2-3 个 roll）</p>
  <p>2. 参考 <a href="checklist.csv" style="color:#ff6b35">checklist.csv</a>，
     在 selected 列填 <code>y</code> 标记选用片段</p>
  <p>3. 质检标准：食物无变形、动态在前3秒内发生、无文字扭曲、色调协调</p>
  <p>4. 填好后保存 CSV，然后运行 step5 合成成片</p>
</div>
"""]

    for dish, clips in dishes.items():
        html_parts.append(f'<div class="dish-section">')
        html_parts.append(f'<h2>{dish} <span class="badge">{len(clips)} 个片段</span></h2>')
        html_parts.append(f'<div class="clips">')
        for clip in clips:
            video_path = clip["output"]
            video_name = os.path.basename(video_path)
            # 生成缩略图
            thumb_name = video_name.replace(".mp4", "_thumb.jpg")
            thumb_path = str(dirs["selected"] / thumb_name)
            try:
                get_video_thumbnail(video_path, thumb_path)
            except Exception:
                thumb_path = ""

            html_parts.append(f"""
            <div class="clip-card">
              <video controls preload="metadata">
                <source src="../03_clips/{video_name}" type="video/mp4">
              </video>
              <div class="clip-info">
                <div class="clip-name">{clip.get('roll', '?')}号片段</div>
                <div>文件: {video_name}</div>
              </div>
            </div>""")
        html_parts.append("</div></div>")

    html_parts.append("</body></html>")

    html_path = dirs["selected"] / "review.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))
    return html_path


def generate_csv(clips_data, dirs):
    """生成审核 CSV 清单。"""
    csv_path = dirs["selected"] / "checklist.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["dish", "roll", "filename", "selected", "notes"])
        for clip in clips_data:
            if clip["status"] != "ok":
                continue
            writer.writerow([
                clip["dish"],
                clip.get("roll", ""),
                os.path.basename(clip["output"]),
                "",  # 运营填写 y
                "",  # 备注
            ])
    return csv_path


def run(config_path: str):
    """主入口。"""
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    batch_date = cfg["batch"]["date"]
    batch_dir = get_batch_dir(batch_date)
    dirs = batch_subdirs(batch_dir)

    manifest_path = dirs["clips"] / "manifest.json"
    if not manifest_path.exists():
        print("[错误] 请先运行 step3 生成视频片段")
        sys.exit(1)

    with open(manifest_path, encoding="utf-8") as f:
        clips_data = json.load(f)

    ok_clips = [c for c in clips_data if c["status"] == "ok"]
    dishes = set(c["dish"] for c in ok_clips)

    print(f"{'='*60}")
    print(f"Step 4: 生成人工审核清单")
    print(f"  视频片段: {len(ok_clips)} 个")
    print(f"  菜品数: {len(dishes)}")
    print(f"{'='*60}")

    html_path = generate_html(ok_clips, dirs)
    csv_path = generate_csv(ok_clips, dirs)

    print(f"\n  HTML 清单: {html_path}")
    print(f"  CSV 清单: {csv_path}")
    print(f"\n  请打开 HTML 文件审核视频，在 CSV 中标记选用的片段")
    print(f"  审核完成后运行 step5 合成成片")
    print(f"{'='*60}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Step 4: 生成人工审核清单")
    ap.add_argument("--config", required=True, help="batch.yaml 路径")
    args = ap.parse_args()
    run(args.config)
