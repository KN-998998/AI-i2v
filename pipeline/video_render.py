# -*- coding: utf-8 -*-
"""FFmpeg video rendering helpers used by canvas composition jobs."""

import os
import re
import subprocess
import unicodedata
from pathlib import Path
from pipeline.config import FINAL_FPS, FINAL_RESOLUTION


def _run_ffmpeg(cmd, timeout: int, action: str) -> None:
    """执行 ffmpeg，并将底层错误保留给页面与日志。"""
    result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if result.returncode == 0:
        return
    raw_detail = result.stderr or result.stdout or b"ffmpeg returned no error output"
    detail = raw_detail.decode("utf-8", errors="replace").strip()
    raise RuntimeError(f"{action}失败: {detail[-500:]}")


def trim_clip(clip_path, out_path, start=0.5, duration=3.0):
    """用 ffmpeg 截取片段的动态最强部分，统一缩放到 1080x1920。"""
    w, h = FINAL_RESOLUTION
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start), "-i", clip_path,
        "-t", str(duration),
        "-vf", f"setpts=PTS-STARTPTS,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FINAL_FPS}",
        "-an",  # 无声
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    _run_ffmpeg(cmd, timeout=60, action="ffmpeg 片段裁切")
    return out_path

def _escape_drawtext(text: str) -> str:
    """转义 ffmpeg drawtext 的特殊字符。"""
    return (
        str(text)
        .replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("%", r"\%")
        .replace("\n", r"\n")
    )


def _safe_color(value: str | None, fallback: str) -> str:
    candidate = str(value or "").strip()
    return candidate if re.fullmatch(r"#[0-9a-fA-F]{6}(?:@[0-9.]+)?", candidate) else fallback


def _normalized_ratio(value) -> float | None:
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.05, min(0.95, ratio)) if 0.0 <= ratio <= 1.0 else None


def _wrap_text_for_width(text: str, width_ratio: float, font_size: int) -> str:
    """Wrap only when the editor explicitly disables single-line display."""
    max_units = max(1.0, FINAL_RESOLUTION[0] * width_ratio / max(1, font_size * 0.95))
    lines = []
    for paragraph in str(text).splitlines() or [""]:
        current = []
        used = 0.0
        for character in paragraph:
            units = _typewriter_char_width(character)
            if current and used + units > max_units:
                lines.append("".join(current))
                current = []
                used = 0.0
            current.append(character)
            used += units
        lines.append("".join(current))
    return "\n".join(lines)


def _typewriter_char_width(character: str) -> float:
    """Estimate a glyph cell width without treating all non-ASCII text as full-width."""
    if character.isspace():
        return 0.28
    if unicodedata.east_asian_width(character) in {"W", "F"}:
        return 0.95
    if character in "@#&%":
        return 0.72
    if character in "MWmw":
        return 0.82
    if character in "ilIjtfr1":
        return 0.32
    if unicodedata.category(character).startswith("P"):
        return 0.34
    return 0.55


def _typewriter_prefixes(text: str) -> list[str]:
    """Return visible prefixes without splitting Unicode characters."""
    characters = list(str(text))
    return ["".join(characters[:index]) for index in range(1, len(characters) + 1)]


def _font_file(font_family: str | None, font_weight: str | None = None) -> str:
    mapping = {
        ("Microsoft YaHei", "normal"): "C\\:/Windows/Fonts/msyh.ttc",
        ("Microsoft YaHei", "bold"): "C\\:/Windows/Fonts/msyhbd.ttc",
        ("SimHei", "normal"): "C\\:/Windows/Fonts/simhei.ttf",
        ("SimHei", "bold"): "C\\:/Windows/Fonts/simhei.ttf",
        ("KaiTi", "normal"): "C\\:/Windows/Fonts/simkai.ttf",
        ("KaiTi", "bold"): "C\\:/Windows/Fonts/simkai.ttf",
        ("FangSong", "normal"): "C\\:/Windows/Fonts/simfang.ttf",
        ("FangSong", "bold"): "C\\:/Windows/Fonts/simfang.ttf",
        ("DengXian", "normal"): "C\\:/Windows/Fonts/Deng.ttf",
        ("DengXian", "bold"): "C\\:/Windows/Fonts/Deng.ttf",
        ("Arial", "normal"): "C\\:/Windows/Fonts/arial.ttf",
        ("Arial", "bold"): "C\\:/Windows/Fonts/arialbd.ttf",
        ("Arial Black", "normal"): "C\\:/Windows/Fonts/ariblk.ttf",
        ("Arial Black", "bold"): "C\\:/Windows/Fonts/ariblk.ttf",
    }
    return mapping.get((str(font_family), str(font_weight or "normal")), mapping[("Microsoft YaHei", "normal")])


def concat_clips(clip_paths, out_path, subtitles=None, brand_info=None):
    """拼接多个片段 + 叠加字幕 + 片尾 CTA。"""
    w, h = FINAL_RESOLUTION

    # 生成 concat 文件列表
    list_path = out_path + ".txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    # 构建字幕滤镜（drawtext）
    filters = []
    subtitle_items = []
    for item in subtitles or []:
        if isinstance(item, dict):
            subtitle_items.append({
                "text": item.get("text", ""),
                "duration": float(item.get("duration", 0) or 0),
                "start": item.get("start"),
                "end": item.get("end"),
                "position": item.get("position", "bottom"),
                "x": item.get("x"),
                "y": item.get("y"),
                "animation": item.get("animation", "static"),
                "sync_voice_id": item.get("syncVoiceId"),
                "style": item.get("style", {}) if isinstance(item.get("style", {}), dict) else {},
            })
        else:
            subtitle_items.append({
                "text": str(item),
                "duration": 0.0,
                "start": None,
                "end": None,
                "position": "bottom",
                "x": None,
                "y": None,
                "style": {},
            })

    if subtitle_items:
        start_time = 0.0
        for item in subtitle_items:
            text = item["text"]
            duration = item["duration"]
            if not text:
                start_time += duration
                continue

            explicit_start = item.get("start")
            explicit_end = item.get("end")
            item_start = float(explicit_start) if explicit_start is not None else start_time
            end_time = float(explicit_end) if explicit_end is not None else item_start + duration
            y_by_position = {
                "top": "120",
                "upper": "h*0.28",
                "center": "(h-text_h)/2",
                "bottom": "h-220",
            }
            y = y_by_position.get(item.get("position", "bottom"), y_by_position["bottom"])
            x_ratio = _normalized_ratio(item.get("x"))
            y_ratio = _normalized_ratio(item.get("y"))
            if x_ratio is not None and y_ratio is not None:
                x = f"(w-text_w)*{x_ratio:.6f}"
                y = f"(h-text_h)*{y_ratio:.6f}"
            else:
                x = "(w-text_w)/2"
            style = item.get("style", {})
            font_size = max(12, min(int(style.get("fontSize", 42) or 42), 120))
            text_box_width = _normalized_ratio(style.get("textBoxWidth")) or 0.84
            single_line = bool(style.get("singleLine", True))
            font_color = _safe_color(style.get("color"), "#FFFFFF")
            stroke_color = _safe_color(style.get("strokeColor"), "#000000")
            stroke_width = max(0, min(int(style.get("strokeWidth", 2) or 0), 12))
            font_weight = "bold" if style.get("fontWeight") == "bold" else "normal"
            background_enabled = bool(style.get("backgroundEnabled", True))
            background_color = _safe_color(style.get("backgroundColor"), "#111417")
            background_opacity = max(0.0, min(float(style.get("backgroundOpacity", 0.62) or 0.0), 1.0))
            box = f":box=1:boxcolor={background_color}@{background_opacity}:boxborderw=12" if background_enabled else ""
            def append_text_filter(
                value: str,
                visible_start: float,
                visible_end: float,
                exclusive_end: bool = False,
                x_override: str | None = None,
                fontsize_override: str | None = None,
                alpha_override: str | None = None,
            ) -> None:
                safe_text = _escape_drawtext(value if single_line else _wrap_text_for_width(value, text_box_width, font_size))
                enable = f"gte(t,{visible_start})*lt(t,{visible_end})" if exclusive_end else f"between(t,{visible_start},{visible_end})"
                fontsize = fontsize_override or str(font_size)
                alpha = f":alpha={alpha_override}" if alpha_override else ""
                filters.append(
                    f"drawtext=text='{safe_text}':"
                    f"fontfile='{_font_file(style.get('fontFamily'), font_weight)}':"
                    f"fontsize={fontsize}:fontcolor={font_color}:borderw={stroke_width}:bordercolor={stroke_color}@0.8{box}{alpha}:"
                    f"x={x_override or x}:y={y}:"
                    f"enable='{enable}'"
                )

            if item.get("animation") == "typewriter" and text:
                typewriter_text = text if single_line else _wrap_text_for_width(text, text_box_width, font_size)
                characters = list(typewriter_text)
                if single_line and characters:
                    unit_widths = [font_size * _typewriter_char_width(character) for character in characters]
                    total_width = sum(unit_widths)
                    offset = 0.0
                    step = (end_time - item_start) / len(characters)
                    for index, character in enumerate(characters):
                        char_start = item_start + index * step
                        appear_duration = min(0.18, max(0.08, step * 0.7))
                        progress = f"min(1\\,max(0\\,(t-{char_start:.6f})/{appear_duration:.6f}))"
                        cell_width = unit_widths[index]
                        char_x = f"(w-{total_width:.3f})/2+{offset:.3f}+({cell_width:.3f}-text_w)/2"
                        append_text_filter(
                            character,
                            char_start,
                            end_time,
                            exclusive_end=True,
                            x_override=char_x,
                            fontsize_override=f"{font_size}*(0.72+0.28*{progress})",
                            alpha_override=progress,
                        )
                        offset += cell_width
                else:
                    prefixes = _typewriter_prefixes(typewriter_text)
                    step = (end_time - item_start) / len(prefixes)
                    for index, prefix in enumerate(prefixes):
                        prefix_start = item_start + index * step
                        prefix_end = end_time if index == len(prefixes) - 1 else prefix_start + step
                        append_text_filter(prefix, prefix_start, prefix_end, exclusive_end=True)
            else:
                append_text_filter(text, item_start, end_time)
            if explicit_start is None and explicit_end is None:
                start_time = end_time

    # 片尾 CTA
    if brand_info:
        cta_text = f"{brand_info.get('name','')} | {brand_info.get('cta','')}"
        safe_cta = _escape_drawtext(cta_text)
        total_duration = sum(s["duration"] for s in subtitle_items) if subtitle_items else 10
        filters.append(
            f"drawtext=text='{safe_cta}':"
            f"fontfile='C\\:/Windows/Fonts/msyh.ttc':"
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

    try:
        _run_ffmpeg(cmd, timeout=120, action="ffmpeg 片段拼接")
    finally:
        if os.path.exists(list_path):
            os.remove(list_path)

    return out_path
