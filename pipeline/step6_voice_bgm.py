# -*- coding: utf-8 -*-
"""
Step 6: 无声成片 → AI 配音 + 固定 BGM → 最终有声成片
=====================================================

输入：05_composed/ 下的无声成片 + 02_prompts/ 中的文案
输出：06_final/ 下的最终有声成片 MP4

流程：
  1. 读取每条视频对应的文案（DeepSeek 生成或人工填写）
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
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import (
    BGM_FILE, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    TTS_PROVIDER, TTS_API_KEY, TTS_VOICE,
    get_batch_dir, batch_subdirs,
)

import requests


def _run_ffmpeg(cmd, timeout: int, action: str) -> None:
    """运行 ffmpeg 并用容错解码保留底层错误。"""
    result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if result.returncode == 0:
        return
    raw_detail = result.stderr or result.stdout or b"ffmpeg returned no error output"
    detail = raw_detail.decode("utf-8", errors="replace").strip()
    raise RuntimeError(f"{action}失败: {detail[-500:]}")

def generate_caption(dishes, brand_info, video_id):
    """调用 DeepSeek 生成视频配音文案。"""
    if not DEEPSEEK_API_KEY:
        # 无 API Key 时用简单拼接
        parts = [d["subtitle"] if isinstance(d, dict) else d for d in dishes]
        cta = brand_info.get("cta", "评论区领优惠券")
        return f"{'，'.join(parts)}。{cta}！"

    system_msg = """你是餐饮短视频文案专家。生成一条12-15秒短视频的配音文案。
要求：
1. 15-30字，语速适中能在10秒内读完
2. 以菜品诱惑开头，以引导到店结尾
3. 口语化、有食欲感
只输出文案正文，不要其他内容。"""

    dish_names = [d if isinstance(d, str) else d.get("subtitle", "") for d in dishes]
    user_msg = f"菜品：{'、'.join(dish_names)}\n品牌：{brand_info.get('name','')}\n引导语：{brand_info.get('cta','')}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.8,
        "max_tokens": 100,
    }
    resp = requests.post(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        headers=headers, json=payload, timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def generate_tts(text, out_path):
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
    # 方案1: edge-tts（免费，推荐先用这个验证流程）
    try:
        import edge_tts
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        communicate = edge_tts.Communicate(text, voice="zh-CN-XiaoxiaoNeural")
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


def mix_audio(voice_path, bgm_path, out_path, bgm_volume=0.3, video_duration=12):
    """用 ffmpeg 混音：配音 + BGM（BGM 降噪+控制音量+截取时长）。"""
    cmd = [
        "ffmpeg", "-y",
        "-i", voice_path,              # 配音
        "-i", bgm_path,                # BGM
        "-filter_complex",
        f"[1:a]volume={bgm_volume},afade=t=in:st=0:d=0.5,"
        f"afade=t=out:st={video_duration-1}:d=1[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]",
        "-map", "[aout]",
        "-t", str(video_duration),
        "-c:a", "aac", "-b:a", "192k",
        out_path,
    ]
    _run_ffmpeg(cmd, timeout=60, action="ffmpeg 音频混合")
    return out_path


def merge_audio_video(video_path, audio_path, out_path):
    """用 ffmpeg 将音频合并到无声视频中。"""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        out_path,
    ]
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
