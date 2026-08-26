from pipeline import step6_voice_bgm as voice_bgm


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
