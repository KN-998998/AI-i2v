# -*- coding: utf-8 -*-
"""Local media analysis and deterministic canvas preflight checks."""
from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

from pipeline.config import FINAL_DURATION_RANGE
from web.services.canvas_state import draft_directory, uploaded_file

_CATEGORIES = {"正餐", "小吃", "甜品", "水果", "饮品", "其他"}
_FRUIT_KEYWORDS = ("蜜瓜", "草莓", "西瓜", "芒果", "葡萄", "蓝莓", "树莓", "樱桃", "桃", "梨", "苹果", "橙", "柚", "柠檬")
_DESSERT_KEYWORDS = ("蛋糕", "布丁", "冰淇淋", "甜点", "甜品", "慕斯", "奶油", "铜锣烧", "抹茶", "芝士")
_SNACK_KEYWORDS = ("天妇罗", "炸", "串", "薯", "饼", "小吃")
_DRINK_KEYWORDS = ("饮料", "果汁", "咖啡", "茶", "酒", "汽水", "苏打")


def infer_category(name: str, explicit: str | None = None) -> str:
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
        return "小吃"
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


def analyze_video(path: str | Path, dish_name: str = "", category: str | None = None) -> dict[str, Any]:
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

    score = max(0, min(100, int(round(score))))
    return {
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
        "semanticReview": "未接入视觉模型",
    }


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
        quality = analyze_video(source, str(clip.get("dish") or ""), str(clip.get("dishCategory") or ""))
        if quality.get("qualityLabel") == "reject":
            warnings.append({"code": "LOW_CLIP_QUALITY", "message": f"片段“{clip.get('dish') or clip.get('id')}”技术质量评分较低"})

    if total < FINAL_DURATION_RANGE[0] or total > FINAL_DURATION_RANGE[1]:
        warnings.append({"code": "DURATION_RANGE", "message": f"当前成片预计 {total:.1f}s，建议控制在 {FINAL_DURATION_RANGE[0]}-{FINAL_DURATION_RANGE[1]}s"})

    workspace_sound = (workspace or {}).get("soundConfig") if workspace is not None else None
    sound = workspace_sound if isinstance(workspace_sound, dict) else next((node.get("data", {}) for node in draft.get("nodes", []) if node.get("data", {}).get("kind") == "sound"), {})
    if not include_sound:
        sound = {}
    overlays = _timeline_items(sound, "overlayItems", [])
    voices = _timeline_items(sound, "voiceItems", [])
    voices_by_id = {str(item.get("id") or ""): item for item in voices if str(item.get("id") or "")}
    overlay_voice_ids: set[str] = set()
    for index, item in enumerate(overlays, 1):
        start = float(item.get("startSeconds") or 0)
        end = float(item.get("endSeconds") or 0)
        sync_voice_id = str(item.get("syncVoiceId") or "")
        linked_voice = voices_by_id.get(sync_voice_id)
        if not str(item.get("text") or "").strip():
            warnings.append({"code": "EMPTY_OVERLAY", "message": f"文字轨道 {index} 没有文案"})
        if end <= start:
            errors.append({"code": "INVALID_OVERLAY_RANGE", "message": f"文字轨道 {index} 的结束时间必须晚于开始时间"})
        if end > total + 0.05:
            warnings.append({"code": "OVERLAY_OUT_OF_RANGE", "message": f"文字轨道 {index} 超出当前成片时长"})
        if linked_voice is None:
            warnings.append({"code": "UNPAIRED_CAPTION", "message": f"文字轨道 {index} 未绑定有效人声，无法保证文字与语音同步"})
        else:
            overlay_voice_ids.add(sync_voice_id)
            voice_start = float(linked_voice.get("startSeconds") or 0)
            voice_end = float(linked_voice.get("endSeconds") or 0)
            if str(item.get("text") or "") != str(linked_voice.get("text") or "") or abs(start - voice_start) > 0.05 or abs(end - voice_end) > 0.05:
                warnings.append({"code": "CAPTION_NOT_SYNCED", "message": f"文字轨道 {index} 与绑定人声不一致，最终生成时会按 TTS 实际时长自动同步"})
    for index, item in enumerate(voices, 1):
        start = float(item.get("startSeconds") or 0)
        end = float(item.get("endSeconds") or 0)
        if not str(item.get("text") or "").strip():
            warnings.append({"code": "EMPTY_VOICE", "message": f"人声轨道 {index} 没有人声文案"})
        if end <= start:
            errors.append({"code": "INVALID_VOICE_RANGE", "message": f"人声轨道 {index} 的结束时间必须晚于开始时间"})
        if end > total + 0.05:
            warnings.append({"code": "VOICE_OUT_OF_RANGE", "message": f"人声轨道 {index} 超出当前成片时长，TTS 会被截断"})
        if str(item.get("id") or "") not in overlay_voice_ids:
            warnings.append({"code": "UNPAIRED_VOICE", "message": f"人声轨道 {index} 没有对应画面文字，无法保证文案同步"})

    bgm_url = sound.get("bgmUrl")
    if bgm_url and _uploaded_path(draft_id, str(bgm_url)) is None:
        warnings.append({"code": "MISSING_BGM", "message": "草稿记录了 BGM，但本地音频文件不存在"})

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
