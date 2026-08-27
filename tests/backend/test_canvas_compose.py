import time
from pathlib import Path

from pipeline.video_render import _typewriter_prefixes
from web.services.canvas_compose import _overlay_items, _pair_caption_tracks, _sound_node, _sync_caption_timings
from web.services import canvas_compose, canvas_quality, canvas_state


def test_typewriter_prefixes_keep_unicode_characters():
    assert _typewriter_prefixes("寿司🍣") == ["寿", "寿司", "寿司🍣"]


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


def test_actual_tts_duration_syncs_paired_voice_and_caption_text():
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
    assert sound["overlayItems"][0]["text"] == "语音文案"
    assert sound["overlayItems"][0]["startSeconds"] == 1.25
    assert sound["overlayItems"][0]["endSeconds"] == 3.75


def test_old_caption_tracks_are_paired_before_rendering():
    sound = {
        "voiceItems": [{"id": "voice-1", "text": "语音文案", "startSeconds": 1, "endSeconds": 4}],
        "overlayItems": [{"id": "overlay-1", "text": "旧文字", "startSeconds": 0, "endSeconds": 2}],
    }

    _pair_caption_tracks(sound)

    assert sound["overlayItems"][0]["syncVoiceId"] == "voice-1"
    assert sound["overlayItems"][0]["text"] == "语音文案"
    assert sound["overlayItems"][0]["startSeconds"] == 1
    assert sound["overlayItems"][0]["endSeconds"] == 4


def test_workspace_sound_config_has_priority_over_legacy_sound_node():
    draft = {
        "nodes": [{"data": {"kind": "sound", "bgmName": "旧 BGM"}}],
        "composeWorkspaces": [{"id": "compose_2", "soundConfig": {"bgmName": "方案 BGM", "bgmUrl": "/方案.mp3"}}],
    }

    assert _sound_node(draft, "compose_2")["bgmName"] == "方案 BGM"


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
