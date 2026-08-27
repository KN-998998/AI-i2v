from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from web.app import create_app
from web.services import canvas_image_processing, canvas_state


def _png_bytes(color: tuple[int, int, int, int]) -> bytes:
    image = Image.new("RGBA", (240, 320), color)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def test_background_template_upload_and_list(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_state, "CANVAS_BACKGROUND_ROOT", tmp_path / "backgrounds")
    client = TestClient(create_app())

    uploaded = client.post(
        "/api/canvas/backgrounds",
        files={"file": ("bar.png", _png_bytes((100, 60, 30, 255)), "image/png")},
    )

    assert uploaded.status_code == 200
    item = uploaded.json()
    assert item["name"] == "bar.png"
    assert client.get(item["url"]).status_code == 200
    assert client.get("/api/canvas/backgrounds").json()[0]["id"] == item["id"]


def test_image_processing_requires_a_connected_input_node(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    canvas_state.save_draft(
        "default",
        {
            "nodes": [{"id": "image_process", "data": {"kind": "image_process"}}, {"id": "assets", "data": {"kind": "input"}}],
            "edges": [],
            "timeline": [],
        },
    )

    try:
        canvas_image_processing.start_image_processing("default", "image_process")
    except ValueError as error:
        assert "没有连接" in str(error)
    else:
        raise AssertionError("unlinked image processing node unexpectedly used a fallback input")


def test_image_processing_composites_and_persists_result(monkeypatch, tmp_path):
    draft_root = tmp_path / "drafts"
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", draft_root)

    def fake_goods_matting(source, destination, _draft_id):
        with Image.open(source) as image:
            image.convert("RGBA").save(destination, "PNG")

    monkeypatch.setattr(canvas_image_processing, "_goods_matting", fake_goods_matting)
    draft_directory = draft_root / "default" / "files"
    draft_directory.mkdir(parents=True)
    (draft_directory / "source.png").write_bytes(_png_bytes((240, 120, 80, 255)))

    payload = {
        "activePanel": "prompt",
        "nextNodeNumber": 1,
        "nodes": [
            {"id": "assets", "type": "workflow", "position": {"x": 0, "y": 0}, "data": {"kind": "input", "dishName": "测试菜品", "imagePreview": "/api/canvas/drafts/default/files/source.png"}},
            {"id": "image_process", "type": "workflow", "position": {"x": 100, "y": 0}, "data": {"kind": "image_process", "subjectScale": 0.6, "subjectX": 0.5, "subjectY": 0.58, "backgroundBlur": 4, "backgroundBrightness": 0.7}},
        ],
        "edges": [{"id": "assets-process", "source": "assets", "target": "image_process"}],
        "timeline": [],
        "candidateClips": [],
        "bgmName": "",
        "bgmUrl": "",
    }
    client = TestClient(create_app())
    assert client.put("/api/canvas/drafts/default", json=payload).status_code == 200

    response = client.post("/api/canvas/drafts/default/image-processing", json={"node_id": "image_process"})
    assert response.status_code == 200
    job = response.json()
    for _ in range(40):
        job = client.get(f"/api/canvas/drafts/default/image-processing/{job['job_id']}").json()
        if job["status"] in {"done", "error"}:
            break
        time.sleep(0.05)

    assert job["status"] == "done", job.get("error")
    assert job["result_url"]
    result = client.get(job["result_url"])
    assert result.status_code == 200
    with Image.open(BytesIO(result.content)) as image:
        assert image.size == (1080, 1920)


def test_startup_recovery_finishes_persisted_image_job(monkeypatch, tmp_path):
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    monkeypatch.setattr(canvas_image_processing, "_goods_matting", lambda source, destination, _draft_id: destination.write_bytes(Path(source).read_bytes()))
    source = canvas_state.draft_directory("default") / "files" / "source.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(_png_bytes((40, 120, 200, 255)))
    canvas_state.save_draft(
        "default",
        {
            "nodes": [
                {"id": "assets", "data": {"kind": "input", "imagePreview": "/api/canvas/drafts/default/files/source.png", "dishName": "Recovery dish"}},
                {"id": "image_process", "data": {"kind": "image_process"}},
            ],
            "edges": [{"source": "assets", "target": "image_process"}],
            "timeline": [],
        },
    )
    job = {"job_id": "d" * 32, "node_id": "image_process", "status": "running"}
    canvas_image_processing._save_job("default", job)

    assert canvas_image_processing.recover_image_processing_jobs() == 1
    for _ in range(40):
        current = canvas_image_processing.get_image_processing_job("default", job["job_id"])
        if current and current["status"] in {"done", "error"}:
            break
        time.sleep(0.05)

    assert current["status"] == "done", current.get("error")
    assert canvas_state.load_draft("default")["nodes"][1]["data"]["status"] == "已处理"
