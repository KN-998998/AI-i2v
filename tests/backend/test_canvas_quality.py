"""A 层硬伤检测：阈值、扣分、以及和 analyze_video 的接线。

阈值不是拍脑袋定的，是在 10 条工具已生成的片段和 4 条 ffmpeg 合成的对照片上标定的
（数字记在 canvas_quality.py 顶部的注释里）。这里用当时实测的数值当样本，任何人改了
阈值都会在这些用例上立刻看到后果。
"""
import shutil
import subprocess

import pytest

from web.services import canvas_quality
from web.services.canvas_quality import _hard_fault_checks, analyze_video

# 2026-09-18 实测值，逐帧统计都在 180px 宽的灰度图上做。
FROZEN = {"frameChecksOk": True, "frameDelta": 0.001, "flickerStd": 0.001, "edgeCorrelation": 1.0}
TINY_SHAKE = {"frameChecksOk": True, "frameDelta": 0.009, "flickerStd": 0.015, "edgeCorrelation": 1.0}
WEAK_MOTION = {"frameChecksOk": True, "frameDelta": 0.075, "flickerStd": 0.038, "edgeCorrelation": 0.998}
SLOW_ZOOM = {"frameChecksOk": True, "frameDelta": 1.479, "flickerStd": 0.075, "edgeCorrelation": 0.951}
FLICKERING = {"frameChecksOk": True, "frameDelta": 13.219, "flickerStd": 22.010, "edgeCorrelation": 0.993}
GREW_A_LEAF = {"frameChecksOk": True, "frameDelta": 0.960, "flickerStd": 0.078, "edgeCorrelation": 0.040}


def test_a_frozen_clip_is_sent_back_for_a_redo():
    penalty, redo, notes = _hard_fault_checks(FROZEN, 0.0)
    assert penalty == 25
    assert redo == ["整段几乎没有动，看着就是一张静止图片"]
    assert notes == []


def test_a_barely_shaking_clip_counts_as_frozen_too():
    _, redo, _ = _hard_fault_checks(TINY_SHAKE, 0.0)
    assert redo, "±2px 的抖动和完全静止对观众没有区别"


def test_the_slow_push_in_the_prompt_asks_for_passes_untouched():
    """提示词要求的就是极慢匀速运镜，这条要是被判重做，整套阈值就没用了。"""
    penalty, redo, notes = _hard_fault_checks(SLOW_ZOOM, 0.0)
    assert (penalty, redo, notes) == (0, [], [])


def test_weak_motion_is_only_a_note_not_a_redo():
    penalty, redo, notes = _hard_fault_checks(WEAK_MOTION, 0.0)
    assert redo == [], "真实生成的片段最静也有 0.075，不能直接判死"
    assert penalty == 8
    assert notes and "轻微" in notes[0]


def test_brightness_jumps_are_a_redo():
    _, redo, _ = _hard_fault_checks(FLICKERING, 0.0)
    assert any("闪烁" in item for item in redo)


def test_something_growing_into_the_frame_edge_is_a_redo():
    """实测那条末帧右侧长出一片绿叶的片段，边缘相关只有 0.040。"""
    _, redo, _ = _hard_fault_checks(GREW_A_LEAF, 0.0)
    assert any("边缘" in item for item in redo)


def test_a_long_freeze_is_a_redo_but_a_short_one_is_only_a_note():
    _, long_redo, _ = _hard_fault_checks(SLOW_ZOOM, 1.4)
    assert any("卡住" in item for item in long_redo)
    _, short_redo, short_notes = _hard_fault_checks(SLOW_ZOOM, 0.4)
    assert short_redo == []
    assert short_notes and "静止" in short_notes[0]


def test_unreadable_frames_do_not_invent_faults():
    """cv2 读不出帧时只剩 freezedetect 能说话，不能因为拿不到数字就判人家重做。"""
    penalty, redo, notes = _hard_fault_checks({"frameChecksOk": False}, 0.0)
    assert (penalty, redo, notes) == (0, [], [])


def _fake_probe(_path):
    return {
        "streams": [{"codec_type": "video", "width": 1080, "height": 1920, "avg_frame_rate": "30/1", "codec_name": "h264"}],
        "format": {"duration": "3.0"},
    }


def test_analyze_video_reports_the_redo_verdict_and_the_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_quality, "_probe_media", _fake_probe)
    monkeypatch.setattr(canvas_quality, "_timing_and_freeze_checks", lambda _p: {"vfrRatio": 0.0, "maxFreezeSeconds": 0.0, "decodeOk": True})
    monkeypatch.setattr(canvas_quality, "_frame_diagnostics", lambda _p: dict(FROZEN))

    result = analyze_video(tmp_path / "clip.mp4", "玉子寿司", "寿司", deep_checks=True)

    assert result["redoRecommended"] is True
    assert result["redoReasons"] == ["整段几乎没有动，看着就是一张静止图片"]
    # 硬伤也要落进 qualityWarnings，只读警告的旧代码才不会漏掉。
    assert result["redoReasons"][0] in result["qualityWarnings"]
    assert result["qualityScore"] == 75


def test_a_quick_analysis_never_flags_a_redo(monkeypatch, tmp_path):
    """列表页那种不做深度检查的调用，不能凭空给片段扣上重做的帽子。"""
    monkeypatch.setattr(canvas_quality, "_probe_media", _fake_probe)
    monkeypatch.setattr(canvas_quality, "_frame_diagnostics", lambda _p: pytest.fail("浅分析不应该逐帧读视频"))

    result = analyze_video(tmp_path / "clip.mp4", "玉子寿司", "寿司")

    assert result["redoRecommended"] is False
    assert result["redoReasons"] == []


def _render(command: list[str]) -> bool:
    return subprocess.run(command, capture_output=True, check=False).returncode == 0


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="需要 ffmpeg 才能造对照片段")
def test_frame_diagnostics_separate_a_frozen_clip_from_a_slow_push_in(tmp_path):
    """端到端跑一遍真正的逐帧统计，守住「完全静止」和「想要的慢推近」之间那条线。"""
    pytest.importorskip("cv2")
    still = tmp_path / "still.png"
    assert _render(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=360x640:duration=1", "-vframes", "1", str(still)])
    frozen = tmp_path / "frozen.mp4"
    zooming = tmp_path / "zooming.mp4"
    assert _render(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(still), "-t", "2", "-r", "30", "-pix_fmt", "yuv420p", str(frozen)])
    assert _render([
        "ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(still), "-t", "2", "-r", "30",
        "-vf", "scale=720:1280,zoompan=z='1+0.08*on/60':d=60:s=360x640:fps=30", "-pix_fmt", "yuv420p", str(zooming),
    ])

    frozen_stats = canvas_quality._frame_diagnostics(frozen)
    zoom_stats = canvas_quality._frame_diagnostics(zooming)

    assert frozen_stats["frameChecksOk"] and zoom_stats["frameChecksOk"]
    assert frozen_stats["frameDelta"] < canvas_quality._FROZEN_FRAME_DELTA
    assert zoom_stats["frameDelta"] > canvas_quality._WEAK_FRAME_DELTA
    assert _hard_fault_checks(frozen_stats, 0.0)[1], "静止片段必须被判重做"
    assert _hard_fault_checks(zoom_stats, 0.0)[1] == [], "慢推近不能被判重做"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="需要 ffmpeg 才能造对照片段")
def test_frame_diagnostics_catch_brightness_jumps(tmp_path):
    pytest.importorskip("cv2")
    flickering = tmp_path / "flicker.mp4"
    assert _render([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=2",
        "-vf", "eq=brightness='0.12*sin(2*PI*6*t)':eval=frame", "-pix_fmt", "yuv420p", str(flickering),
    ])

    stats = canvas_quality._frame_diagnostics(flickering)

    assert stats["flickerStd"] > canvas_quality._FLICKER_STD
    assert any("闪烁" in item for item in _hard_fault_checks(stats, 0.0)[1])


def test_an_unreadable_file_degrades_to_no_frame_checks(tmp_path):
    """视频坏了、或者 cv2 没装好时，整条分析要照常返回，只是少了逐帧那几项。"""
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not a video")

    assert canvas_quality._frame_diagnostics(clip) == {"frameChecksOk": False}


# ---------------------------------------------------------------------------
# 第十一批：每段只用"动得最多"的 1.8 秒
# 参考片的单镜头中位时长是 1.53 秒（四分位 0.98–1.98，见 docs/reference_profile.json），
# 工具原来固定把 3 秒片段截成 2.5 秒用掉，节奏明显更拖。
# ---------------------------------------------------------------------------
def test_the_target_clip_length_comes_from_the_reference_profile():
    assert canvas_quality.TARGET_CLIP_SECONDS == 1.8


def test_a_clip_shorter_than_the_window_is_used_whole():
    """片段本身还没窗口长时，原样用完，别去切。"""
    start, end = canvas_quality._best_motion_window([1.0] * 10, 30.0, 1.8)
    assert start == 0.0
    assert round(end, 2) == round(11 / 30, 2)


def test_the_window_lands_where_the_motion_is():
    """前 2 秒几乎不动、后 1 秒动得厉害的片子，窗口要贴着片尾。"""
    deltas = [0.01] * 60 + [5.0] * 29
    start, end = canvas_quality._best_motion_window(deltas, 30.0, 1.0)
    assert round(end, 1) == 3.0
    assert round(end - start, 1) == 1.0


def test_the_window_is_exactly_as_long_as_asked():
    start, end = canvas_quality._best_motion_window([1.0] * 89, 30.0, 1.8)
    assert round(end - start, 2) == 1.8


def test_an_evenly_paced_clip_starts_from_the_beginning():
    """全片动得一样多时取最靠前的窗口，同一个片段每次算出来要一样。"""
    start, _end = canvas_quality._best_motion_window([1.0] * 89, 30.0, 1.8)
    assert start == 0.0


def test_a_quick_analysis_does_not_guess_a_window(monkeypatch, tmp_path):
    """浅分析没有逐帧数据，就不该凭空给出一个窗口。"""
    monkeypatch.setattr(canvas_quality, "_probe_media", _fake_probe)
    monkeypatch.setattr(canvas_quality, "_frame_diagnostics", lambda _p: pytest.fail("浅分析不应该逐帧读视频"))

    result = analyze_video(tmp_path / "clip.mp4", "玉子寿司", "寿司")

    assert "bestWindowStart" not in result or result.get("bestWindowStart") is None


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="需要 ffmpeg 才能造对照片段")
def test_frame_diagnostics_pick_the_liveliest_part_of_a_real_clip(tmp_path):
    """端到端：2 秒静止 + 1 秒晃动拼起来的片子，窗口必须落在后面那一秒。"""
    pytest.importorskip("cv2")
    still = tmp_path / "still.png"
    frozen = tmp_path / "frozen.mp4"
    moving = tmp_path / "moving.mp4"
    joined = tmp_path / "joined.mp4"
    listing = tmp_path / "list.txt"
    assert _render(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=#334455:size=360x640:duration=1", "-vframes", "1", str(still)])
    assert _render(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(still), "-t", "2", "-r", "30", "-pix_fmt", "yuv420p", str(frozen)])
    assert _render(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=1", "-pix_fmt", "yuv420p", str(moving)])
    listing.write_text(f"file '{frozen}'\nfile '{moving}'\n", encoding="utf-8")
    assert _render(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(joined)])

    stats = canvas_quality._frame_diagnostics(joined)

    assert stats["frameChecksOk"]
    assert stats["bestWindowStart"] >= 1.0, "静止的那两秒不该被选中"
    assert stats["bestWindowEnd"] > 2.0
