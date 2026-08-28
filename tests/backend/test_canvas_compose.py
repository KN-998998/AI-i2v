import time
from pathlib import Path

from pipeline import video_render
from pipeline.video_render import _typewriter_char_width, _typewriter_prefixes
from web.services.canvas_compose import _overlay_items, _pair_caption_tracks, _sound_node, _sync_caption_timings, _voice_items
from web.services import canvas_compose, canvas_quality, canvas_state


def test_typewriter_prefixes_keep_unicode_characters():
    assert _typewriter_prefixes("寿司🍣") == ["寿", "寿司", "寿司🍣"]


def test_typewriter_widths_distinguish_ascii_punctuation_and_fullwidth_text():
    assert _typewriter_char_width("你") == 0.95
    assert _typewriter_char_width("，") == 0.95
    assert _typewriter_char_width("’") < _typewriter_char_width("你")
    assert _typewriter_char_width("@") > _typewriter_char_width("i")
    assert _typewriter_char_width(" ") < _typewriter_char_width("a")


def test_video_timing_diagnostics_detect_vfr_and_freeze(monkeypatch, tmp_path):
    def fake_check(_path, video_filter=None, level="error"):
        if video_filter == "vfrdet":
            return 0, "VFR:0.105263 (20/170)"
        if video_filter and video_filter.startswith("freezedetect"):
            return 0, "freeze_duration:0.42"
        return 0, ""

    monkeypatch.setattr(canvas_quality, "_run_ffmpeg_check", fake_check)

    diagnostics = canvas_quality._timing_and_freeze_checks(tmp_path / "clip.mp4")

    assert diagnostics == {"vfrRatio": 0.1053, "maxFreezeSeconds": 0.42, "decodeOk": True}


def test_typewriter_filters_animate_each_character_without_prefix_layers(monkeypatch, tmp_path):
    source = tmp_path / "clip.mp4"
    output = tmp_path / "output.mp4"
    source.write_bytes(b"video")
    commands = []
    monkeypatch.setattr(video_render, "_run_ffmpeg", lambda command, timeout, action: commands.append(command))

    video_render.concat_clips(
        [str(source)],
        str(output),
        subtitles=[{"text": "寿司", "start": 0, "end": 2, "animation": "typewriter"}],
    )

    command = commands[0]
    vf = command[command.index("-vf") + 1]
    assert "drawtext=text='寿'" in vf
    assert "drawtext=text='司'" in vf
    assert "enable='gte(t,0.0)*lt(t,2.0)'" in vf
    assert "enable='gte(t,1.0)*lt(t,2.0)'" in vf
    assert "fontsize=42*(0.72+0.28*min(1\\,max(0\\,(t-0.000000)/0.180000)))" in vf
    assert ":alpha=min(1\\,max(0\\,(t-1.000000)/0.180000))" in vf


def test_overlay_can_follow_actual_voice_timing():
    sound = {
        "overlayItems": [
            {
                "id": "overlay-1",
                "text": "今日推荐",
                "startSeconds": 0,
                "endSeconds": 2,
                "animation": "typewriter",
                "syncVoiceId": "voice-1",
            }
        ]
    }

    items = _overlay_items(sound, {"voice-1": (1.25, 3.75)})

    assert items[0]["start"] == 1.25
    assert items[0]["end"] == 3.75
    assert items[0]["animation"] == "typewriter"


def test_actual_tts_duration_syncs_paired_track_timing_without_overwriting_text():
    draft = {
        "nodes": [{
            "data": {
                "kind": "sound",
                "voiceItems": [{"id": "voice-1", "text": "语音文案", "startSeconds": 0, "endSeconds": 2}],
                "overlayItems": [{"id": "overlay-1", "text": "旧文字", "syncVoiceId": "voice-1", "startSeconds": 0, "endSeconds": 2, "position": "upper"}],
            },
        }],
    }

    _sync_caption_timings(draft, {"voice-1": (1.25, 3.75)})

    sound = draft["nodes"][0]["data"]
    assert sound["voiceItems"][0]["startSeconds"] == 1.25
    assert sound["voiceItems"][0]["endSeconds"] == 3.75
    assert sound["overlayItems"][0]["text"] == "旧文字"
    assert sound["overlayItems"][0]["startSeconds"] == 1.25
    assert sound["overlayItems"][0]["endSeconds"] == 3.75


def test_old_caption_tracks_are_paired_before_rendering():
    sound = {
        "voiceItems": [{"id": "voice-1", "text": "语音文案", "startSeconds": 1, "endSeconds": 4}],
        "overlayItems": [{"id": "overlay-1", "text": "旧文字", "startSeconds": 0, "endSeconds": 2}],
    }

    _pair_caption_tracks(sound)

    assert sound["overlayItems"][0]["syncVoiceId"] == "voice-1"
    assert sound["overlayItems"][0]["text"] == "旧文字"
    assert sound["overlayItems"][0]["startSeconds"] == 0
    assert sound["overlayItems"][0]["endSeconds"] == 2


def test_disabled_caption_tracks_are_excluded_from_render_inputs():
    sound = {
        "overlayItems": [{"id": "overlay-1", "text": "只保留语音", "enabled": False, "startSeconds": 0, "endSeconds": 2}],
        "voiceItems": [{"id": "voice-1", "text": "只保留文字", "enabled": False, "startSeconds": 0, "endSeconds": 2, "voiceId": "Cherry"}],
    }

    assert _overlay_items(sound) == []
    assert _voice_items(sound) == []


def test_workspace_sound_config_has_priority_over_legacy_sound_node():
    draft = {
        "nodes": [{"data": {"kind": "sound", "bgmName": "旧 BGM"}}],
        "composeWorkspaces": [{"id": "compose_2", "soundConfig": {"bgmName": "方案 BGM", "bgmUrl": "/方案.mp3"}}],
    }

    assert _sound_node(draft, "compose_2")["bgmName"] == "方案 BGM"


def test_stale_client_save_does_not_remove_completed_final_job(tmp_path, monkeypatch):
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    clip = {"id": "clip-1", "dish": "测试菜品"}
    sound = {"voiceItems": [{"id": "voice-1", "text": "测试", "startSeconds": 0, "endSeconds": 2}]}
    base = {"nodes": [], "edges": [], "timeline": [clip]}
    completed = {
        "job_id": "f" * 32,
        "status": "done",
        "include_sound": True,
        "updated_at": "2026-08-27T10:00:00+00:00",
        "timeline": [clip],
        "sound": sound,
    }
    canvas_state.save_draft(
        "default",
        {
            **base,
            "composeWorkspaces": [{"id": "compose_1", "clips": [clip], "soundConfig": sound, "job": None, "finalJob": completed}],
            "composeJob": completed,
        },
    )
    canvas_state.save_draft(
        "default",
        {
            **base,
            "composeWorkspaces": [{"id": "compose_1", "clips": [clip], "soundConfig": sound, "job": None, "finalJob": None}],
            "composeJob": None,
        },
    )

    saved = canvas_state.load_draft("default")
    assert saved["composeWorkspaces"][0]["finalJob"]["job_id"] == completed["job_id"]


def test_preflight_blocks_real_clip_without_trim_confirmation(monkeypatch, tmp_path):
    clip_path = tmp_path / "clip.mp4"
    clip_path.write_bytes(b"video")
    monkeypatch.setattr(canvas_quality, "analyze_video", lambda *args: {"qualityLabel": "good"})

    report = canvas_quality.preflight_draft(
        {"timeline": [{"id": "clip", "dish": "测试菜", "sourcePath": str(clip_path), "timelineDuration": 2.5}]},
        "default",
        include_sound=False,
    )

    assert report["ok"] is False
    assert report["errors"][0]["code"] == "TRIM_NOT_CONFIRMED"


def test_preflight_blocks_clip_with_decode_error(monkeypatch, tmp_path):
    clip_path = tmp_path / "clip.mp4"
    clip_path.write_bytes(b"video")
    monkeypatch.setattr(
        canvas_quality,
        "analyze_video",
        lambda *_args: {"qualityLabel": "good", "decodeOk": False},
    )

    report = canvas_quality.preflight_draft(
        {"timeline": [{"id": "clip", "dish": "测试菜品", "sourcePath": str(clip_path), "timelineDuration": 2.5, "trimConfirmed": True}]},
        "default",
        include_sound=False,
    )

    assert report["ok"] is False
    assert report["errors"][0]["code"] == "CLIP_DECODE_ERROR"


def test_startup_recovery_finishes_persisted_compose_job(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    canvas_state.save_draft("default", {"nodes": [], "edges": [], "timeline": []})
    clip = {"id": "clip-1", "dish": "Recovery dish", "timelineDuration": 2.0}
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    monkeypatch.setattr(canvas_compose, "_prepare_sources", lambda _draft_id, timeline: [(timeline[0], source)])

    from pipeline import video_render

    monkeypatch.setattr(video_render, "trim_clip", lambda _source, destination, start, duration: Path(destination).write_bytes(b"trimmed"))
    monkeypatch.setattr(video_render, "concat_clips", lambda _sources, destination, subtitles, brand_info: Path(destination).write_bytes(b"composed"))
    job = {
        "job_id": "e" * 32,
        "draft_id": "default",
        "status": "running",
        "workspace_id": None,
        "include_sound": False,
        "timeline": [clip],
        "sound": {},
    }
    canvas_compose._save_job("default", job)

    assert canvas_compose.recover_compose_jobs() == 1
    for _ in range(40):
        current = canvas_compose.get_compose_job("default", job["job_id"])
        if current and current["status"] in {"done", "error"}:
            break
        time.sleep(0.05)

    assert current["status"] == "done", current.get("error")
    output = canvas_compose.compose_output_path("default", job["job_id"])
    assert output is not None and output.is_file()
