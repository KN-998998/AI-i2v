import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from web.app import create_app
from web.services import canvas_state
from web.services import canvas_quality
from web.services import canvas_asset_library
from web.api import routes as api_routes


def test_canvas_routes_serve_react_page_only():
    client = TestClient(create_app())

    root_page = client.get("/")
    assert root_page.status_code == 200
    assert "/static/canvas-app/assets/index.js" in root_page.text

    react_page = client.get("/canvas-mvp")
    assert react_page.status_code == 200
    assert "/static/canvas-app/assets/index.js" in react_page.text

    assert client.get("/canvas-mvp-legacy").status_code == 404


def test_workflow_pages_use_react_spa_fallback():
    client = TestClient(create_app())
    for step in ("assets", "asset-library-review", "image-processing", "prompts", "generator", "timeline", "compose", "sound", "output"):
        response = client.get(f"/workflow/{step}")
        assert response.status_code == 200
        assert "/static/canvas-app/assets/index.js" in response.text
    assert client.get("/workflow/unknown").status_code == 404


def test_asset_library_rules_route_lists_saved_categories(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_asset_library, "_RULES_PATH", tmp_path / "rules.json")
    canvas_asset_library.save_category_rule("烤龙虾", "主菜", "热食")

    response = TestClient(create_app()).get("/api/canvas/asset-library/rules")

    assert response.status_code == 200
    assert response.json() == [{"dishName": "烤龙虾", "category": "主菜", "foodType": "热食"}]


def test_manual_asset_review_routes_require_confirmation_and_copy_images(monkeypatch, tmp_path):
    review_root = tmp_path / "review-scans"
    monkeypatch.setattr(canvas_asset_library, "_MANUAL_REVIEW_ROOT", review_root)
    source_root = tmp_path / "raw" / "寿司" / "三文鱼寿司"
    source_root.mkdir(parents=True)
    source_image = source_root / "dish.jpg"
    source_image.write_bytes(b"jpeg-bytes")
    target_root = tmp_path / "图片素材库"
    client = TestClient(create_app())

    scan_response = client.post(
        "/api/canvas/asset-library/manual-review/scans",
        params={"asset_root": str(tmp_path / "raw")},
    )

    assert scan_response.status_code == 200
    scan = scan_response.json()
    item = scan["items"][0]
    assert client.get(f"/api/canvas/asset-library/manual-review/scans/{scan['scanId']}").json() == scan
    preview = client.get(item["previewUrls"][0])
    assert preview.status_code == 200
    assert preview.content == b"jpeg-bytes"

    incomplete = client.post(
        "/api/canvas/asset-library/manual-review/organize",
        json={"scan_id": scan["scanId"], "target_root": str(target_root), "classifications": []},
    )
    assert incomplete.status_code == 400

    organized = client.post(
        "/api/canvas/asset-library/manual-review/organize",
        json={
            "scan_id": scan["scanId"],
            "target_root": str(target_root),
            "classifications": [{"dishKey": item["dishKey"], "category": "寿司", "foodType": "冷食"}],
        },
    )
    assert organized.status_code == 200
    assert organized.json()["imageCount"] == 1
    assert (target_root / "寿司" / "三文鱼寿司" / "dish.jpg").is_file()
    assert source_image.is_file()


def test_manual_asset_review_upload_route_preserves_folder_structure(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_asset_library, "_MANUAL_REVIEW_ROOT", tmp_path / "review-scans")
    response = TestClient(create_app()).post(
        "/api/canvas/asset-library/manual-review/scans/uploads",
        files=[("files", ("raw/寿司/三文鱼寿司/dish.jpg", b"jpeg-bytes", "image/jpeg"))],
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["dishName"] == "三文鱼寿司"
    assert response.json()["items"][0]["imageCount"] == 1


def test_canvas_draft_and_file_persistence(monkeypatch, tmp_path):
    test_root = tmp_path / "canvas-draft"
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", test_root)
    client = TestClient(create_app())
    payload = {
        "activePanel": "prompt",
        "nextNodeNumber": 3,
        "nodes": [{"id": "assets", "type": "workflow", "position": {"x": 10, "y": 20}, "data": {"kind": "input"}}],
        "edges": [],
        "timeline": [],
        "candidateClips": [],
        "composeBatchCount": 2,
        "composeClipCount": 3,
        "composeWorkspaces": [
            {"id": "compose_1", "title": "成片 1", "clips": [], "job": None},
            {"id": "compose_2", "title": "成片 2", "clips": [], "job": None},
        ],
        "bgmName": "默认 BGM",
        "bgmUrl": "",
        "assetLibraryPlan": {
            "assetRoot": "F:\\assets",
            "backgroundRoot": "F:\\backgrounds",
            "selected": [],
            "warnings": [],
            "categoryCounts": {"寿司": 2},
            "reviewItems": [{
                "dishName": "炙烧寿司",
                "sourceCategory": "未确认",
                "classificationReason": "名称存在多个候选分类",
                "categoryCandidates": ["寿司", "正餐"],
                "suggestedCategory": "寿司",
                "folderCount": 2,
            }],
        },
    }

    assert client.get("/api/canvas/drafts/default").status_code == 404
    saved = client.put("/api/canvas/drafts/default", json=payload)
    assert saved.status_code == 200
    assert saved.json()["version"] == 1
    assert client.get("/api/canvas/drafts/default").json()["nextNodeNumber"] == 3
    assert client.get("/api/canvas/drafts/default").json()["composeBatchCount"] == 2
    assert len(client.get("/api/canvas/drafts/default").json()["composeWorkspaces"]) == 2
    persisted_plan = client.get("/api/canvas/drafts/default").json()["assetLibraryPlan"]
    assert persisted_plan["assetRoot"] == "F:\\assets"
    assert persisted_plan["reviewItems"][0]["dishName"] == "炙烧寿司"

    uploaded = client.post(
        "/api/canvas/drafts/default/files",
        data={"kind": "image"},
        files={"file": ("dish.png", b"image-bytes", "image/png")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["analysis"]["kind"] == "image"
    assert "qualityScore" in uploaded.json()["analysis"]
    file_url = uploaded.json()["url"]
    assert client.get(file_url).content == b"image-bytes"
    shutil.rmtree(test_root, ignore_errors=True)


def test_canvas_preflight_reports_missing_clips(monkeypatch, tmp_path):
    test_root = tmp_path / "canvas-draft"
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", test_root)
    client = TestClient(create_app())
    payload = {
        "activePanel": "prompt",
        "nextNodeNumber": 1,
        "nodes": [],
        "edges": [],
        "timeline": [],
        "candidateClips": [],
        "bgmName": "",
        "bgmUrl": "",
    }
    assert client.put("/api/canvas/drafts/default", json=payload).status_code == 200
    response = client.post("/api/canvas/drafts/default/preflight", json={"include_sound": False})
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["errors"][0]["code"] == "NO_CLIPS"


def test_canvas_generation_rejects_missing_kling_key(monkeypatch, tmp_path):
    test_root = tmp_path / "canvas-draft"
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", test_root)
    from web.services import canvas_generation

    monkeypatch.setattr(canvas_generation, "KLING_API_KEY", "")
    monkeypatch.setattr(canvas_generation, "KLING_ACCESS_KEY", "")
    monkeypatch.setattr(canvas_generation, "KLING_SECRET_KEY", "")
    client = TestClient(create_app())
    payload = {
        "activePanel": "prompt",
        "nextNodeNumber": 1,
        "nodes": [{"id": "clips", "type": "workflow", "position": {"x": 0, "y": 0}, "data": {"kind": "generator"}}],
        "edges": [],
        "timeline": [],
        "candidateClips": [],
        "bgmName": "",
        "bgmUrl": "",
    }
    assert client.put("/api/canvas/drafts/default", json=payload).status_code == 200
    response = client.post("/api/canvas/drafts/default/generations", json={"node_id": "clips"})
    assert response.status_code == 400
    assert "Kling" in response.json()["detail"]


def test_canvas_draft_accepts_utf8_bom(monkeypatch, tmp_path):
    test_root = tmp_path / "canvas-draft"
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", test_root)
    client = TestClient(create_app())
    payload = {
        "activePanel": "prompt",
        "nextNodeNumber": 1,
        "nodes": [],
        "edges": [],
        "timeline": [],
        "candidateClips": [],
        "bgmName": "",
        "bgmUrl": "",
    }
    client.put("/api/canvas/drafts/default", json=payload)
    draft_path = test_root / "default" / "draft.json"
    draft_path.write_text(draft_path.read_text(encoding="utf-8"), encoding="utf-8-sig")

    response = client.get("/api/canvas/drafts/default")

    assert response.status_code == 200
    assert response.json()["draft_id"] == "default"


def test_canvas_compose_rejects_unlinked_demo_clips(monkeypatch, tmp_path):
    test_root = tmp_path / "canvas-draft"
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", test_root)
    client = TestClient(create_app())
    payload = {
        "activePanel": "prompt",
        "nextNodeNumber": 1,
        "nodes": [],
        "edges": [],
        "timeline": [{"id": "clip_demo", "dish": "演示菜品", "timelineDuration": 2.5}],
        "bgmName": "",
        "bgmUrl": "",
    }
    assert client.put("/api/canvas/drafts/default", json=payload).status_code == 200
    response = client.post("/api/canvas/drafts/default/compose")
    assert response.status_code == 400
    assert "没有关联" in response.json()["detail"] and "视频文件" in response.json()["detail"]


def test_canvas_clip_library_lists_and_serves_real_mp4(monkeypatch, tmp_path):
    output_root = tmp_path / "output"
    clip_dir = output_root / "canvas_clips"
    clip_dir.mkdir(parents=True)
    clip_path = clip_dir / "天妇罗_roll1_1080p_5s.mp4"
    clip_path.write_bytes(b"fake-mp4")
    monkeypatch.setattr(api_routes, "CANVAS_CLIP_ROOT", clip_dir)
    monkeypatch.setattr(api_routes, "_read_video_duration_seconds", lambda _path: 5.0)

    client = TestClient(create_app())
    clips = client.get("/api/canvas/clips")
    assert clips.status_code == 200
    item = clips.json()[0]
    assert item["dish"] == "天妇罗"
    assert item["timelineDuration"] == 2.5
    assert client.get(item["sourceUrl"]).content == b"fake-mp4"


def test_canvas_clip_thumbnail_is_generated_from_the_library(monkeypatch, tmp_path):
    clip_dir = tmp_path / "canvas_clips"
    clip_dir.mkdir()
    clip_path = clip_dir / "test_01.mp4"
    clip_path.write_bytes(b"fake-mp4")
    thumbnail_path = tmp_path / "test_01_00100.jpg"
    thumbnail_path.write_bytes(b"jpeg-bytes")
    monkeypatch.setattr(api_routes, "CANVAS_CLIP_ROOT", clip_dir)
    monkeypatch.setattr(api_routes, "_clip_thumbnail", lambda path, at: thumbnail_path if path == clip_path and at == 1.0 else None)

    response = TestClient(create_app()).get("/api/canvas/clips/thumbnails/test_01.mp4?at=1")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b"jpeg-bytes"


def test_video_quality_uses_rotation_metadata_for_display_ratio(monkeypatch, tmp_path):
    monkeypatch.setattr(
        canvas_quality,
        "_probe_media",
        lambda _path: {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 3840,
                    "height": 2160,
                    "avg_frame_rate": "30/1",
                    "codec_name": "hevc",
                    "side_data_list": [{"rotation": -90}],
                }
            ],
            "format": {"duration": "4.0"},
        },
    )
    monkeypatch.setattr(
        canvas_quality,
        "_timing_and_freeze_checks",
        lambda _path: {"vfrRatio": 0.0, "maxFreezeSeconds": 0.0, "decodeOk": True},
    )

    analysis = canvas_quality.analyze_video(tmp_path / "rotated.mp4")

    assert analysis["width"] == 2160
    assert analysis["height"] == 3840
    assert analysis["rotation"] == -90
    assert analysis["qualityScore"] == 100
    assert analysis["qualityWarnings"] == []


def test_canvas_compose_accepts_workspace_id(monkeypatch):
    captured = {}

    def fake_start(draft_id, workspace_id=None, include_sound=False):
        captured["draft_id"] = draft_id
        captured["workspace_id"] = workspace_id
        captured["include_sound"] = include_sound
        return {"job_id": "a" * 32, "status": "running", "timeline_count": 2, "output_url": None, "error": None}

    monkeypatch.setattr(api_routes, "start_compose", fake_start)
    response = TestClient(create_app()).post(
        "/api/canvas/drafts/default/compose",
        json={"workspace_id": "compose_2"},
    )
    assert response.status_code == 200
    assert captured == {"draft_id": "default", "workspace_id": "compose_2", "include_sound": False}


def test_canvas_compose_accepts_sound_render_flag(monkeypatch):
    captured = {}

    def fake_start(draft_id, workspace_id=None, include_sound=False):
        captured.update(draft_id=draft_id, workspace_id=workspace_id, include_sound=include_sound)
        return {"job_id": "b" * 32, "status": "running", "timeline_count": 1, "output_url": None, "error": None}

    monkeypatch.setattr(api_routes, "start_compose", fake_start)
    response = TestClient(create_app()).post(
        "/api/canvas/drafts/default/compose",
        json={"include_sound": True},
    )
    assert response.status_code == 200
    assert captured == {"draft_id": "default", "workspace_id": None, "include_sound": True}
