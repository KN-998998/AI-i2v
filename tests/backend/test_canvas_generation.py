import time

from web.services import canvas_generation, canvas_state


def test_generation_upstream_requires_a_real_connection():
    draft = {
        "nodes": [
            {"id": "prompt", "data": {"kind": "prompt"}},
            {"id": "clips", "data": {"kind": "generator"}},
        ],
        "edges": [],
    }

    try:
        canvas_generation._upstream_data(draft, "clips", "prompt")
    except ValueError as error:
        assert "没有连接" in str(error)
    else:
        raise AssertionError("unlinked generation node unexpectedly used a legacy fallback")


def test_generation_upstream_rejects_multiple_connected_branches():
    draft = {
        "nodes": [
            {"id": "prompt_a", "data": {"kind": "prompt", "title": "A"}},
            {"id": "prompt_b", "data": {"kind": "prompt", "title": "B"}},
            {"id": "clips", "data": {"kind": "generator"}},
        ],
        "edges": [
            {"source": "prompt_a", "target": "clips"},
            {"source": "prompt_b", "target": "clips"},
        ],
    }

    try:
        canvas_generation._upstream_data(draft, "clips", "prompt")
    except ValueError as error:
        assert "多个" in str(error)
    else:
        raise AssertionError("multiple prompt branches were silently accepted")


def test_prompt_generation_inherits_mixed_food_type_from_input():
    prompt, _negative, _keyframe = canvas_generation._prompt_from_node({
        "foodType": "混合/多温",
        "promptConfig": {
            "mode": "single_image",
            "camera_move": "locked_off",
            "camera_amplitude": "subtle",
            "elements": ["dish_hot", "tableware", "surface"],
            "l1_subject": "dish_hot",
            "l2_dynamics": [],
        },
    })

    assert "【餐品属性】当前为套餐组合，包含冷食与热食" in prompt
    assert "套餐整体与各组成餐品保持原位不动" in prompt


def test_completed_generation_persists_clip_and_node_status(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    draft_id = "default"
    pending = {
        "id": "clips_clip",
        "dish": "测试菜",
        "label": "生成任务",
        "tone": "#355e62",
        "timelineDuration": 2.5,
        "status": "pending",
        "generatorNodeId": "clips",
    }
    canvas_state.save_draft(draft_id, {
        "nodes": [{"id": "clips", "data": {"kind": "generator", "status": "生成中"}}],
        "edges": [],
        "timeline": [pending],
        "candidateClips": [pending],
        "composeWorkspaces": [{"id": "compose_1", "title": "成片 1", "clips": [pending], "job": None}],
    })
    clip = {
        "id": "clip_canvas_test.mp4",
        "filename": "test.mp4",
        "dish": "测试菜",
        "label": "生成片段",
        "tone": "#355e62",
        "timelineDuration": 2.5,
        "status": "generated",
        "sourcePath": "C:/clips/test.mp4",
        "generatorNodeId": "clips",
    }

    canvas_generation._persist_generated_clip(draft_id, "clips", clip)

    saved = canvas_state.load_draft(draft_id)
    assert saved["nodes"][0]["data"]["status"] == "已生成"
    assert saved["candidateClips"][0]["id"] == "clips_clip"
    assert saved["candidateClips"][0]["sourcePath"] == "C:/clips/test.mp4"
    assert saved["timeline"][0]["status"] == "generated"
    assert saved["composeWorkspaces"][0]["clips"][0]["sourcePath"] == "C:/clips/test.mp4"


def test_startup_recovery_polls_task_downloads_and_persists_clip(monkeypatch, tmp_path):
    draft_root = tmp_path / "drafts"
    clip_root = tmp_path / "clips"
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", draft_root)
    monkeypatch.setattr(canvas_generation, "CANVAS_CLIP_ROOT", clip_root)
    canvas_state.save_draft(
        "default",
        {
            "nodes": [{"id": "clips", "data": {"kind": "generator", "status": "生成中"}}],
            "edges": [],
            "timeline": [],
            "candidateClips": [],
            "composeWorkspaces": [{"id": "compose_1", "title": "成片 1", "clips": [], "job": None}],
        },
    )
    job = {
        "job_id": "a" * 32,
        "draft_id": "default",
        "node_id": "clips",
        "status": "running",
        "task_id": "kling-task-1",
        "dish": "测试菜",
        "dish_category": "正餐",
        "duration": 3,
        "prompt": "food movement",
    }
    canvas_generation._save_job("default", job)

    class FakeSession:
        pass

    monkeypatch.setattr("pipeline.kling.session_with_retry", lambda: FakeSession())
    monkeypatch.setattr("pipeline.kling.wait_for_video", lambda _session, task_id: ("https://example.test/video.mp4", {"task_id": task_id}))

    def fake_download(_session, _url, output_path):
        path = tmp_path / "downloaded.mp4"
        path.write_bytes(b"mp4")
        import shutil
        from pathlib import Path
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, output_path)
        return 3

    monkeypatch.setattr("pipeline.kling.download_video", fake_download)
    monkeypatch.setattr(canvas_generation, "analyze_video", lambda *_args: {"durationSeconds": 3, "qualityScore": 90, "qualityLabel": "good", "qualityWarnings": [], "analysisMode": "technical_rules"})

    assert canvas_generation.recover_generation_jobs() == 1
    for _ in range(40):
        current = canvas_generation.get_generation_job("default", job["job_id"])
        if current and current["status"] in {"done", "error"}:
            break
        time.sleep(0.05)

    assert current["status"] == "done", current.get("error")
    assert current["task_id"] == "kling-task-1"
    assert current["clip"]["sourcePath"].endswith(".mp4")
    assert canvas_state.load_draft("default")["nodes"][0]["data"]["status"] == "已生成"


def test_startup_recovery_marks_job_without_task_id_as_unrecoverable(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    canvas_state.save_draft(
        "default",
        {
            "nodes": [{"id": "clips", "data": {"kind": "generator", "status": "生成中"}}],
            "edges": [],
            "timeline": [],
        },
    )
    job = {"job_id": "b" * 32, "draft_id": "default", "node_id": "clips", "status": "queued", "task_id": None}
    canvas_generation._save_job("default", job)

    assert canvas_generation.recover_generation_jobs() == 0
    current = canvas_generation.get_generation_job("default", job["job_id"])
    assert current["status"] == "error"
    assert "task_id" in current["error"]
