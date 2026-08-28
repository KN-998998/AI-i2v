# -*- coding: utf-8 -*-
"""Qwen TTS and FFmpeg audio helpers used by canvas composition jobs."""

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from pipeline.config import (
    QWEN_API_KEY, QWEN_TTS_BASE_URL, QWEN_TTS_MODEL, QWEN_TTS_MODELS,
    QWEN_TTS_NATIVE_BASE_URL, QWEN_TTS_CLONE_MODEL, QWEN_TTS_CLONED_VOICES,
    TTS_VOICE,
)


class QwenTTSRequestError(RuntimeError):
    """Raised when DashScope rejects a Qwen TTS request."""


def _run_ffmpeg(cmd, timeout: int, action: str) -> None:
    """运行 ffmpeg 并用容错解码保留底层错误。"""
    result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if result.returncode == 0:
        return
    raw_detail = result.stderr or result.stdout or b"ffmpeg returned no error output"
    detail = raw_detail.decode("utf-8", errors="replace").strip()
    raise RuntimeError(f"{action}失败: {detail[-500:]}")

QWEN_VOICE_OPTIONS = (
    ("Cherry", "女声 · Cherry · 温暖自然", "female"),
    ("Serena", "女声 · Serena · 清晰自然", "female"),
    ("Ethan", "男声 · Ethan · 稳重清晰", "male"),
    ("Chelsie", "女声 · Chelsie · 活泼清晰", "female"),
    ("Momo", "女声 · Momo · 活泼明亮", "female"),
    ("Dylan", "男声 · Dylan · 年轻自然", "male"),
    ("Jada", "女声 · Jada · 温柔自然", "female"),
    ("Sunny", "女声 · Sunny · 甜美明亮", "female"),
    ("Eric", "男声 · Eric · 成熟稳重", "male"),
)


def _qwen_cloned_voice_options() -> list[dict[str, str]]:
    """Parse configured cloned voices without exposing any API credentials.

    QWEN_TTS_CLONED_VOICES uses comma-separated ``voice_id|label|gender`` items.
    ``gender`` may be ``female``, ``male``, or ``custom`` and is presentation-only.
    """
    options: list[dict[str, str]] = []
    for raw_item in QWEN_TTS_CLONED_VOICES.split(","):
        parts = [part.strip() for part in raw_item.split("|")]
        voice_id = parts[0] if parts else ""
        if not voice_id:
            continue
        label = parts[1] if len(parts) > 1 and parts[1] else "复刻音色"
        gender = parts[2].lower() if len(parts) > 2 else "custom"
        if gender not in {"female", "male", "custom"}:
            gender = "custom"
        options.append({
            "provider": "qwen",
            "model": QWEN_TTS_CLONE_MODEL,
            "voice_id": voice_id,
            "label": f"复刻音色 · {label}",
            "gender": gender,
        })
    return options


def _configured_qwen_cloned_voice_ids() -> set[str]:
    return {option["voice_id"] for option in _qwen_cloned_voice_options()}


def qwen_tts_options() -> list[dict[str, str]]:
    """Return safe, non-secret Qwen model/voice metadata for the web UI."""
    model_names = [QWEN_TTS_MODEL, "qwen-tts"]
    model_names.extend(item.strip() for item in QWEN_TTS_MODELS.split(",") if item.strip())
    built_in_models = [model for model in dict.fromkeys(model_names) if model != QWEN_TTS_CLONE_MODEL]
    built_in_options = [
        {
            "provider": "qwen",
            "model": model,
            "voice_id": voice_id,
            "label": label,
            "gender": gender,
        }
        for model in built_in_models
        for voice_id, label, gender in QWEN_VOICE_OPTIONS
    ]
    return [*built_in_options, *_qwen_cloned_voice_options()]


def _qwen_voice_id(voice: str | None) -> str | None:
    value = (voice or "").strip()
    if not value or value == "none":
        return None
    if value.startswith("qwen:"):
        return value.split(":", 1)[1].strip() or None
    if "男" in value:
        return "Ethan"
    if "女" in value:
        return "Cherry"
    if value in {"female_warm", "female"}:
        return "Cherry"
    if value in {"male_clear", "male"}:
        return "Ethan"
    if any(item[0] == value for item in QWEN_VOICE_OPTIONS):
        return value
    return value if value in _configured_qwen_cloned_voice_ids() else None


def _qwen_tts_model(voice_id: str, requested_model: str | None = None) -> str:
    """Keep cloned voices on the DashScope VC model they require."""
    if requested_model == QWEN_TTS_CLONE_MODEL:
        return QWEN_TTS_CLONE_MODEL
    if voice_id in _configured_qwen_cloned_voice_ids():
        return QWEN_TTS_CLONE_MODEL
    if requested_model:
        return requested_model
    return QWEN_TTS_MODEL


def _generate_qwen_tts(text: str, out_path: str, voice: str | None = None, model: str | None = None) -> str | None:
    if not QWEN_API_KEY:
        print("    [TTS] 未配置 QWEN_API_KEY/DASHSCOPE_API_KEY/TTS_API_KEY")
        return None
    voice_id = _qwen_voice_id(voice) or _qwen_voice_id(TTS_VOICE)
    if not voice_id:
        return None
    model_id = _qwen_tts_model(voice_id, model)
    payload = json.dumps({"model": model_id, "input": {"text": text, "voice": voice_id}, "response_format": "mp3"}).encode("utf-8")
    request = urllib.request.Request(
        QWEN_TTS_BASE_URL,
        data=payload,
        headers={"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            audio = response.read()
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(audio)
        return out_path if Path(out_path).is_file() and Path(out_path).stat().st_size > 0 else None
    except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f"    [TTS] Qwen 生成失败: {exc}")
        return None


def _qwen_error_detail(raw: bytes | str) -> str:
    """Extract a short provider error without echoing request credentials."""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    text = text.strip()
    if not text:
        return "provider returned an empty error response"
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        return text[-500:]
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            for key in ("message", "detail", "code"):
                value = str(error.get(key) or "").strip()
                if value:
                    return value[-500:]
        for key in ("message", "detail", "code"):
            value = str(body.get(key) or "").strip()
            if value:
                return value[-500:]
    return text[-500:]


def _generate_qwen_tts_strict(text: str, out_path: str, voice: str | None = None, model: str | None = None) -> str | None:
    """Generate audio and preserve provider diagnostics for composition jobs."""
    if not QWEN_API_KEY:
        return None
    raw_voice = (voice or "").strip()
    voice_id = _qwen_voice_id(raw_voice) or _qwen_voice_id(TTS_VOICE)
    # An explicitly selected VC model may carry a manually entered voice id.
    if not voice_id and model == QWEN_TTS_CLONE_MODEL and raw_voice and raw_voice != "none":
        voice_id = raw_voice.removeprefix("qwen:").strip() or None
    if not voice_id:
        return None
    model_id = _qwen_tts_model(voice_id, model)
    if model_id.startswith("qwen3-tts") and voice_id.lower().startswith("cosyvoice-"):
        raise QwenTTSRequestError(
            "voice id belongs to CosyVoice, but the selected model is Qwen3-TTS VC; "
            "configure a Qwen3-TTS cloned voice id or select the matching CosyVoice model"
        )
    payload = json.dumps({
        "model": model_id,
        "input": {"text": text, "voice": voice_id},
        "parameters": {"format": "mp3"},
    }).encode("utf-8")
    request = urllib.request.Request(
        QWEN_TTS_NATIVE_BASE_URL,
        data=payload,
        headers={"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            response_body = response.read()
        body = json.loads(response_body.decode("utf-8"))
        audio_info = (body.get("output") or {}).get("audio") if isinstance(body, dict) else None
        audio_url = audio_info.get("url") if isinstance(audio_info, dict) else None
        if not audio_url:
            raise QwenTTSRequestError(f"DashScope returned no audio URL: {_qwen_error_detail(response_body)}")
        with urllib.request.urlopen(str(audio_url), timeout=90) as audio_response:
            audio = audio_response.read()
        if not audio:
            raise QwenTTSRequestError("DashScope returned an empty audio file")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(audio)
        return out_path if Path(out_path).is_file() and Path(out_path).stat().st_size > 0 else None
    except urllib.error.HTTPError as exc:
        raise QwenTTSRequestError(f"DashScope HTTP {exc.code}: {_qwen_error_detail(exc.read())}") from exc
    except urllib.error.URLError as exc:
        raise QwenTTSRequestError(f"DashScope network error: {exc.reason}") from exc
    except OSError as exc:
        raise QwenTTSRequestError(f"Qwen audio file error: {exc}") from exc


def generate_tts(text: str, out_path: str, voice: str | None = None, model: str | None = None) -> str | None:
    """Generate one Qwen TTS segment for a canvas voice item."""
    return _generate_qwen_tts_strict(text, out_path, voice=voice, model=model)


def mix_voice_segments(voice_segments, bgm_path, out_path, bgm_volume=0.3, video_duration=12):
    """Mix independently generated voice segments at their timeline offsets."""
    if not voice_segments and not bgm_path:
        raise ValueError("至少需要一段人声或一个 BGM")
    inputs = []
    filters = []
    labels = []
    for index, segment in enumerate(voice_segments):
        if len(segment) == 4:
            voice_path, start_seconds, end_seconds, volume = segment
            segment_duration = max(0.1, float(end_seconds) - float(start_seconds))
        else:
            voice_path, start_seconds, volume = segment
            segment_duration = None
        inputs.extend(["-i", str(voice_path)])
        label = f"voice{index}"
        delay_ms = max(0, round(float(start_seconds) * 1000))
        source = f"[{index}:a]asetpts=PTS-STARTPTS"
        if segment_duration is not None:
            source += f",atrim=duration={segment_duration}"
        filters.append(f"{source},adelay={delay_ms}:all=1,volume={max(0.0, min(float(volume), 1.0))}[{label}]")
        labels.append(f"[{label}]")
    bgm_index = len(voice_segments)
    if bgm_path:
        inputs.extend(["-stream_loop", "-1", "-i", str(bgm_path)])
        filters.append(f"[{bgm_index}:a]volume={max(0.0, min(float(bgm_volume), 1.0))},afade=t=in:st=0:d=0.5,afade=t=out:st={max(0, float(video_duration) - 1)}:d=1[bgm]")
        labels.append("[bgm]")
    if len(labels) == 1:
        filters.append(f"{labels[0]}aresample=async=1:first_pts=0[aout]")
    else:
        filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:dropout_transition=0,aresample=async=1:first_pts=0[aout]")
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[aout]", "-t", str(video_duration), "-c:a", "aac", "-b:a", "192k", out_path]
    _run_ffmpeg(cmd, timeout=60, action="ffmpeg 分段人声混音")
    return out_path


def merge_audio_video(video_path, audio_path, out_path, audio_volume=1.0, video_duration=None):
    """用 ffmpeg 将音频合并到无声视频中。"""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-filter:a", f"volume={audio_volume}",
        "-c:a", "aac", "-b:a", "192k",
    ]
    if video_duration is None:
        cmd.append("-shortest")
    else:
        cmd.extend(["-t", str(video_duration)])
    cmd.append(out_path)
    _run_ffmpeg(cmd, timeout=60, action="ffmpeg 音视频合并")
    return out_path


def get_audio_duration(audio_path):
    """Read the duration of a generated TTS audio file with ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=10)
    if result.returncode == 0:
        try:
            info = json.loads((result.stdout or b"").decode("utf-8", errors="replace"))
            return max(0.0, float(info["format"]["duration"]))
        except (TypeError, ValueError, KeyError):
            pass
    return 0.0
