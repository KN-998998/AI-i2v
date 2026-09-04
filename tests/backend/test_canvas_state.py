import json

from web.services import canvas_state


def test_save_draft_repairs_stale_client_mojibake(tmp_path, monkeypatch):
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    original = "素材与菜品"
    stale_client_value = original.encode("utf-8").decode("latin-1")

    saved = canvas_state.save_draft(
        "default",
        {
            "nodes": [{"id": "assets", "data": {"kind": "input", "title": stale_client_value}}],
            "edges": [],
            "timeline": [],
        },
    )

    assert saved["nodes"][0]["data"]["title"] == original
    payload = json.loads(canvas_state.draft_file("default").read_text(encoding="utf-8"))
    assert payload["nodes"][0]["data"]["title"] == original


def test_save_draft_repairs_mixed_mojibake_without_touching_normal_cjk(tmp_path, monkeypatch):
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")

    saved = canvas_state.save_draft(
        "default",
        {
            "nodes": [{"id": "sound", "data": {"kind": "sound", "voiceName": "女声 Â· Chelsie Â· 活泼清晰"}}],
            "edges": [],
            "timeline": [],
        },
    )

    assert saved["nodes"][0]["data"]["voiceName"] == "女声 · Chelsie · 活泼清晰"


def test_save_draft_repairs_segmented_voice_label_mojibake(tmp_path, monkeypatch):
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    stale_voice_name = "女声 · Chelsie · 活泼清晰".encode("utf-8").decode("latin-1").replace("\u00c2\u00b7", "\u00b7")

    saved = canvas_state.save_draft(
        "default",
        {
            "nodes": [{"id": "sound", "data": {"kind": "sound", "voiceName": stale_voice_name}}],
            "edges": [],
            "timeline": [],
        },
    )

    assert saved["nodes"][0]["data"]["voiceName"] == "女声 · Chelsie · 活泼清晰"
