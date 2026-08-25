# -*- coding: utf-8 -*-
"""
Step 6: 无声成片 → AI 配音 + 固定 BGM → 最终有声成片
=====================================================

输入：05_composed/ 下的无声成片 + 02_prompts/ 中的文案
输出：06_final/ 下的最终有声成片 MP4

流程：
  1. 读取每条视频对应的手动文案
  2. 调用 TTS API 生成配音音频
  3. 将配音 + 固定 BGM 混音
  4. 将混音叠加到无声成片上
  5. 输出最终成片

TTS 工具待选型，当前提供占位接口，选定后在此实现。
候选方案：阿里 CosyVoice / 火山引擎 TTS / 豆包 TTS / Edge-TTS（免费）

用法：
  python pipeline/step6_voice_bgm.py --config pipeline/batch_20260814.yaml
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import (
    BGM_FILE, QWEN_API_KEY, QWEN_TTS_BASE_URL, QWEN_TTS_MODEL, QWEN_TTS_MODELS,
    TTS_PROVIDER, TTS_API_KEY, TTS_VOICE,
    get_batch_dir, batch_subdirs,
)


def _run_ffmpeg(cmd, timeout: int, action: str) -> None:
    """运行 ffmpeg 并用容错解码保留底层错误。"""
    result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if result.returncode == 0:
        return
    raw_detail = result.stderr or result.stdout or b"ffmpeg returned no error output"
    detail = raw_detail.decode("utf-8", errors="replace").strip()
    raise RuntimeError(f"{action}失败: {detail[-500:]}")

def generate_caption(dishes, brand_info, video_id):
    """Return the manually supplied caption, with a simple fallback for CLI batches."""
    parts = [d["subtitle"] if isinstance(d, dict) else d for d in dishes]
    cta = brand_info.get("cta", "评论区领优惠券")
    return f"{'，'.join(parts)}。{cta}！"


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


def qwen_tts_options() -> list[dict[str, str]]:
    """Return safe, non-secret Qwen model/voice metadata for the web UI."""
    model_names = [QWEN_TTS_MODEL]
    model_names.extend(item.strip() for item in QWEN_TTS_MODELS.split(",") if item.strip())
    return [
        {
            "provider": "qwen",
            "model": model,
            "voice_id": voice_id,
            "label": label,
            "gender": gender,
        }
        for model in dict.fromkeys(model_names)
        for voice_id, label, gender in QWEN_VOICE_OPTIONS
    ]


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
    return value if any(item[0] == value for item in QWEN_VOICE_OPTIONS) else None


def _generate_qwen_tts(text: str, out_path: str, voice: str | None = None, model: str | None = None) -> str | None:
    if not QWEN_API_KEY:
        print("    [TTS] 未配置 QWEN_API_KEY/DASHSCOPE_API_KEY/TTS_API_KEY")
        return None
    voice_id = _qwen_voice_id(voice) or _qwen_voice_id(TTS_VOICE)
    if not voice_id:
        return None
    payload = json.dumps({"model": model or QWEN_TTS_MODEL, "input": {"text": text, "voice": voice_id}, "response_format": "mp3"}).encode("utf-8")
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


def generate_tts(text, out_path, voice=None, model=None):
    """
    调用 TTS API 生成配音音频。

    TTS 工具待选型，以下为占位实现。
    选定后替换为具体的 API 调用。

    候选方案：
    - edge-tts（免费，无需 API Key）：pip install edge-tts
    - 阿里 CosyVoice：需阿里云 API
    - 火山引擎 TTS：需火山引擎 API
    - 豆包 TTS：需豆包 API
    """
    if TTS_PROVIDER in {"qwen", "dashscope"}:
        return _generate_qwen_tts(text, out_path, voice=voice, model=model)

    # Legacy fallback for CLI users who explicitly select edge-tts.
    try:
        import edge_tts
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        communicate = edge_tts.Communicate(text, voice=voice)
        result = communicate.save(out_path)
        if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
            asyncio.run(result)
        if os.path.exists(out_path):
            return out_path
        print(f"    [TTS] 音频未生成: {out_path}")
        return None
    except ImportError:
        pass
    except Exception as e:
        print(f"    [TTS] edge-tts 失败: {e}")

    # 方案2: 其他 TTS API（选定后在此实现）
    # if TTS_PROVIDER == "cosyvoice":
    #     ...
    # elif TTS_PROVIDER == "volcengine":
    #     ...

    print(f"    [TTS] 未配置可用的 TTS 工具")
    print(f"    [TTS] 请安装: pip install edge-tts")
    return None


def mix_audio(voice_path, bgm_path, out_path, bgm_volume=0.3, video_duration=12, voice_volume=1.0):
    """用 ffmpeg 混音：配音 + BGM（BGM 降噪+控制音量+截取时长）。"""
    cmd = [
        "ffmpeg", "-y",
        "-i", voice_path,              # 配音
        "-i", bgm_path,                # BGM
        "-filter_complex",
        f"[0:a]volume={voice_volume}[voice];"
        f"[1:a]volume={bgm_volume},afade=t=in:st=0:d=0.5,"
        f"afade=t=out:st={video_duration-1}:d=1[bgm];"
        f"[voice][bgm]amix=inputs=2:duration=longest:dropout_transition=0[aout]",
        "-map", "[aout]",
        "-t", str(video_duration),
        "-c:a", "aac", "-b:a", "192k",
        out_path,
    ]
    _run_ffmpeg(cmd, timeout=60, action="ffmpeg 音频混合")
    return out_path


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


def add_bgm(bgm_path, out_path, bgm_volume=0.3, video_duration=12):
    """Create a duration-limited BGM track with a short fade in/out."""
    fade_out_start = max(0, float(video_duration) - 1)
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", bgm_path,
        "-t", str(video_duration),
        "-filter:a", f"volume={bgm_volume},afade=t=in:st=0:d=0.5,afade=t=out:st={fade_out_start}:d=1",
        "-c:a", "aac", "-b:a", "192k",
        out_path,
    ]
    _run_ffmpeg(cmd, timeout=60, action="ffmpeg BGM 处理")
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


def get_video_duration(video_path):
    """获取视频时长。"""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=10)
    if result.returncode == 0:
        try:
            info = json.loads((result.stdout or b"").decode("utf-8", errors="replace"))
            return float(info["format"]["duration"])
        except (TypeError, ValueError, KeyError):
            pass
    return 12.0  # 默认


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


def run(config_path: str):
    """主入口。"""
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    batch_date = cfg["batch"]["date"]
    batch_dir = get_batch_dir(batch_date)
    dirs = batch_subdirs(batch_dir)

    composed_manifest = dirs["composed"] / "manifest.json"
    if not composed_manifest.exists():
        print("[错误] 请先运行 step5 合成无声成片")
        sys.exit(1)

    with open(composed_manifest, encoding="utf-8") as f:
        composed = json.load(f)

    brand_info = cfg.get("brand", {})
    bgm_file = cfg.get("bgm", {}).get("file", "") or str(BGM_FILE)
    bgm_volume = cfg.get("bgm", {}).get("volume", 0.3)

    # 读取字幕文案
    subtitles = {}
    for f in dirs["prompts"].glob("*_meta.json"):
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
            subtitles[data["dish"]] = data.get("subtitle", data["dish"])

    videos = cfg.get("videos", [])

    print(f"{'='*60}")
    print(f"Step 6: AI 配音 + 固定 BGM → 最终有声成片")
    print(f"  视频数: {len([c for c in composed if c['status'] == 'ok'])}")
    print(f"  BGM: {bgm_file}")
    print(f"  TTS: {'edge-tts' if TTS_PROVIDER == '' else TTS_PROVIDER}")
    print(f"  输出: {dirs['final']}")
    print(f"{'='*60}")

    results = []
    for item in composed:
        if item["status"] != "ok":
            continue

        vid = item["id"]
        video_path = item["output"]

        # 找到对应的视频编排
        video_cfg = next((v for v in videos if v["id"] == vid), None)
        dish_names = video_cfg["dishes"] if video_cfg else []

        print(f"\n[{vid}] {os.path.basename(video_path)}")

        # 1. 生成配音文案
        dish_subtitles = [subtitles.get(d, d) for d in dish_names]
        caption = generate_caption(dish_subtitles, brand_info, vid)
        print(f"  文案: {caption}")

        # 2. TTS 生成配音
        voice_path = str(dirs["final"] / f"{vid}_voice.mp3")
        voice_result = generate_tts(caption, voice_path)

        if not voice_result:
            print(f"  [跳过] TTS 不可用，仅添加 BGM")
            # 仅添加 BGM
            duration = get_video_duration(video_path)
            audio_path = str(dirs["final"] / f"{vid}_audio.mp3")
            if os.path.exists(bgm_file):
                cmd = [
                    "ffmpeg", "-y", "-i", bgm_file,
                    "-t", str(duration),
                    "-af", f"volume={bgm_volume},afade=t=in:st=0:d=0.5,"
                           f"afade=t=out:st={duration-1}:d=1",
                    "-c:a", "aac", "-b:a", "192k",
                    audio_path,
                ]
                subprocess.run(cmd, capture_output=True, timeout=60)
            else:
                print(f"  [跳过] BGM 文件不存在: {bgm_file}")
                results.append({"id": vid, "status": "no_audio",
                                "output": video_path})
                continue
        else:
            # 3. 混音：配音 + BGM
            audio_path = str(dirs["final"] / f"{vid}_audio.mp3")
            duration = get_video_duration(video_path)
            if os.path.exists(bgm_file):
                mix_audio(voice_path, bgm_file, audio_path,
                         bgm_volume=bgm_volume, video_duration=duration)
            else:
                # 无 BGM，只用配音
                import shutil
                shutil.copy(voice_path, audio_path)

        # 4. 合并音视频
        final_path = str(dirs["final"] / f"{vid}_final.mp4")
        merge_audio_video(video_path, audio_path, final_path)

        if os.path.exists(final_path):
            size = os.path.getsize(final_path) / 1024 / 1024
            print(f"  [完成] {final_path} ({size:.1f}MB)")
            results.append({"id": vid, "status": "ok", "output": final_path,
                           "caption": caption})
        else:
            results.append({"id": vid, "status": "failed"})

        # 清理临时文件
        for tmp in [voice_path, audio_path]:
            if os.path.exists(tmp):
                os.remove(tmp)

    manifest_path = dirs["final"] / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n{'='*60}")
    print(f"完成: {ok}/{len(results)} 条最终视频生成成功")
    print(f"清单: {manifest_path}")
    print(f"{'='*60}")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Step 6: AI 配音 + BGM")
    ap.add_argument("--config", required=True, help="batch.yaml 路径")
    args = ap.parse_args()
    run(args.config)
