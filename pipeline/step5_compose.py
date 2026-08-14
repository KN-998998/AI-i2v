# -*- coding: utf-8 -*-
"""
Step 5: 人工精选片段 → ffmpeg 合成无声成片
==========================================

输入：04_selected/checklist.csv（运营标记了 selected=y 的片段）
输出：05_composed/ 下的无声成片 MP4（10-12s, 1080x1920, 30fps）

合成逻辑：
  1. 读取 CSV 获取每道菜选用的片段
  2. 按 batch.yaml 中的视频编排组合菜品
  3. 每段掐头去尾保留 2-3s 动态最强部分
  4. 硬切拼接 + 字幕叠加 + 片尾 CTA
  5. 输出无声成片

用法：
  python pipeline/step5_compose.py --config pipeline/batch_20260814.yaml
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
from pipeline.config import (
    TEMPLATE_5_DISH, TEMPLATE_3_DISH,
    FINAL_RESOLUTION, FINAL_FPS,
    get_batch_dir, batch_subdirs,
)


def read_selected_clips(csv_path: str) -> dict:
    """读取 CSV，返回 {菜名: 视频文件名}。"""
    selected = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["selected"].strip().lower() in ("y", "yes", "1", "true"):
                selected[row["dish"]] = row["filename"]
    return selected


def read_subtitles(prompts_dir: Path) -> dict:
    """读取每道菜的字幕文案。"""
    subtitles = {}
    for f in prompts_dir.glob("*_meta.json"):
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
            subtitles[data["dish"]] = data.get("subtitle", data["dish"])
    return subtitles


def trim_clip(clip_path, out_path, start=0.5, duration=3.0):
    """用 ffmpeg 截取片段的动态最强部分，统一缩放到 1080x1920。"""
    w, h = FINAL_RESOLUTION
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start), "-i", clip_path,
        "-t", str(duration),
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
        "-r", str(FINAL_FPS),
        "-an",  # 无声
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"  [ffmpeg] {result.stderr[-300:]}")
    return out_path


def concat_clips(clip_paths, out_path, subtitles=None, brand_info=None):
    """拼接多个片段 + 叠加字幕 + 片尾 CTA。"""
    w, h = FINAL_RESOLUTION

    # 生成 concat 文件列表
    list_path = out_path + ".txt"
    with open(list_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    # 构建字幕滤镜（drawtext）
    filters = []
    if subtitles:
        for i, text in enumerate(subtitles):
            if not text:
                continue
            # 在每个片段底部居中显示字幕
            # 使用 escape 避免特殊字符问题
            safe_text = text.replace(":", r"\:").replace("'", r"'\''")
            # 简化：所有字幕统一叠加在底部
            start_time = sum(subtitles[j]["duration"] for j in range(i))
            end_time = start_time + subtitles[i]["duration"]
            filters.append(
                f"drawtext=text='{safe_text}':"
                f"fontfile='C\\\\:/Windows/Fonts/msyh.ttc':"
                f"fontsize=42:fontcolor=white:borderw=2:bordercolor=black@0.8:"
                f"x=(w-text_w)/2:y=h-80:"
                f"enable='between(t,{start_time},{end_time})'"
            )

    # 片尾 CTA
    if brand_info:
        cta_text = f"{brand_info.get('name','')} | {brand_info.get('cta','')}"
        safe_cta = cta_text.replace(":", r"\:").replace("'", r"'\''")
        total_duration = sum(s["duration"] for s in subtitles) if subtitles else 10
        filters.append(
            f"drawtext=text='{safe_cta}':"
            f"fontfile='C\\\\:/Windows/Fonts/msyh.ttc':"
            f"fontsize=52:fontcolor=#FFD700:borderw=3:bordercolor=black@0.9:"
            f"x=(w-text_w)/2:y=h-120:"
            f"enable='gte(t,{total_duration - 2})'"
        )

    # 执行拼接
    vf_arg = ",".join(filters) if filters else None

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", list_path,
    ]
    if vf_arg:
        cmd.extend(["-vf", vf_arg])
    cmd.extend([
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-r", str(FINAL_FPS),
        "-an",
        out_path,
    ])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  [ffmpeg concat] {result.stderr[-500:]}")

    # 清理临时文件
    if os.path.exists(list_path):
        os.remove(list_path)

    return out_path


def compose_video(video_cfg, selected_clips, clips_dir, subtitles, brand_info,
                  dirs, template):
    """合成单条视频。"""
    vid = video_cfg["id"]
    dish_names = video_cfg["dishes"]
    hook_dish = video_cfg.get("hook_dish", dish_names[0])

    # 按 hook 顺序排列菜品
    ordered = list(dish_names)
    if hook_dish in ordered:
        ordered.remove(hook_dish)
        ordered.insert(0, hook_dish)

    # 获取模板段时长
    segments = template["segments"]
    seg_durations = [s["duration"] for s in segments if s["role"] != "outro"]
    outro_duration = [s["duration"] for s in segments if s["role"] == "outro"]
    outro_duration = outro_duration[0] if outro_duration else 2.0

    # 截取每道菜的片段
    trimmed_paths = []
    vid_subtitles = []
    for i, dish in enumerate(ordered):
        if dish not in selected_clips:
            print(f"  [跳过] {dish} 无选用片段")
            continue
        clip_file = selected_clips[dish]
        clip_path = str(clips_dir / clip_file)
        if not os.path.exists(clip_path):
            print(f"  [跳过] {clip_file} 不存在")
            continue

        duration = seg_durations[i] if i < len(seg_durations) else 2.0
        trimmed_name = f"{vid}_{dish}_trim.mp4"
        trimmed_path = str(dirs["composed"] / trimmed_name)
        trim_clip(clip_path, trimmed_path, start=0.5, duration=duration)
        trimmed_paths.append(trimmed_path)
        vid_subtitles.append({
            "text": subtitles.get(dish, dish),
            "duration": duration,
        })

    if not trimmed_paths:
        print(f"  [错误] {vid} 无可用片段")
        return None

    # 拼接 + 字幕 + CTA
    out_name = f"{vid}_composed.mp4"
    out_path = str(dirs["composed"] / out_name)
    concat_clips(trimmed_paths, out_path, vid_subtitles, brand_info)

    # 清理临时片段
    for p in trimmed_paths:
        if os.path.exists(p):
            os.remove(p)

    return out_path


def run(config_path: str):
    """主入口。"""
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    batch_date = cfg["batch"]["date"]
    batch_dir = get_batch_dir(batch_date)
    dirs = batch_subdirs(batch_dir)

    csv_path = dirs["selected"] / "checklist.csv"
    if not csv_path.exists():
        print("[错误] 请先运行 step4 生成审核清单，并在 CSV 中标记选用片段")
        sys.exit(1)

    selected_clips = read_selected_clips(str(csv_path))
    subtitles = read_subtitles(dirs["prompts"])
    brand_info = cfg.get("brand", {})
    videos = cfg.get("videos", [])

    print(f"{'='*60}")
    print(f"Step 5: ffmpeg 合成无声成片")
    print(f"  选用片段: {len(selected_clips)} 道菜")
    print(f"  视频编排: {len(videos)} 条")
    print(f"  输出: {dirs['composed']}")
    print(f"{'='*60}")

    results = []
    for i, video_cfg in enumerate(videos, 1):
        vid = video_cfg["id"]
        vtype = video_cfg["type"]
        template_key = video_cfg.get("template", "5_dish")
        template = TEMPLATE_5_DISH if template_key == "5_dish" else TEMPLATE_3_DISH

        print(f"\n[{i}/{len(videos)}] {vid} ({vtype})")

        if vtype == "variant":
            # 变体：基于基础视频，换文案/顺序
            base_id = video_cfg.get("base", "")
            swaps = video_cfg.get("swap", [])
            # 找到基础视频的菜品列表，做顺序调整
            base_video = next((v for v in videos if v["id"] == base_id), None)
            if base_video:
                dish_names = base_video["dishes"]
                if "顺序" in swaps and len(dish_names) > 1:
                    # 反转顺序作为变体
                    dish_names = list(reversed(dish_names))
                video_cfg = {**video_cfg, "dishes": dish_names}

        out_path = compose_video(
            video_cfg, selected_clips, dirs["clips"],
            subtitles, brand_info, dirs, template,
        )

        if out_path:
            size = os.path.getsize(out_path) / 1024 / 1024
            print(f"  [完成] {out_path} ({size:.1f}MB)")
            results.append({"id": vid, "status": "ok", "output": out_path})
        else:
            results.append({"id": vid, "status": "failed"})

    manifest_path = dirs["composed"] / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n{'='*60}")
    print(f"完成: {ok}/{len(videos)} 条视频合成成功")
    print(f"清单: {manifest_path}")
    print(f"{'='*60}")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Step 5: ffmpeg 合成无声成片")
    ap.add_argument("--config", required=True, help="batch.yaml 路径")
    args = ap.parse_args()
    run(args.config)
