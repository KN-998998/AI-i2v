from web.services import canvas_generation, canvas_state


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
