from pipeline.video_render import _typewriter_prefixes
from web.services.canvas_compose import _overlay_items, _pair_caption_tracks, _sync_caption_timings


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
