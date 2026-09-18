#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一批已发布的参考片量成一份画像（reference_profile.json）。

用法：
    python3 scripts/analyze_reference_videos.py ig视频效果 -o docs/reference_profile.json

画像是 B 层「参考相似度」的标尺：成片和这份画像比，算出 0–100 的像不像。
参考片换了就重跑一次，不用改代码。

刻意只依赖 ffmpeg/ffprobe + cv2 + numpy，都是项目已有的东西。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v"}
FRAME_WIDTH = 180          # 统计尺度，和 canvas_quality 的逐帧检查保持一致
MAX_SAMPLED_FRAMES = 240   # 10 秒 30fps 是 300 帧，取样到这个上限就够
SCENE_THRESHOLD = 0.30     # ffmpeg 场景切换分数，超过算一个新镜头
AUDIO_WINDOW_SECONDS = 0.5


def _run(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return result.returncode, f"{result.stdout}\n{result.stderr}"


def probe(path: Path) -> dict[str, Any]:
    code, output = _run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    if code != 0:
        return {}
    try:
        return json.loads(output.split("\n")[0] or "{}")
    except json.JSONDecodeError:
        try:
            return json.loads(output[: output.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            return {}


def shot_boundaries(path: Path, duration: float) -> list[float]:
    """用 ffmpeg 的场景切换分数找镜头切点，返回每个镜头的时长。"""
    code, output = _run([
        "ffmpeg", "-hide_banner", "-v", "info", "-i", str(path),
        "-filter:v", f"select='gt(scene,{SCENE_THRESHOLD})',showinfo", "-an", "-f", "null", "-",
    ])
    if code != 0:
        return [duration] if duration > 0 else []
    times = sorted({round(float(value), 3) for value in re.findall(r"pts_time:([0-9]+\.?[0-9]*)", output)})
    cuts = [value for value in times if 0.2 < value < duration - 0.2]
    marks = [0.0, *cuts, duration]
    return [round(marks[i + 1] - marks[i], 3) for i in range(len(marks) - 1)]


def sample_frames(path: Path) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """返回（灰度帧, 彩色帧）两份等长的采样，都缩到 180px 宽。"""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return [], []
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    stride = max(1, total // MAX_SAMPLED_FRAMES) if total > MAX_SAMPLED_FRAMES else 1
    grays: list[np.ndarray] = []
    colors: list[np.ndarray] = []
    index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index % stride == 0:
                height, width = frame.shape[:2]
                if width < 2:
                    break
                scale = FRAME_WIDTH / float(width)
                small = cv2.resize(frame, (FRAME_WIDTH, max(2, int(round(height * scale)))), interpolation=cv2.INTER_AREA)
                colors.append(small)
                grays.append(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
            index += 1
    finally:
        capture.release()
    return grays, colors


def motion_median(grays: list[np.ndarray]) -> float:
    pairs = len(grays) - 1
    if pairs < 1:
        return 0.0
    step = max(1, pairs // 48)
    values = []
    for index in range(0, pairs, step):
        flow = cv2.calcOpticalFlowFarneback(grays[index], grays[index + 1], None, 0.5, 3, 15, 3, 5, 1.2, 0)
        values.append(float(np.mean(np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2))))
    return float(np.median(values)) if values else 0.0


def brightness_and_saturation(colors: list[np.ndarray]) -> tuple[float, float]:
    if not colors:
        return 0.0, 0.0
    luma = []
    saturation = []
    for frame in colors:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        luma.append(float(np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))))
        saturation.append(float(np.mean(hsv[..., 1])))
    return float(np.mean(luma)), float(np.mean(saturation))


def has_fade_in(grays: list[np.ndarray]) -> bool:
    """开头几帧明显比之后暗 = 淡入。参考片是 2 帧黑场起。"""
    if len(grays) < 8:
        return False
    head = float(np.mean(grays[0]))
    body = float(np.median([np.mean(frame) for frame in grays[4:12]]))
    return head < body * 0.5


def has_end_card(grays: list[np.ndarray]) -> bool:
    """结尾有一段明显更暗、且几乎不动的画面 = 黑底信息卡。"""
    if len(grays) < 12:
        return False
    tail = grays[-6:]
    body = float(np.median([np.mean(frame) for frame in grays[: -6]]))
    tail_luma = float(np.mean([np.mean(frame) for frame in tail]))
    tail_motion = float(np.mean([np.mean(cv2.absdiff(tail[i], tail[i + 1])) for i in range(len(tail) - 1)]))
    return tail_luma < body * 0.6 and tail_motion < 2.0


def audio_levels(path: Path) -> dict[str, Any]:
    """解出单声道 PCM，按 0.5 秒窗口算 RMS(dB)，给出整体和起伏。"""
    code, _ = _run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)])
    if code != 0:
        return {"hasAudio": False}
    process = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True, check=False,
    )
    if process.returncode != 0 or not process.stdout:
        return {"hasAudio": False}
    samples = np.frombuffer(process.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    window = int(16000 * AUDIO_WINDOW_SECONDS)
    if samples.size < window:
        return {"hasAudio": False}
    usable = samples[: samples.size - samples.size % window].reshape(-1, window)
    rms = np.sqrt(np.mean(usable ** 2, axis=1))
    db = 20 * np.log10(np.maximum(rms, 1e-6))
    return {"hasAudio": True, "rmsDb": round(float(np.mean(db)), 2), "rmsStdDb": round(float(np.std(db)), 2)}


def analyze(path: Path) -> dict[str, Any]:
    payload = probe(path)
    video = next((item for item in payload.get("streams", []) if item.get("codec_type") == "video"), {})
    try:
        duration = float((payload.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    shots = shot_boundaries(path, duration)
    grays, colors = sample_frames(path)
    luma, saturation = brightness_and_saturation(colors)
    return {
        "file": path.name,
        "durationSeconds": round(duration, 3),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "shotCount": len(shots),
        "medianShotSeconds": round(float(np.median(shots)), 3) if shots else 0.0,
        "motionMedian": round(motion_median(grays), 4),
        "brightness": round(luma, 2),
        "saturation": round(saturation, 2),
        "hasFadeIn": has_fade_in(grays),
        "hasEndCard": has_end_card(grays),
        **audio_levels(path),
    }


def _band(values: list[float], low: float = 10, high: float = 90) -> dict[str, float]:
    array = np.array(values, dtype=float)
    return {
        "p10": round(float(np.percentile(array, low)), 3),
        "median": round(float(np.median(array)), 3),
        "p90": round(float(np.percentile(array, high)), 3),
    }


def build_profile(records: list[dict[str, Any]]) -> dict[str, Any]:
    with_audio = [item for item in records if item.get("hasAudio")]
    return {
        "sampleCount": len(records),
        "durationSeconds": _band([item["durationSeconds"] for item in records]),
        "shotCount": _band([item["shotCount"] for item in records]),
        "medianShotSeconds": _band([item["medianShotSeconds"] for item in records]),
        "motionMedian": _band([item["motionMedian"] for item in records]),
        "brightness": _band([item["brightness"] for item in records]),
        "saturation": _band([item["saturation"] for item in records]),
        "fadeInRatio": round(sum(1 for item in records if item["hasFadeIn"]) / max(1, len(records)), 3),
        "endCardRatio": round(sum(1 for item in records if item["hasEndCard"]) / max(1, len(records)), 3),
        "audioRmsDb": _band([item["rmsDb"] for item in with_audio]) if with_audio else None,
        "audioRmsStdDb": _band([item["rmsStdDb"] for item in with_audio]) if with_audio else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="把参考片量成 reference_profile.json")
    parser.add_argument("folder", help="存放参考片的文件夹")
    parser.add_argument("-o", "--output", default="docs/reference_profile.json")
    args = parser.parse_args()

    folder = Path(args.folder).expanduser()
    videos = sorted(path for path in folder.iterdir() if path.suffix.lower() in VIDEO_SUFFIXES) if folder.is_dir() else []
    if not videos:
        print(f"{folder} 里没有找到视频", file=sys.stderr)
        return 1

    records = []
    for path in videos:
        record = analyze(path)
        records.append(record)
        print(
            f"{record['file'][:36]:38s} {record['durationSeconds']:6.2f}s  镜头 {record['shotCount']:2d}"
            f"  中位 {record['medianShotSeconds']:5.2f}s  运动 {record['motionMedian']:6.3f}"
            f"  亮 {record['brightness']:6.2f}  饱和 {record['saturation']:6.2f}"
            f"  淡入 {'有' if record['hasFadeIn'] else '无'}  片尾卡 {'有' if record['hasEndCard'] else '无'}"
            f"  音量 {record.get('rmsDb', float('nan')):6.2f}dB±{record.get('rmsStdDb', float('nan')):.2f}"
        )

    profile = {"clips": records, "profile": build_profile(records)}
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n画像已写入 {output}")
    print(json.dumps(profile["profile"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
