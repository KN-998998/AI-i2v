import time
from pathlib import Path

from pipeline import video_render
from pipeline.video_render import _typewriter_char_width, _typewriter_prefixes
from web.services.canvas_compose import _overlay_items, _pair_caption_tracks, _sound_node, _sync_caption_timings, _voice_items
from web.services import canvas_compose, canvas_quality, canvas_state

import pytest


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


def test_preflight_blocks_real_clip_whose_trim_was_dragged_but_not_confirmed(monkeypatch, tmp_path):
    """第十五批改了约定：没有 trimConfirmed = 工具挑的窗口 = 已确认；只有明确的 False（人拖过）才拦。"""
    clip_path = tmp_path / "clip.mp4"
    clip_path.write_bytes(b"video")
    monkeypatch.setattr(canvas_quality, "analyze_video", lambda *args: {"qualityLabel": "good"})

    report = canvas_quality.preflight_draft(
        {"timeline": [{"id": "clip", "dish": "测试菜", "sourcePath": str(clip_path), "timelineDuration": 2.5, "trimConfirmed": False}]},
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


# ---------------------------------------------------------------------------
# 字体解析：仓库原来写死 Windows 路径，线上是 Debian 容器，ffmpeg 不报错、默默换成
# 一个不含中文的字体，中文字幕全变方框。这几条用例守住"必须解析到真实存在的文件"。
# ---------------------------------------------------------------------------
def test_caption_font_prefers_the_explicit_environment_override(monkeypatch, tmp_path):
    font = tmp_path / "my.ttc"
    font.write_bytes(b"font")
    monkeypatch.setenv("CAPTION_FONT_FILE", str(font))
    video_render.resolve_caption_font.cache_clear()

    assert video_render.resolve_caption_font() == str(font)
    assert video_render.caption_font_missing() is False


def test_caption_font_falls_back_to_a_font_that_actually_exists(monkeypatch, tmp_path):
    installed = tmp_path / "NotoSansCJK-Regular.ttc"
    installed.write_bytes(b"font")
    monkeypatch.delenv("CAPTION_FONT_FILE", raising=False)
    monkeypatch.setattr(video_render, "_WINDOWS_FONTS", {("Microsoft YaHei", "normal"): "C:/Windows/Fonts/msyh.ttc"})
    monkeypatch.setattr(video_render, "_FALLBACK_FONTS", (str(installed),))
    video_render.resolve_caption_font.cache_clear()

    assert video_render.resolve_caption_font("Microsoft YaHei", "normal") == str(installed)


def test_caption_font_reports_missing_instead_of_pretending(monkeypatch):
    monkeypatch.delenv("CAPTION_FONT_FILE", raising=False)
    monkeypatch.setattr(video_render, "_WINDOWS_FONTS", {})
    monkeypatch.setattr(video_render, "_FALLBACK_FONTS", ())
    video_render.resolve_caption_font.cache_clear()

    assert video_render.resolve_caption_font() == ""
    assert video_render.caption_font_missing() is True
    # 找不到字体时不写 fontfile，交给 ffmpeg 自己兜底，而不是塞一个不存在的路径。
    assert video_render._font_file("Microsoft YaHei", "normal") == ""


def test_subtitles_never_reference_a_windows_path_that_is_not_there(monkeypatch, tmp_path):
    installed = tmp_path / "cjk.ttc"
    installed.write_bytes(b"font")
    monkeypatch.setenv("CAPTION_FONT_FILE", str(installed))
    video_render.resolve_caption_font.cache_clear()
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    commands = []
    monkeypatch.setattr(video_render, "_run_ffmpeg", lambda command, timeout, action: commands.append(command))

    video_render.concat_clips([str(source)], str(tmp_path / "out.mp4"), subtitles=[{"text": "寿司", "start": 0, "end": 2}])

    vf = commands[0][commands[0].index("-vf") + 1]
    assert "C:/Windows" not in vf
    assert installed.name in vf


# ---------------------------------------------------------------------------
# 开头淡入 + 片尾信息卡：11 条参考片里 9 条有淡入、11 条全有片尾卡，工具原来一样都没有。
# ---------------------------------------------------------------------------
def test_every_composition_fades_in(monkeypatch, tmp_path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    commands = []
    monkeypatch.setattr(video_render, "_run_ffmpeg", lambda command, timeout, action: commands.append(command))

    video_render.concat_clips([str(source)], str(tmp_path / "out.mp4"), subtitles=[])

    vf = commands[0][commands[0].index("-vf") + 1]
    assert vf.endswith(f"fade=t=in:st=0:d={video_render.FADE_IN_SECONDS}"), "淡入要放在最后一环，字幕才会跟着一起淡进来"


def test_the_end_card_renders_three_centred_lines(monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(video_render, "_run_ffmpeg", lambda command, timeout, action: commands.append(command))

    result = video_render.render_end_card(tmp_path / "card.mp4", ["和心居酒屋", "旺角登打士街 32 号", "搜尋「和心」"])

    assert result == str(tmp_path / "card.mp4")
    vf = commands[0][commands[0].index("-vf") + 1]
    assert vf.count("drawtext=") == 3
    assert "和心居酒屋" in vf and "x=(w-text_w)/2" in vf


def test_no_lines_means_no_end_card(monkeypatch, tmp_path):
    monkeypatch.setattr(video_render, "_run_ffmpeg", lambda command, timeout, action: pytest.fail("没有文案时不该调 ffmpeg"))

    assert video_render.render_end_card(tmp_path / "card.mp4", ["", "  "]) is None


def test_the_end_card_text_comes_from_the_template_then_from_the_env(monkeypatch):
    monkeypatch.setattr(canvas_compose, "BRAND_END_CARD_LINES", ["全局店名", "全局地址"])

    assert canvas_compose._end_card_lines({}) == ["全局店名", "全局地址"]
    assert canvas_compose._end_card_lines({"endCardLines": ["样板店名"]}) == ["样板店名"]
    assert canvas_compose._end_card_lines({"endCardEnabled": False}) == []
    # 样板里写了空字符串不算配置过，还是走全局的。
    assert canvas_compose._end_card_lines({"endCardLines": ["", " "]}) == ["全局店名", "全局地址"]


def test_the_end_card_is_appended_as_an_ordinary_segment(monkeypatch, tmp_path):
    """片尾卡就是接在最后的一段普通视频，所以拼接逻辑和字幕时间轴都不用改。"""
    monkeypatch.setattr(canvas_compose, "BRAND_END_CARD_LINES", ["和心居酒屋"])
    monkeypatch.setattr(video_render, "render_end_card", lambda destination, lines, **_kwargs: str(destination))
    clips: list[str] = ["/tmp/segment_000.mp4"]
    temporary: list[str] = []

    seconds = canvas_compose._append_end_card(tmp_path, {}, clips, temporary)

    assert seconds == video_render.END_CARD_SECONDS
    assert clips[-1].endswith("end_card.mp4")
    assert temporary == [clips[-1]], "片尾卡也要登记成临时文件，任务结束后跟着清掉"


# ---------------------------------------------------------------------------
# 第十四批：字幕不画到片尾卡上
# 9/21 真片：默认文案「本周限定优惠」的时间段是 0–2.5s，成片内容只有 1.8s，片尾卡从 1.8s
# 开始，字幕就压在店名地址上。字幕的结束时间要夹到「内容时长 = 总时长 − 片尾卡」。
# ---------------------------------------------------------------------------
def test_overlays_are_clamped_to_the_content_before_the_end_card():
    sound = {"overlayItems": [
        {"id": "a", "text": "本周限定优惠", "startSeconds": 0, "endSeconds": 2.5},
        {"id": "b", "text": "片尾才出现", "startSeconds": 2.0, "endSeconds": 2.6},
    ]}

    items = _overlay_items(sound, content_seconds=1.8)

    assert [item["text"] for item in items] == ["本周限定优惠"], "整段都落在片尾卡上的字幕直接不画"
    assert items[0]["end"] == 1.8


def test_overlays_without_a_content_limit_keep_their_own_timing():
    items = _overlay_items({"overlayItems": [{"id": "a", "text": "x", "startSeconds": 0, "endSeconds": 2.5}]})

    assert items[0]["end"] == 2.5


def test_a_rendered_video_never_burns_captions_over_the_end_card(monkeypatch, tmp_path):
    """端到端走恢复路径：1.8s 内容 + 1s 片尾卡，字幕配的是 0–2.5s，烧进去的必须停在 1.8s。"""
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    monkeypatch.setattr(canvas_compose, "BRAND_END_CARD_LINES", ["和心居酒屋"])
    from web.services import default_bgm

    monkeypatch.setattr(default_bgm, "DEFAULT_BGM_DIR", tmp_path / "no-bgm")
    canvas_state.save_draft("default", {"nodes": [], "edges": [], "timeline": []})
    clip = {"id": "clip-1", "dish": "玉子寿司", "timelineDuration": 1.8, "sourceStartSeconds": 1.0, "sourceEndSeconds": 2.8, "trimConfirmed": True}
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    monkeypatch.setattr(canvas_compose, "_prepare_sources", lambda _draft_id, timeline: [(timeline[0], source)])
    monkeypatch.setattr(video_render, "trim_clip", lambda _source, destination, start, duration: Path(destination).write_bytes(b"trimmed"))
    monkeypatch.setattr(video_render, "render_end_card", lambda destination, lines, **_kwargs: (Path(destination).write_bytes(b"card"), str(destination))[1])
    burned: list[list[dict]] = []

    def fake_concat(_sources, destination, subtitles, brand_info):
        burned.append(subtitles)
        Path(destination).write_bytes(b"composed")

    monkeypatch.setattr(video_render, "concat_clips", fake_concat)
    job = {
        "job_id": "f" * 32, "draft_id": "default", "status": "running", "workspace_id": None, "include_sound": True,
        "timeline": [clip],
        "sound": {"bgmMode": "none", "overlayItems": [{"id": "a", "text": "本周限定优惠", "startSeconds": 0, "endSeconds": 2.5}]},
    }
    canvas_compose._save_job("default", job)

    assert canvas_compose.recover_compose_jobs() == 1
    for _ in range(40):
        current = canvas_compose.get_compose_job("default", job["job_id"])
        if current and current["status"] in {"done", "error"}:
            break
        time.sleep(0.05)

    assert current["status"] == "done", current.get("error")
    assert burned and burned[0][0]["text"] == "本周限定优惠"
    assert abs(burned[0][0]["end"] - 1.8) < 1e-6, "字幕在片尾卡开始的那一刻就该消失"


# ---------------------------------------------------------------------------
# 第十四批：ffmpeg 会不会画字，要在预检里查，不能等合成到片尾卡才炸
# 9/21 Patrick 的 Homebrew ffmpeg 9.0.2 没编 freetype，点「合成此条」才报
# "No such filter: 'drawtext'"，还是一屏 ffmpeg 原文。
# ---------------------------------------------------------------------------
class _Completed:
    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_drawtext_capability_is_read_from_the_filter_list(monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return _Completed(0, stdout=b" ... drawtext          V->V       Draw text on top of video frames using libfreetype library.\n")

    monkeypatch.setattr(video_render.subprocess, "run", fake_run)
    video_render.ffmpeg_can_draw_text.cache_clear()

    assert video_render.ffmpeg_can_draw_text() is True
    assert video_render.drawtext_missing() is False
    assert calls and calls[0][0] == "ffmpeg" and "-filters" in calls[0]


def test_drawtext_capability_reports_missing_when_the_filter_is_absent(monkeypatch):
    monkeypatch.setattr(video_render.subprocess, "run", lambda command, **_kwargs: _Completed(0, stdout=b" ... scale   V->V   Scale the input video.\n"))
    video_render.ffmpeg_can_draw_text.cache_clear()

    assert video_render.ffmpeg_can_draw_text() is False
    assert video_render.drawtext_missing() is True


def test_drawtext_capability_is_missing_when_ffmpeg_itself_is_missing(monkeypatch):
    def boom(command, **_kwargs):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(video_render.subprocess, "run", boom)
    video_render.ffmpeg_can_draw_text.cache_clear()

    assert video_render.ffmpeg_can_draw_text() is False


def test_a_missing_drawtext_filter_is_explained_in_plain_words(monkeypatch, tmp_path):
    stderr = b"[AVFilterGraph @ 0x1] No such filter: 'drawtext'\nError opening output file /x/end_card.mp4.\nError opening output files: Filter not found\n"
    monkeypatch.setattr(video_render.subprocess, "run", lambda command, **_kwargs: _Completed(1, stderr=stderr))

    with pytest.raises(RuntimeError) as failure:
        video_render.render_end_card(tmp_path / "card.mp4", ["和心居酒屋"])

    message = str(failure.value)
    assert "画字" in message or "drawtext" in message
    assert "brew install" in message, "报错里直接给修法，别让人去查 ffmpeg 原文"
    assert "AVFilterGraph" not in message, "一屏 ffmpeg 原文对运营没有意义"


def _preflight_draft_with_one_ready_clip(tmp_path):
    clip_path = tmp_path / "clip.mp4"
    clip_path.write_bytes(b"video")
    return {"timeline": [{"id": "clip", "dish": "玉子寿司", "sourcePath": str(clip_path), "timelineDuration": 1.8, "trimConfirmed": True}]}


def test_preflight_blocks_when_the_end_card_needs_drawtext_the_machine_lacks(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_quality, "analyze_video", lambda *_args: {"qualityLabel": "good"})
    monkeypatch.setattr(canvas_compose, "BRAND_END_CARD_LINES", ["和心居酒屋"])
    monkeypatch.setattr(video_render, "drawtext_missing", lambda: True)

    report = canvas_quality.preflight_draft(_preflight_draft_with_one_ready_clip(tmp_path), "default", include_sound=False)

    codes = [item["code"] for item in report["errors"]]
    assert "MISSING_DRAWTEXT" in codes
    message = next(item["message"] for item in report["errors"] if item["code"] == "MISSING_DRAWTEXT")
    assert "brew install" in message
    assert report["ok"] is False


def test_preflight_blocks_when_captions_need_drawtext_the_machine_lacks(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_quality, "analyze_video", lambda *_args: {"qualityLabel": "good"})
    monkeypatch.setattr(canvas_compose, "BRAND_END_CARD_LINES", [])
    monkeypatch.setattr(video_render, "drawtext_missing", lambda: True)
    draft = _preflight_draft_with_one_ready_clip(tmp_path)
    draft["nodes"] = [{"id": "sound", "data": {"kind": "sound", "endCardEnabled": False, "overlayItems": [{"id": "a", "text": "本周限定优惠", "startSeconds": 0, "endSeconds": 1.5}]}}]

    report = canvas_quality.preflight_draft(draft, "default", include_sound=True)

    assert "MISSING_DRAWTEXT" in [item["code"] for item in report["errors"]]


def test_preflight_does_not_mention_drawtext_when_nothing_needs_it(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_quality, "analyze_video", lambda *_args: {"qualityLabel": "good"})
    monkeypatch.setattr(canvas_compose, "BRAND_END_CARD_LINES", [])
    monkeypatch.setattr(video_render, "drawtext_missing", lambda: True)
    draft = _preflight_draft_with_one_ready_clip(tmp_path)
    draft["nodes"] = [{"id": "sound", "data": {"kind": "sound", "endCardEnabled": False, "overlayItems": []}}]

    report = canvas_quality.preflight_draft(draft, "default", include_sound=True)

    assert "MISSING_DRAWTEXT" not in [item["code"] for item in report["errors"]]


def test_preflight_is_quiet_about_drawtext_when_ffmpeg_can_draw(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_quality, "analyze_video", lambda *_args: {"qualityLabel": "good"})
    monkeypatch.setattr(canvas_compose, "BRAND_END_CARD_LINES", ["和心居酒屋"])
    monkeypatch.setattr(video_render, "drawtext_missing", lambda: False)

    report = canvas_quality.preflight_draft(_preflight_draft_with_one_ready_clip(tmp_path), "default", include_sound=False)

    assert "MISSING_DRAWTEXT" not in [item["code"] for item in report["errors"]]


# ---------------------------------------------------------------------------
# 第十四批：默认曲库
# ---------------------------------------------------------------------------
def _bgm_pool(tmp_path, names):
    pool = tmp_path / "bgm"
    pool.mkdir(exist_ok=True)
    for name in names:
        (pool / name).write_bytes(b"mp3")
    return pool


def test_bgm_mode_is_read_the_same_way_as_the_frontend():
    from web.services.default_bgm import bgm_mode

    assert bgm_mode({"bgmMode": "none", "bgmName": "默认 BGM", "bgmUrl": ""}) == "none"
    assert bgm_mode({"bgmName": "song.mp3", "bgmUrl": "/api/canvas/drafts/d/files/x.mp3"}) == "custom"
    assert bgm_mode({"bgmName": "默认 BGM", "bgmUrl": ""}) == "default", "老草稿里那个只有名字的「默认 BGM」，现在真的给音乐"
    assert bgm_mode({"bgmName": "默认曲库", "bgmUrl": ""}) == "default"
    assert bgm_mode({"bgmName": "", "bgmUrl": ""}) == "none"
    assert bgm_mode({}) == "none"


def test_the_default_library_lists_audio_files_only(monkeypatch, tmp_path):
    from web.services import default_bgm

    monkeypatch.setattr(default_bgm, "DEFAULT_BGM_DIR", _bgm_pool(tmp_path, ["b.mp3", "a.mp3", "readme.md", ".DS_Store", "c.m4a"]))

    names = [item["name"] for item in default_bgm.list_default_bgm()]

    assert names == ["a.mp3", "b.mp3", "c.m4a"]
    assert all(item["url"] == f"/api/canvas/bgm/default/{item['name']}" for item in default_bgm.list_default_bgm())


def test_the_default_library_is_empty_when_the_folder_is_missing(monkeypatch, tmp_path):
    from web.services import default_bgm

    monkeypatch.setattr(default_bgm, "DEFAULT_BGM_DIR", tmp_path / "missing")

    assert default_bgm.list_default_bgm() == []
    assert default_bgm.pick_default_bgm("any-seed") is None


def test_each_video_gets_a_stable_pick_from_the_default_library(monkeypatch, tmp_path):
    """同一条成片重渲染要拿到同一首（按任务号定），不同成片之间要轮着来。"""
    from web.services import default_bgm

    monkeypatch.setattr(default_bgm, "DEFAULT_BGM_DIR", _bgm_pool(tmp_path, ["a.mp3", "b.mp3", "c.mp3"]))

    picks = {seed: default_bgm.pick_default_bgm(seed) for seed in ("job-1", "job-2", "job-3", "job-4", "job-5", "job-6", "job-7", "job-8")}

    assert all(path is not None and path.parent == default_bgm.DEFAULT_BGM_DIR for path in picks.values())
    assert default_bgm.pick_default_bgm("job-1") == picks["job-1"]
    assert len({path.name for path in picks.values()}) == 3, "8 条成片下来三首都该轮到"


def test_resolve_bgm_path_follows_the_mode(monkeypatch, tmp_path):
    from web.services import default_bgm

    monkeypatch.setattr(default_bgm, "DEFAULT_BGM_DIR", _bgm_pool(tmp_path, ["a.mp3"]))
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    uploaded_dir = canvas_state.draft_directory("default") / "files"
    uploaded_dir.mkdir(parents=True)
    (uploaded_dir / "own.mp3").write_bytes(b"mp3")

    assert default_bgm.resolve_bgm_path("default", {"bgmName": "默认 BGM", "bgmUrl": ""}, "job-1") == default_bgm.DEFAULT_BGM_DIR / "a.mp3"
    assert default_bgm.resolve_bgm_path("default", {"bgmName": "own.mp3", "bgmUrl": "/api/canvas/drafts/default/files/own.mp3"}, "job-1") == uploaded_dir / "own.mp3"
    assert default_bgm.resolve_bgm_path("default", {"bgmMode": "none", "bgmName": "默认 BGM", "bgmUrl": ""}, "job-1") is None


def test_preflight_warns_when_the_default_library_is_empty(monkeypatch, tmp_path):
    from web.services import default_bgm

    monkeypatch.setattr(canvas_quality, "analyze_video", lambda *_args: {"qualityLabel": "good"})
    monkeypatch.setattr(canvas_compose, "BRAND_END_CARD_LINES", [])
    monkeypatch.setattr(video_render, "drawtext_missing", lambda: False)
    monkeypatch.setattr(default_bgm, "DEFAULT_BGM_DIR", tmp_path / "missing")
    draft = _preflight_draft_with_one_ready_clip(tmp_path)
    draft["nodes"] = [{"id": "sound", "data": {"kind": "sound", "endCardEnabled": False, "bgmName": "默认 BGM", "bgmUrl": ""}}]

    report = canvas_quality.preflight_draft(draft, "default", include_sound=True)

    codes = [item["code"] for item in report["warnings"]]
    assert "DEFAULT_BGM_EMPTY" in codes
    assert "MISSING_BGM" not in codes, "默认曲库空了是另一回事，别报成「本地音频文件不存在」"
    message = next(item["message"] for item in report["warnings"] if item["code"] == "DEFAULT_BGM_EMPTY")
    assert "assets/bgm/default" in message


# ---------------------------------------------------------------------------
# 第十五批（二）：预检只拦「人拖过又没确认」的裁剪
# ---------------------------------------------------------------------------
def test_preflight_only_blocks_a_trim_someone_dragged_and_left_unconfirmed(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_quality, "analyze_video", lambda *_args: {"qualityLabel": "good"})
    monkeypatch.setattr(canvas_compose, "BRAND_END_CARD_LINES", [])
    monkeypatch.setattr(video_render, "drawtext_missing", lambda: False)
    draft = _preflight_draft_with_one_ready_clip(tmp_path)
    del draft["timeline"][0]["trimConfirmed"]

    report = canvas_quality.preflight_draft(draft, "default", include_sound=False)

    assert "TRIM_NOT_CONFIRMED" not in [item["code"] for item in report["errors"]], "没有这个字段 = 工具给的窗口 = 已确认"
    assert report["ok"] is True

    draft["timeline"][0]["trimConfirmed"] = False
    report = canvas_quality.preflight_draft(draft, "default", include_sound=False)

    assert "TRIM_NOT_CONFIRMED" in [item["code"] for item in report["errors"]], "人拖过入点出点又没确认，才拦"


# ---------------------------------------------------------------------------
# 第十五批（四）：默认曲库可以指定一首
# bgmTrack 是曲库里的文件名；空 / 没有 = 随机（第十四批的行为不变）。
# ---------------------------------------------------------------------------
def test_a_pinned_track_beats_the_stable_pick(monkeypatch, tmp_path):
    from web.services import default_bgm

    monkeypatch.setattr(default_bgm, "DEFAULT_BGM_DIR", _bgm_pool(tmp_path, ["a.mp3", "b.mp3", "c.mp3"]))

    assert all(default_bgm.pick_default_bgm(seed, "b.mp3") == default_bgm.DEFAULT_BGM_DIR / "b.mp3" for seed in ("job-1", "job-2", "job-3")), "指定了就每条都是它"
    assert default_bgm.pick_default_bgm("job-1", "") == default_bgm.pick_default_bgm("job-1"), "空字符串 = 没指定 = 随机"
    assert default_bgm.pick_default_bgm("job-1", None) == default_bgm.pick_default_bgm("job-1")


def test_a_missing_or_unsafe_pin_falls_back_to_the_stable_pick(monkeypatch, tmp_path):
    from web.services import default_bgm

    monkeypatch.setattr(default_bgm, "DEFAULT_BGM_DIR", _bgm_pool(tmp_path, ["a.mp3", "b.mp3", "readme.md"]))
    (tmp_path / "secret.mp3").write_bytes(b"mp3")

    assert default_bgm.pick_default_bgm("job-1", "gone.mp3") == default_bgm.pick_default_bgm("job-1"), "曲子被人拿走了：不报错，改用随机"
    assert default_bgm.pick_default_bgm("job-1", "../secret.mp3") == default_bgm.pick_default_bgm("job-1"), "只认曲库里的纯文件名"
    assert default_bgm.pick_default_bgm("job-1", "readme.md") == default_bgm.pick_default_bgm("job-1"), "不是音频的文件不能被指定"
    assert default_bgm.has_default_track("a.mp3") is True
    assert default_bgm.has_default_track("gone.mp3") is False
    assert default_bgm.has_default_track("../secret.mp3") is False
    assert default_bgm.has_default_track("") is False


def test_resolve_bgm_path_honours_the_pinned_track(monkeypatch, tmp_path):
    from web.services import default_bgm

    monkeypatch.setattr(default_bgm, "DEFAULT_BGM_DIR", _bgm_pool(tmp_path, ["a.mp3", "b.mp3", "c.mp3"]))
    sound = {"bgmMode": "default", "bgmName": "默认曲库", "bgmUrl": "", "bgmTrack": "c.mp3"}

    assert default_bgm.resolve_bgm_path("default", sound, "job-1") == default_bgm.DEFAULT_BGM_DIR / "c.mp3"
    assert default_bgm.resolve_bgm_path("default", {**sound, "bgmTrack": ""}, "job-1") == default_bgm.pick_default_bgm("job-1")
    assert default_bgm.resolve_bgm_path("default", {**sound, "bgmMode": "none"}, "job-1") is None, "不要音乐时指定的曲子也不算数"


def test_preflight_warns_when_the_pinned_track_is_gone(monkeypatch, tmp_path):
    from web.services import default_bgm

    monkeypatch.setattr(canvas_quality, "analyze_video", lambda *_args: {"qualityLabel": "good"})
    monkeypatch.setattr(canvas_compose, "BRAND_END_CARD_LINES", [])
    monkeypatch.setattr(video_render, "drawtext_missing", lambda: False)
    monkeypatch.setattr(default_bgm, "DEFAULT_BGM_DIR", _bgm_pool(tmp_path, ["a.mp3"]))
    draft = _preflight_draft_with_one_ready_clip(tmp_path)
    draft["composeWorkspaces"] = [{"id": "compose_1", "clips": draft["timeline"], "soundConfig": {"bgmMode": "default", "bgmName": "默认曲库", "bgmUrl": "", "bgmTrack": "gone.mp3", "endCardEnabled": False}}]

    report = canvas_quality.preflight_draft(draft, "default", "compose_1", include_sound=True)

    codes = [item["code"] for item in report["warnings"]]
    assert "DEFAULT_BGM_TRACK_MISSING" in codes
    assert "DEFAULT_BGM_EMPTY" not in codes, "曲库不空，只是指定的那首不在"
    assert report["ok"] is True, "指定的曲子不在只是提示，改用随机一首，不拦合成"
    message = next(item["message"] for item in report["warnings"] if item["code"] == "DEFAULT_BGM_TRACK_MISSING")
    assert "gone.mp3" in message and "随机" in message

    draft["composeWorkspaces"][0]["soundConfig"]["bgmTrack"] = "a.mp3"
    report = canvas_quality.preflight_draft(draft, "default", "compose_1", include_sound=True)

    assert "DEFAULT_BGM_TRACK_MISSING" not in [item["code"] for item in report["warnings"]]
