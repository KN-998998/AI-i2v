import io
import json
from unittest.mock import patch

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
