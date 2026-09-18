import io
import json
import re
import shutil
import subprocess
from unittest.mock import patch

import pytest

from pipeline import audio as voice_bgm


class _FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def test_qwen_cloned_voice_is_exposed_and_bound_to_vc_model(monkeypatch):
    clone_id = "cosyvoice-v3.5-plus-bailian-example"
    monkeypatch.setattr(voice_bgm, "QWEN_TTS_MODEL", "qwen3-tts-flash")
    monkeypatch.setattr(voice_bgm, "QWEN_TTS_CLONE_MODEL", "qwen3-tts-vc-2026-01-22")
    monkeypatch.setattr(voice_bgm, "QWEN_TTS_MODELS", "")
    monkeypatch.setattr(voice_bgm, "QWEN_TTS_CLONED_VOICES", f"{clone_id}|Brand clone|custom")

    options = voice_bgm.qwen_tts_options()
    clone_option = next(option for option in options if option["voice_id"] == clone_id)

    assert clone_option["model"] == "qwen3-tts-vc-2026-01-22"
    assert clone_option["gender"] == "custom"
    assert voice_bgm._qwen_voice_id(clone_id) == clone_id
    assert voice_bgm._qwen_tts_model(clone_id, "qwen3-tts-flash") == "qwen3-tts-vc-2026-01-22"
    assert all(option["model"] != "qwen3-tts-vc-2026-01-22" for option in options if option["voice_id"] == "Cherry")


def test_qwen_tts_includes_chelsie_voice(monkeypatch):
    monkeypatch.setattr(voice_bgm, "QWEN_TTS_MODEL", "qwen3-tts-flash")
    monkeypatch.setattr(voice_bgm, "QWEN_TTS_MODELS", "")
    monkeypatch.setattr(voice_bgm, "QWEN_TTS_CLONED_VOICES", "")

    option = next(option for option in voice_bgm.qwen_tts_options() if option["model"] == "qwen-tts" and option["voice_id"] == "Chelsie")

    assert option["label"] == "女声 · Chelsie · 活泼清晰"
    assert voice_bgm._qwen_tts_model("Chelsie", "qwen-tts") == "qwen-tts"


def test_explicit_clone_model_keeps_a_manual_voice_id_and_builds_vc_request(monkeypatch, tmp_path):
    voice_id = "manual-clone-voice-id"
    monkeypatch.setattr(voice_bgm, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(voice_bgm, "QWEN_TTS_NATIVE_BASE_URL", "https://example.invalid/generation")
    monkeypatch.setattr(voice_bgm, "QWEN_TTS_CLONE_MODEL", "qwen3-tts-vc-2026-01-22")

    response = _FakeResponse(b'{"output":{"audio":{"url":"https://example.invalid/audio.mp3"}}}')
    audio_response = _FakeResponse(b"fake-mp3")
    with patch.object(voice_bgm.urllib.request, "urlopen", side_effect=[response, audio_response]) as urlopen:
        output = voice_bgm.generate_tts(
            "测试语音",
            str(tmp_path / "voice.mp3"),
            voice=voice_id,
            model="qwen3-tts-vc-2026-01-22",
        )

    assert output is not None
    request = urlopen.call_args_list[0].args[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["model"] == "qwen3-tts-vc-2026-01-22"
    assert payload["input"]["voice"] == voice_id
    assert payload["parameters"]["format"] == "mp3"


def test_qwen_http_error_preserves_provider_message(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_bgm, "QWEN_API_KEY", "test-key")
    error = voice_bgm.urllib.error.HTTPError(
        "https://example.invalid",
        400,
        "Bad Request",
        {},
        io.BytesIO(b'{"error":{"message":"voice is not available"}}'),
    )
    with patch.object(voice_bgm.urllib.request, "urlopen", side_effect=error):
        try:
            voice_bgm.generate_tts("测试语音", str(tmp_path / "voice.mp3"), voice="Cherry", model="qwen3-tts-flash")
        except voice_bgm.QwenTTSRequestError as exc:
            assert "voice is not available" in str(exc)
        else:
            raise AssertionError("expected QwenTTSRequestError")


def test_cosyvoice_id_is_rejected_for_qwen_vc_model(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_bgm, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(voice_bgm, "QWEN_TTS_CLONE_MODEL", "qwen3-tts-vc-2026-01-22")
    try:
        voice_bgm.generate_tts(
            "测试语音",
            str(tmp_path / "voice.mp3"),
            voice="cosyvoice-v3.5-plus-bailian-example",
            model="qwen3-tts-vc-2026-01-22",
        )
    except voice_bgm.QwenTTSRequestError as exc:
        assert "CosyVoice" in str(exc)
    else:
        raise AssertionError("expected a voice/model mismatch error")


# ---------------------------------------------------------------------------
# 第十二批：成片统一到 −14 LUFS
# 11 条已发布的参考片整体响度实测全部落在 −14.0 ~ −14.2 LUFS（Instagram / YouTube
# 的标准化目标），而工具合成的三条成片是 −20.4 / −26.2 / −31.1，彼此差了 10.7 dB。
# ---------------------------------------------------------------------------
def test_the_reference_loudness_target_is_minus_fourteen():
    from pipeline.config import FINAL_LOUDNESS_LUFS

    assert FINAL_LOUDNESS_LUFS == -14.0


def test_the_final_mix_is_normalised_to_the_reference_loudness(monkeypatch, tmp_path):
    from pipeline.config import FINAL_LOUDNESS_LUFS

    commands = []
    monkeypatch.setattr(voice_bgm, "_run_ffmpeg", lambda command, timeout, action: commands.append(command))

    voice_bgm.merge_audio_video(str(tmp_path / "v.mp4"), str(tmp_path / "a.m4a"), str(tmp_path / "out.mp4"), video_duration=11.8)

    command = commands[0]
    audio_filter = command[command.index("-filter:a") + 1]
    assert f"loudnorm=I={FINAL_LOUDNESS_LUFS}" in audio_filter
    assert "TP=-1.5" in audio_filter, "留 1.5 dB 真峰值余量，免得平台转码时削波"
    assert audio_filter.startswith("volume="), "音量倍数要在归一化之前生效，否则用户调的音量会被抹掉"


def _run_ok(command):
    return subprocess.run(command, capture_output=True, check=False).returncode == 0


def _integrated_loudness(path):
    """用 ffmpeg 的 ebur128 量整体响度，量不到返回 None。"""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
        capture_output=True, text=True, errors="replace", check=False,
    )
    found = re.findall(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", f"{result.stdout}\n{result.stderr}")
    return float(found[-1]) if found else None


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="需要 ffmpeg 才能量响度")
def test_a_quiet_soundtrack_comes_out_at_the_reference_loudness(tmp_path):
    """端到端：造一条比目标安静十几 dB 的音频，合并之后实际响度要落回 −14 附近。"""
    from pipeline.config import FINAL_LOUDNESS_LUFS

    video = tmp_path / "silent.mp4"
    quiet = tmp_path / "quiet.m4a"
    merged = tmp_path / "merged.mp4"
    assert _run_ok(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=180x320:d=6:r=30", "-pix_fmt", "yuv420p", "-an", str(video)])
    assert _run_ok(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=color=pink:d=6:r=44100", "-af", "volume=-18dB", "-c:a", "aac", str(quiet)])

    voice_bgm.merge_audio_video(str(video), str(quiet), str(merged), video_duration=6)

    measured = _integrated_loudness(merged)
    assert measured is not None, "没量到响度，ebur128 的输出格式可能变了"
    assert abs(measured - FINAL_LOUDNESS_LUFS) <= 2.0, f"实际响度 {measured} LUFS，离目标 {FINAL_LOUDNESS_LUFS} 太远"


# ---------------------------------------------------------------------------
# 第十二批 · 补充：归一化之后把采样率收回 44.1 kHz
# loudnorm 内部按 192 kHz 工作，不收尾的话 ffmpeg 会就近给 aac 挑 96 kHz——实测
# 同样 192 kbps 摊到两倍的采样点上，是个没人要的副作用。11 条已发布的参考片
# 全部是 aac / 44100 Hz / 立体声，成片没理由跟着变。
# ---------------------------------------------------------------------------
def test_the_published_sample_rate_is_forty_four_one():
    from pipeline.config import FINAL_AUDIO_SAMPLE_RATE

    assert FINAL_AUDIO_SAMPLE_RATE == 44100


def test_the_filter_chain_ends_by_restoring_the_sample_rate(monkeypatch, tmp_path):
    from pipeline.config import FINAL_AUDIO_SAMPLE_RATE

    commands = []
    monkeypatch.setattr(voice_bgm, "_run_ffmpeg", lambda command, timeout, action: commands.append(command))

    voice_bgm.merge_audio_video(str(tmp_path / "v.mp4"), str(tmp_path / "a.m4a"), str(tmp_path / "out.mp4"), video_duration=11.8)

    audio_filter = commands[0][commands[0].index("-filter:a") + 1]
    assert audio_filter.endswith(f"aresample={FINAL_AUDIO_SAMPLE_RATE}"), "重采样要放在最后一环，放在 loudnorm 前面会被它重新抬上去"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="需要 ffmpeg 才能真合一条出来量")
def test_the_merged_file_keeps_the_published_sample_rate(tmp_path):
    """端到端：真合一条出来，探它的采样率，而不是只看命令串。"""
    from pipeline.config import FINAL_AUDIO_SAMPLE_RATE

    video = tmp_path / "silent.mp4"
    quiet = tmp_path / "quiet.m4a"
    merged = tmp_path / "merged.mp4"
    assert _run_ok(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=180x320:d=6:r=30", "-pix_fmt", "yuv420p", "-an", str(video)])
    assert _run_ok(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=color=pink:d=6:r=44100", "-af", "volume=-18dB", "-c:a", "aac", str(quiet)])

    voice_bgm.merge_audio_video(str(video), str(quiet), str(merged), video_duration=6)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate", "-of", "csv=p=0", str(merged)],
        capture_output=True, text=True, errors="replace", check=False,
    )
    assert probe.stdout.strip() == str(FINAL_AUDIO_SAMPLE_RATE), f"实际采样率是 {probe.stdout.strip()}，不是 {FINAL_AUDIO_SAMPLE_RATE}"
