# -*- coding: utf-8 -*-
"""FFmpeg video rendering helpers used by canvas composition jobs."""

import os
import re
import subprocess
import unicodedata
from functools import lru_cache
from pathlib import Path
from pipeline.config import FINAL_FPS, FINAL_RESOLUTION

# 开头淡入。11 条参考片里 9 条都是黑场淡入起手，这里统一加上。
FADE_IN_SECONDS = 0.3
# 片尾信息卡时长。参考片全部有，约 1 秒。
END_CARD_SECONDS = 1.0

# 片尾卡和字幕都靠 drawtext 这个滤镜，而它要 ffmpeg 编进 libfreetype 才有。
# 2026-09-21 实测：Homebrew 的 ffmpeg 9.0.2 就没编，点「合成此条」才报一屏
# "No such filter: 'drawtext'"。这句话要能直接照着做，别让运营去查 ffmpeg 原文。
#
# 写 ffmpeg@7 而不是 @8：2026-09-22 在本机逐个量过，@7（7.1.5）有 drawtext、编了
# libfreetype，@8（8.1.2）和默认的 9.0.2 都没有。指到 @8 等于让人白装一次。
DRAWTEXT_HELP = (
    "这台机器的 ffmpeg 没有画字功能（drawtext 滤镜），片尾卡和字幕都渲染不了。"
    "macOS：brew install ffmpeg@7，再把 /opt/homebrew/opt/ffmpeg@7/bin 放到 PATH 最前面；"
    "Linux：apt install ffmpeg。"
)
_DRAWTEXT_MISSING_MARK = "No such filter: 'drawtext'"


@lru_cache(maxsize=1)
def ffmpeg_can_draw_text() -> bool:
    """这台机器的 ffmpeg 会不会画字。问一次就够，结果缓存起来（换 ffmpeg 要重启进程）。"""
    try:
        result = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        # 连 ffmpeg 都没有，那更不会画字；这里不抛，交给调用方按「不会画字」处理。
        return False
    # 有的构建把滤镜表打到 stderr，两边一起看。
    output = (result.stdout or b"") + b"\n" + (result.stderr or b"")
    return b"drawtext" in output


def drawtext_missing() -> bool:
    return not ffmpeg_can_draw_text()


def _run_ffmpeg(cmd, timeout: int, action: str) -> None:
    """执行 ffmpeg，并将底层错误保留给页面与日志。"""
    result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if result.returncode == 0:
        return
    raw_detail = result.stderr or result.stdout or b"ffmpeg returned no error output"
    detail = raw_detail.decode("utf-8", errors="replace").strip()
    # 缺 drawtext 是已知且有修法的一种失败，给人话；其余照旧留 ffmpeg 原文的尾巴。
    if _DRAWTEXT_MISSING_MARK in detail:
        raise RuntimeError(f"{action}失败: {DRAWTEXT_HELP}")
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


# drawtext 必须拿到一个真实存在的字体文件。这里原来写死的是 Windows 路径，而线上
# 跑的是 Debian 容器，那些文件根本不存在——ffmpeg 不报错，它会默默换一个不含中文
# 的字体，于是所有中文字幕都渲染成方框，人还以为是字幕没写对。
# 所以改成运行时按平台找一个真的能写中文的字体；想指定具体字体就设 CAPTION_FONT_FILE。
_FONT_ENV_KEY = "CAPTION_FONT_FILE"
_WINDOWS_FONTS = {
    ("Microsoft YaHei", "normal"): "C:/Windows/Fonts/msyh.ttc",
    ("Microsoft YaHei", "bold"): "C:/Windows/Fonts/msyhbd.ttc",
    ("SimHei", "normal"): "C:/Windows/Fonts/simhei.ttf",
    ("SimHei", "bold"): "C:/Windows/Fonts/simhei.ttf",
    ("KaiTi", "normal"): "C:/Windows/Fonts/simkai.ttf",
    ("KaiTi", "bold"): "C:/Windows/Fonts/simkai.ttf",
    ("FangSong", "normal"): "C:/Windows/Fonts/simfang.ttf",
    ("FangSong", "bold"): "C:/Windows/Fonts/simfang.ttf",
    ("DengXian", "normal"): "C:/Windows/Fonts/Deng.ttf",
    ("DengXian", "bold"): "C:/Windows/Fonts/Deng.ttf",
    ("Arial", "normal"): "C:/Windows/Fonts/arial.ttf",
    ("Arial", "bold"): "C:/Windows/Fonts/arialbd.ttf",
    ("Arial Black", "normal"): "C:/Windows/Fonts/ariblk.ttf",
    ("Arial Black", "bold"): "C:/Windows/Fonts/ariblk.ttf",
}
# 按 macOS → Linux 的顺序找，都是自带或 fonts-noto-cjk 装出来的路径。
_FALLBACK_FONTS = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
)


@lru_cache(maxsize=64)
def resolve_caption_font(font_family: str | None = None, font_weight: str | None = None) -> str:
    """返回一个真实存在的字体文件路径；一个都找不到时返回空字符串。"""
    override = os.environ.get(_FONT_ENV_KEY, "").strip()
    if override and Path(override).is_file():
        return override
    preferred = _WINDOWS_FONTS.get((str(font_family), str(font_weight or "normal")))
    for candidate in (preferred, *_FALLBACK_FONTS):
        if candidate and Path(candidate).is_file():
            return candidate
    return ""


def caption_font_missing() -> bool:
    """机器上一个中文字体都没有——预检用它提前告诉人"中文会变成方框"。"""
    return not resolve_caption_font()


def _font_file(font_family: str | None, font_weight: str | None = None) -> str:
    """拼进 drawtext 的 `:fontfile='...'` 片段；找不到字体就返回空串，交给 ffmpeg 兜底。"""
    resolved = resolve_caption_font(font_family, font_weight)
    if not resolved:
        return ""
    escaped = resolved.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    return f":fontfile='{escaped}'"


def render_end_card(out_path, lines, duration: float = END_CARD_SECONDS):
    """渲染一张黑底的片尾信息卡（店名 / 地址 / 定位），规格和裁好的片段一致。

    参考片 11 条全都有这么一张卡。它作为普通片段接在 concat 列表最后，所以不需要
    改拼接逻辑，字幕的时间轴也不受影响。
    """
    usable = [str(item).strip() for item in (lines or []) if str(item).strip()][:3]
    if not usable:
        return None
    width, height = FINAL_RESOLUTION
    font = _font_file("Microsoft YaHei", "bold")
    sizes = [78, 46, 40][: len(usable)]
    gap = 34
    block = sum(sizes) + gap * (len(usable) - 1)
    top = (height - block) / 2
    filters = []
    for text, size in zip(usable, sizes):
        filters.append(
            f"drawtext=text='{_escape_drawtext(text)}'{font}:"
            f"fontsize={size}:fontcolor=#FFFFFF:x=(w-text_w)/2:y={int(round(top))}"
        )
        top += size + gap
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:d={max(0.2, float(duration))}:r={FINAL_FPS}",
        "-vf", ",".join(filters),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-an",
        str(out_path),
    ]
    _run_ffmpeg(cmd, timeout=60, action="ffmpeg 片尾卡渲染")
    return str(out_path)


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
                    f"drawtext=text='{safe_text}'"
                    f"{_font_file(style.get('fontFamily'), font_weight)}:"
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

    # 片尾 CTA（旧接口，现在片尾信息卡走 render_end_card 作为独立片段接在最后）
    if brand_info:
        cta_text = f"{brand_info.get('name','')} | {brand_info.get('cta','')}"
        safe_cta = _escape_drawtext(cta_text)
        total_duration = sum(s["duration"] for s in subtitle_items) if subtitle_items else 10
        filters.append(
            f"drawtext=text='{safe_cta}'"
            f"{_font_file('Microsoft YaHei', 'bold')}:"
            f"fontsize=52:fontcolor=#FFD700:borderw=3:bordercolor=black@0.9:"
            f"x=(w-text_w)/2:y=h-120:"
            f"enable='gte(t,{total_duration - 2})'"
        )

    # 开头淡入放在最后一环，这样连字幕一起淡进来，和参考片的黑场起手一致。
    if FADE_IN_SECONDS > 0:
        filters.append(f"fade=t=in:st=0:d={FADE_IN_SECONDS}")

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
