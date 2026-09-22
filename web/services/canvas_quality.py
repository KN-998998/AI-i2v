# -*- coding: utf-8 -*-
"""Local media analysis and deterministic canvas preflight checks."""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

from pipeline.config import FINAL_DURATION_RANGE
from web.services.canvas_state import draft_directory, uploaded_file

_CATEGORIES = {"寿司", "刺身", "前菜/小菜", "炸物", "主菜", "主食", "汤品", "甜品", "水果", "饮品", "套餐", "其他"}
_LEGACY_CATEGORY_MAP = {"正餐": "主菜", "小吃": "前菜/小菜"}
_FRUIT_KEYWORDS = ("蜜瓜", "草莓", "西瓜", "芒果", "葡萄", "蓝莓", "树莓", "樱桃", "桃", "梨", "苹果", "橙", "柚", "柠檬")
_DESSERT_KEYWORDS = ("蛋糕", "布丁", "冰淇淋", "甜点", "甜品", "慕斯", "奶油", "铜锣烧", "抹茶", "芝士")
_SNACK_KEYWORDS = ("天妇罗", "炸", "串", "薯", "饼", "小吃")
_DRINK_KEYWORDS = ("饮料", "果汁", "咖啡", "茶", "酒", "汽水", "苏打")


def infer_category(name: str, explicit: str | None = None) -> str:
    if explicit in _LEGACY_CATEGORY_MAP:
        return _LEGACY_CATEGORY_MAP[explicit]
    if explicit in _CATEGORIES:
        return explicit
    normalized = str(name or "").strip().lower()
    if any(keyword in normalized for keyword in _FRUIT_KEYWORDS):
        return "水果"
    if any(keyword in normalized for keyword in _DESSERT_KEYWORDS):
        return "甜品"
    if any(keyword in normalized for keyword in _DRINK_KEYWORDS):
        return "饮品"
    if any(keyword in normalized for keyword in _SNACK_KEYWORDS):
        return "前菜/小菜"
    return "其他"


def _quality_label(score: int) -> str:
    if score >= 80:
        return "good"
    if score >= 60:
        return "warning"
    return "reject"


def analyze_image(path: str | Path, dish_name: str = "", category: str | None = None) -> dict[str, Any]:
    """Score image usability with local image statistics, not semantic AI."""
    image_path = Path(path)
    warnings: list[str] = []
    try:
        with Image.open(image_path) as image:
            image.load()
            width, height = image.size
            gray = image.convert("L").resize((256, 256))
            brightness = float(ImageStat.Stat(gray).mean[0])
            contrast = float(ImageStat.Stat(gray).stddev[0])
            edge_mean = float(ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0])
            image_format = image.format or image_path.suffix.lstrip(".").upper()
    except (OSError, ValueError) as exc:
        return {
            "kind": "image",
            "analysisMode": "local_rules",
            "qualityScore": 0,
            "qualityLabel": "reject",
            "qualityWarnings": [f"图片无法读取：{exc}"],
            "category": infer_category(dish_name, category),
        }

    score = 100
    ratio = width / max(height, 1)
    if min(width, height) < 720:
        score -= 20
        warnings.append("图片分辨率偏低，建议至少使用 720 像素短边")
    if abs(ratio - (9 / 16)) > 0.12:
        score -= 12
        warnings.append("图片比例不是 9:16，生成前会进行裁切或补边")
    if brightness < 30 or brightness > 235:
        score -= 15
        warnings.append("图片整体过暗或过曝")
    if contrast < 12:
        score -= 10
        warnings.append("图片对比度较低，菜品主体可能不突出")
    if edge_mean < 3:
        score -= 10
        warnings.append("图片边缘细节较少，可能存在失焦")
    if image_path.stat().st_size < 10 * 1024:
        score -= 10
        warnings.append("图片文件过小，可能是低质量缩略图")

    return {
        "kind": "image",
        "analysisMode": "local_rules",
        "qualityScore": max(0, min(100, int(round(score)))),
        "qualityLabel": _quality_label(max(0, min(100, int(round(score))))),
        "qualityWarnings": warnings,
        "category": infer_category(dish_name, category),
        "width": width,
        "height": height,
        "aspectRatio": round(ratio, 4),
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "format": image_format,
    }


def _probe_media(path: Path) -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            return None
        payload = json.loads(result.stdout or "{}")
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
        return None


def _run_ffmpeg_check(path: Path, video_filter: str | None = None, level: str = "error") -> tuple[int, str]:
    command = ["ffmpeg", "-hide_banner", "-v", level, "-i", str(path)]
    if video_filter:
        command.extend(["-vf", video_filter])
    command.extend(["-map", "0:v:0", "-an", "-f", "null", os.devnull])
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            check=False,
        )
        return result.returncode, f"{result.stdout}\n{result.stderr}"
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, str(exc)


def _timing_and_freeze_checks(path: Path) -> dict[str, Any]:
    """Check source timing before render; normalization happens in trim_clip."""
    _, timing_output = _run_ffmpeg_check(path, "vfrdet", level="info")
    vfr_match = re.findall(r"VFR:\s*([0-9]+(?:\.[0-9]+)?)", timing_output)
    try:
        vfr_ratio = max(float(value) for value in vfr_match) if vfr_match else 0.0
    except ValueError:
        vfr_ratio = 0.0

    _, freeze_output = _run_ffmpeg_check(path, "freezedetect=n=-60dB:d=0.25", level="info")
    freeze_matches = re.findall(r"freeze_duration:\s*([0-9]+(?:\.[0-9]+)?)", freeze_output)
    try:
        max_freeze_seconds = max(float(value) for value in freeze_matches) if freeze_matches else 0.0
    except ValueError:
        max_freeze_seconds = 0.0

    decode_code, _ = _run_ffmpeg_check(path)
    return {
        "vfrRatio": round(vfr_ratio, 4),
        "maxFreezeSeconds": round(max_freeze_seconds, 3),
        "decodeOk": decode_code == 0,
    }


# ---------------------------------------------------------------------------
# A 层：单片段硬伤，自动判「建议重做」
#
# 阈值没有照搬 IG 参考片的统计，照搬会把正常片段全判死。参考片是有剪辑点的蒙太奇，
# 这里要判的是一条 3 秒单镜头 AI 片段，两者的数字根本不是一回事：同样是「逐帧亮度
# 差的标准差」，参考片是 2–12（剪辑点造成的跳变），工具生成的片段只有 0.03–0.20。
#
# 下面每个阈值都在真实素材上标定过：10 条工具已生成的片段，外加 4 条用 ffmpeg
# 合成的对照片（2026-09-18 实测，画面统一缩到 180px 宽的灰度图上统计）——
#
#   合成·完全静止（一张图撑 3 秒）    帧差 0.001   闪烁 0.001   边缘相关 1.000
#   合成·只有 ±2px 抖动               帧差 0.009   闪烁 0.015   边缘相关 1.000
#   合成·提示词想要的慢推近 8%        帧差 1.479   闪烁 0.075   边缘相关 0.951
#   合成·慢推近叠加亮度跳变           帧差 13.22   闪烁 22.01   边缘相关 0.993
#   真实·10 条已生成片段              帧差 0.075–2.28  闪烁 0.03–0.20  边缘相关 0.04–1.00
#
# 其中边缘相关 0.040 那条经目视确认确实是废片：末帧右侧长出了一片原本不存在的绿叶。
#
# 光流（motionMean）和首末帧 ORB 匹配率（subjectMatchRatio）只记录数值、不参与扣分。
# 实测这两项分不开「主体动得多」和「主体变形」：真实片段的 ORB 匹配率在 0.01–0.90
# 之间乱跳，而提示词想要的慢推近本身就只有 0.43。等有了人工标注的废片样本再回来定。
# ---------------------------------------------------------------------------
_ANALYSIS_FRAME_WIDTH = 180        # 统计尺度，和当初分析 IG 参考片时一致
_ANALYSIS_MAX_FRAMES = 150         # 3 秒 30fps 是 90 帧，够覆盖全片段
_ANALYSIS_MAX_FLOW_PAIRS = 24      # 光流只抽样算，够给排序用
_FROZEN_FRAME_DELTA = 0.05         # 相邻帧平均绝对差（0-255）低于此值 = 画面完全没动
_WEAK_FRAME_DELTA = 0.30           # 介于两者之间 = 动得很轻微，只提醒不判重做
_FLICKER_STD = 3.0                 # 逐帧亮度一阶差分标准差，真实片段最高只有 0.20
_EDGE_CORRELATION = 0.60           # 首末帧四边 8% 区域的直方图相关，低于此值 = 边缘长出新东西
_FREEZE_REDO_SECONDS = 1.0         # 连续静止到这个长度就不只是提醒了


# ---------------------------------------------------------------------------
# 成片节奏：每段默认只用「动得最多」的那一小段
#
# 11 条已发布参考片量下来，单镜头时长中位 1.53 秒、四分位 0.98–1.98
# （docs/reference_profile.json）。工具原来把 3 秒片段固定按 0.5 → 3.0 用掉 2.5 秒，
# 比参考片拖得明显。取 1.8 秒落在四分位带的上沿：跟得上参考片的节奏，又不至于
# 短到看不清是什么菜。这只是个默认值，人在第 5 步仍然可以手动改裁剪区间。
# ---------------------------------------------------------------------------
TARGET_CLIP_SECONDS = 1.8   # 参考片单镜头中位 1.53s，四分位 0.98–1.98（docs/reference_profile.json）


def _best_motion_window(deltas: list[float], fps: float, window_seconds: float) -> tuple[float, float]:
    """在逐帧差上滑窗，找出动得最多的一段，返回（起点秒, 终点秒）。

    deltas[i] 是第 i 帧与第 i+1 帧的平均绝对差，比帧数少 1，所以片段总长按
    (len(deltas) + 1) / fps 算。并列时取最靠前的一段：同一个片段重复分析必须给出
    同一个答案，否则重新生成一次时间线就会莫名其妙地跳。
    """
    total_seconds = (len(deltas) + 1) / fps
    if total_seconds <= window_seconds:
        # 片段本身还没窗口长，整段用完，别切出个更短的来。
        return 0.0, round(total_seconds, 3)
    span = max(1, min(len(deltas), int(round(window_seconds * fps))))
    best_index = 0
    best_sum = sum(deltas[:span])
    for index in range(1, len(deltas) - span + 1):
        # 逐窗重新求和而不是滚动加减：最多 150 帧，代价可以忽略，
        # 而滚动累加的浮点误差会让「全片动得一样多」这种并列悄悄漂到后面去。
        current = sum(deltas[index:index + span])
        if current > best_sum:
            best_sum, best_index = current, index
    start = best_index / fps
    return round(start, 3), round(min(start + window_seconds, total_seconds), 3)


def _frame_diagnostics(path: Path) -> dict[str, Any]:
    """逐帧统计 A 层用到的几个数。cv2 和 numpy 已在 requirements 里，不引入新依赖。"""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return {"frameChecksOk": False}
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return {"frameChecksOk": False}
    frames: list[Any] = []
    fps = 0.0
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        while len(frames) < _ANALYSIS_MAX_FRAMES:
            ok, frame = capture.read()
            if not ok:
                break
            height, width = frame.shape[:2]
            if width < 2 or height < 2:
                break
            # 立刻缩小再留下，否则 1080p 的 90 帧会占几百 MB 内存。
            scale = _ANALYSIS_FRAME_WIDTH / float(width)
            small = cv2.resize(frame, (_ANALYSIS_FRAME_WIDTH, max(2, int(round(height * scale)))), interpolation=cv2.INTER_AREA)
            frames.append(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
    except cv2.error:
        return {"frameChecksOk": False}
    finally:
        capture.release()
    if len(frames) < 3:
        return {"frameChecksOk": False}

    try:
        deltas = [float(np.mean(cv2.absdiff(frames[i], frames[i + 1]))) for i in range(len(frames) - 1)]
        frame_delta = float(np.median(deltas))
        means = np.array([float(np.mean(frame)) for frame in frames])
        flicker = float(np.std(np.diff(means)))
        motion = _optical_flow_mean(cv2, np, frames)
        match_ratio = _subject_match_ratio(cv2, frames)
        edge = _edge_correlation(cv2, frames)
        # 顺手把「动得最多的 1.8 秒」算出来：逐帧差这一趟已经跑完了，白算一遍太亏。
        # 有的容器读不出帧率（拿到 0 甚至负数），生成出来的片段都是 30fps，按 30 兜底。
        window_start, window_end = _best_motion_window(deltas, fps if fps > 0 else 30.0, TARGET_CLIP_SECONDS)
    except (cv2.error, ValueError, ZeroDivisionError):
        return {"frameChecksOk": False}

    return {
        "frameChecksOk": True,
        "sampledFrames": len(frames),
        "frameDelta": round(frame_delta, 4),
        "flickerStd": round(flicker, 4),
        "motionMean": round(motion, 4),
        "subjectMatchRatio": None if match_ratio is None else round(match_ratio, 4),
        "edgeCorrelation": round(edge, 4),
        "bestWindowStart": window_start,
        "bestWindowEnd": window_end,
    }


def _optical_flow_mean(cv2: Any, np: Any, frames: list[Any]) -> float:
    """整幅平均光流的中位数（px/帧）。只记录，用于排序和后续的成片对照。"""
    pairs = len(frames) - 1
    step = max(1, pairs // _ANALYSIS_MAX_FLOW_PAIRS)
    values = []
    for index in range(0, pairs, step):
        flow = cv2.calcOpticalFlowFarneback(frames[index], frames[index + 1], None, 0.5, 3, 15, 3, 5, 1.2, 0)
        values.append(float(np.mean(np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2))))
    return float(np.median(values)) if values else 0.0


def _subject_match_ratio(cv2: Any, frames: list[Any]) -> float | None:
    """首末帧中央 70% 区域的 ORB 匹配率。只记录，暂不参与扣分（见上面的说明）。"""
    first, last = frames[0], frames[-1]
    height, width = first.shape
    y0, y1 = int(height * 0.15), int(height * 0.85)
    x0, x1 = int(width * 0.15), int(width * 0.85)
    orb = cv2.ORB_create(nfeatures=600)
    kp1, des1 = orb.detectAndCompute(first[y0:y1, x0:x1], None)
    kp2, des2 = orb.detectAndCompute(last[y0:y1, x0:x1], None)
    if des1 is None or des2 is None or len(kp1) < 12 or len(kp2) < 12:
        return None
    good = 0
    for pair in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des1, des2, k=2):
        if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance:
            good += 1
    return good / max(1, min(len(kp1), len(kp2)))


def _edge_correlation(cv2: Any, frames: list[Any]) -> float:
    """首末帧在画面四条边 8% 宽的带状区域上的直方图相关，取最差的一条边。"""
    first, last = frames[0], frames[-1]
    height, width = first.shape
    band = max(2, int(round(min(height, width) * 0.08)))
    regions = (
        (first[:band, :], last[:band, :]),
        (first[-band:, :], last[-band:, :]),
        (first[:, :band], last[:, :band]),
        (first[:, -band:], last[:, -band:]),
    )
    scores = []
    for left, right in regions:
        hist_left = cv2.calcHist([left], [0], None, [64], [0, 256])
        hist_right = cv2.calcHist([right], [0], None, [64], [0, 256])
        cv2.normalize(hist_left, hist_left)
        cv2.normalize(hist_right, hist_right)
        scores.append(float(cv2.compareHist(hist_left, hist_right, cv2.HISTCMP_CORREL)))
    return min(scores)


def _hard_fault_checks(frame_stats: dict[str, Any], max_freeze_seconds: float) -> tuple[int, list[str], list[str]]:
    """返回（扣分, 建议重做的理由, 只提醒的话）。理由写给运营看，不写指标名。"""
    penalty = 0
    redo: list[str] = []
    notes: list[str] = []
    if max_freeze_seconds >= _FREEZE_REDO_SECONDS:
        penalty += 20
        redo.append(f"有约 {max_freeze_seconds:.1f} 秒画面完全卡住")
    elif max_freeze_seconds >= 0.25:
        notes.append(f"有约 {max_freeze_seconds:.1f} 秒画面静止，建议看一眼")
    if not frame_stats.get("frameChecksOk"):
        return penalty, redo, notes
    frame_delta = float(frame_stats.get("frameDelta") or 0.0)
    if frame_delta < _FROZEN_FRAME_DELTA:
        penalty += 25
        redo.append("整段几乎没有动，看着就是一张静止图片")
    elif frame_delta < _WEAK_FRAME_DELTA:
        penalty += 8
        notes.append("画面只有很轻微的动静，放进成片会显得发木")
    if float(frame_stats.get("flickerStd") or 0.0) > _FLICKER_STD:
        penalty += 20
        redo.append("画面亮度忽明忽暗，有明显闪烁")
    if float(frame_stats.get("edgeCorrelation") or 1.0) < _EDGE_CORRELATION:
        penalty += 15
        redo.append("画面边缘长出了原本没有的东西，或者被拉伸变形")
    return penalty, redo, notes


def _display_video_dimensions(video_stream: dict[str, Any]) -> tuple[int, int, int]:
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    rotation = 0
    for side_data in video_stream.get("side_data_list") or []:
        try:
            rotation = int(float(side_data.get("rotation", 0)))
        except (AttributeError, TypeError, ValueError):
            continue
        break
    if abs(rotation) % 180 == 90:
        return height, width, rotation
    return width, height, rotation


def analyze_video(path: str | Path, dish_name: str = "", category: str | None = None, deep_checks: bool = False) -> dict[str, Any]:
    """Score technical video readiness; semantic quality remains a future model step."""
    video_path = Path(path)
    payload = _probe_media(video_path)
    warnings: list[str] = []
    if not payload:
        return {
            "kind": "video",
            "analysisMode": "technical_rules",
            "qualityScore": 50,
            "qualityLabel": "warning",
            "qualityWarnings": ["无法读取视频元数据，请确认 ffprobe 可用"],
            "category": infer_category(dish_name, category),
            "semanticReview": "未接入视觉模型",
        }

    streams = payload.get("streams") or []
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    try:
        duration = float((payload.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    width, height, rotation = _display_video_dimensions(video_stream)
    score = 100
    if duration < 2.5:
        score -= 25
        warnings.append("视频时长短于 2.5 秒")
    if width < 720 or height < 1280:
        score -= 20
        warnings.append("视频分辨率低于竖版成片建议规格")
    if height and abs((width / height) - (9 / 16)) > 0.12:
        score -= 15
        warnings.append("视频不是接近 9:16 的竖版比例")
    fps_text = str(video_stream.get("avg_frame_rate") or "0/1")
    try:
        numerator, denominator = fps_text.split("/", 1)
        fps = float(numerator) / max(float(denominator), 1)
    except (ValueError, ZeroDivisionError):
        fps = 0
    if fps and fps < 20:
        score -= 10
        warnings.append("帧率偏低，运动画面可能不流畅")

    diagnostics = {
        "vfrRatio": 0.0,
        "maxFreezeSeconds": 0.0,
        "decodeOk": True,
    }
    frame_stats: dict[str, Any] = {"frameChecksOk": False}
    redo_reasons: list[str] = []
    if deep_checks:
        diagnostics = _timing_and_freeze_checks(video_path)
        frame_stats = _frame_diagnostics(video_path)
        penalty, redo_reasons, soft_notes = _hard_fault_checks(frame_stats, float(diagnostics["maxFreezeSeconds"]))
        score -= penalty
        # 硬伤同时写进 qualityWarnings，免得只读警告的旧代码漏掉信息。
        warnings.extend(redo_reasons)
        warnings.extend(soft_notes)
    if not diagnostics["decodeOk"]:
        score -= 30
        warnings.append("视频存在解码错误，合成前需要重新导出或替换")
    if diagnostics["vfrRatio"] >= 0.02:
        warnings.append("视频时间戳不均匀，合成时会统一重采样为 30fps")

    score = max(0, min(100, int(round(score))))
    return {
        "redoRecommended": bool(redo_reasons),
        "redoReasons": redo_reasons,
        **frame_stats,
        "kind": "video",
        "analysisMode": "technical_rules",
        "qualityScore": score,
        "qualityLabel": _quality_label(score),
        "qualityWarnings": warnings,
        "category": infer_category(dish_name, category),
        "durationSeconds": round(duration, 3),
        "width": width,
        "height": height,
        "rotation": rotation,
        "fps": round(fps, 2),
        "codec": video_stream.get("codec_name", ""),
        **diagnostics,
        "semanticReview": "未接入视觉模型",
    }


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in text)


def _uploaded_path(draft_id: str, url: str | None) -> Path | None:
    if not url:
        return None
    return uploaded_file(draft_id, Path(url.split("?", 1)[0]).name)


def _timeline_items(sound: dict[str, Any], key: str, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    value = sound.get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else fallback


def preflight_draft(
    draft: dict[str, Any],
    draft_id: str,
    workspace_id: str | None = None,
    include_sound: bool = True,
) -> dict[str, Any]:
    workspaces = draft.get("composeWorkspaces") or []
    workspace = next((item for item in workspaces if item.get("id") == workspace_id), None) if workspace_id else None
    timeline = (workspace or {}).get("clips") if workspace is not None else draft.get("timeline") or []
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    total = sum(max(0.0, float(item.get("timelineDuration") or 0)) for item in timeline if isinstance(item, dict))

    if not timeline:
        errors.append({"code": "NO_CLIPS", "message": "时间线中没有视频片段"})
    for index, clip in enumerate(timeline, 1):
        source = Path(str(clip.get("sourcePath") or ""))
        if not source.is_file():
            errors.append({"code": "MISSING_CLIP", "message": f"第 {index} 个片段没有关联本地视频文件"})
            continue
        if clip.get("trimConfirmed") is not True:
            errors.append({"code": "TRIM_NOT_CONFIRMED", "message": f"第 {index} 个片段尚未确认裁剪区间，请先在第 5 步点击“确定所选片段”"})
        quality = analyze_video(source, str(clip.get("dish") or ""), str(clip.get("dishCategory") or ""), True)
        if quality.get("decodeOk") is False:
            errors.append({"code": "CLIP_DECODE_ERROR", "message": f"第 {index} 个片段无法被 FFmpeg 完整解码，请重新导出或替换"})
        if quality.get("redoRecommended"):
            reasons = "；".join(str(item) for item in (quality.get("redoReasons") or []))
            warnings.append({"code": "CLIP_REDO_RECOMMENDED", "message": f"片段“{clip.get('dish') or clip.get('id')}”建议重做：{reasons}"})
        elif quality.get("qualityLabel") == "reject":
            warnings.append({"code": "LOW_CLIP_QUALITY", "message": f"片段“{clip.get('dish') or clip.get('id')}”技术质量评分较低"})

    if total < FINAL_DURATION_RANGE[0] or total > FINAL_DURATION_RANGE[1]:
        warnings.append({"code": "DURATION_RANGE", "message": f"当前成片预计 {total:.1f}s，建议控制在 {FINAL_DURATION_RANGE[0]}-{FINAL_DURATION_RANGE[1]}s"})

    workspace_sound = (workspace or {}).get("soundConfig") if workspace is not None else None
    sound = workspace_sound if isinstance(workspace_sound, dict) else next((node.get("data", {}) for node in draft.get("nodes", []) if node.get("data", {}).get("kind") == "sound"), {})
    # 无声那一遍不烧字幕，但片尾卡照样渲，所以片尾卡要问草稿里真正的配置，不能跟着被清空。
    sound_for_end_card = sound
    if not include_sound:
        sound = {}
    overlays = [item for item in _timeline_items(sound, "overlayItems", []) if item.get("enabled") is not False]
    voices = [item for item in _timeline_items(sound, "voiceItems", []) if item.get("enabled") is not False]
    for index, item in enumerate(overlays, 1):
        start = float(item.get("startSeconds") or 0)
        end = float(item.get("endSeconds") or 0)
        if not str(item.get("text") or "").strip():
            warnings.append({"code": "EMPTY_OVERLAY", "message": f"文字轨道 {index} 没有文案"})
        if end <= start:
            errors.append({"code": "INVALID_OVERLAY_RANGE", "message": f"文字轨道 {index} 的结束时间必须晚于开始时间"})
        if end > total + 0.05:
            warnings.append({"code": "OVERLAY_OUT_OF_RANGE", "message": f"文字轨道 {index} 超出当前成片时长"})
    for index, item in enumerate(voices, 1):
        start = float(item.get("startSeconds") or 0)
        end = float(item.get("endSeconds") or 0)
        if not str(item.get("text") or "").strip():
            warnings.append({"code": "EMPTY_VOICE", "message": f"人声轨道 {index} 没有人声文案"})
        if end <= start:
            errors.append({"code": "INVALID_VOICE_RANGE", "message": f"人声轨道 {index} 的结束时间必须晚于开始时间"})
        if end > total + 0.05:
            warnings.append({"code": "VOICE_OUT_OF_RANGE", "message": f"人声轨道 {index} 超出当前成片时长，TTS 会被截断"})

    # BGM 分三种：自己传的（文件得在）、默认曲库（曲库得有曲子）、不要音乐（不提）。
    # 默认曲库空了和「本地音频文件不存在」是两回事，混在一起报会让人去翻自己没传过的文件。
    from web.services.default_bgm import bgm_mode, list_default_bgm

    mode = bgm_mode(sound)
    if mode == "custom" and _uploaded_path(draft_id, str(sound.get("bgmUrl") or "")) is None:
        warnings.append({"code": "MISSING_BGM", "message": "草稿记录了 BGM，但本地音频文件不存在"})
    elif mode == "default" and not list_default_bgm():
        warnings.append({
            "code": "DEFAULT_BGM_EMPTY",
            "message": "默认曲库是空的，成片会没有音乐：把音乐文件放进 assets/bgm/default/，或在第 6 步上传一首",
        })

    # 机器上没有中文字体时 ffmpeg 不报错，它会默默换一个字体，中文全变成方框。
    # 与其让人渲染完才发现，不如在这里说清楚。
    if any(_has_cjk(str(item.get("text") or "")) for item in overlays + voices):
        from pipeline.video_render import caption_font_missing

        if caption_font_missing():
            warnings.append({
                "code": "MISSING_CAPTION_FONT",
                "message": "这台机器上找不到中文字体，字幕里的中文会渲染成方框。安装 fonts-noto-cjk，或用环境变量 CAPTION_FONT_FILE 指定一个字体文件",
            })

    # 字体只是会渲成方框，缺 drawtext 滤镜是整条渲不出来，所以这条算错误、直接拦下。
    # canvas_compose 顶层已经 import 了本模块，这里只能延迟 import，否则成环。
    from pipeline import video_render
    from web.services.canvas_compose import _end_card_lines

    needs_drawtext = bool(_end_card_lines(sound_for_end_card)) or any(str(item.get("text") or "").strip() for item in overlays)
    if needs_drawtext and video_render.drawtext_missing():
        errors.append({"code": "MISSING_DRAWTEXT", "message": video_render.DRAWTEXT_HELP})

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "clipCount": len(timeline),
            "totalDurationSeconds": round(total, 2),
            "overlayCount": len(overlays),
            "voiceCount": len(voices),
        },
    }
