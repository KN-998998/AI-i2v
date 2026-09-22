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


# ---------------------------------------------------------------------------
# 第十四批：老草稿里没动过的背景亮度 0.72，读出来时自动变成新默认值 0.85
# 第十二批把默认值从 0.72 调到 0.85，但草稿里存着的是旧值，批量生产深拷贝样板节点时也跟着旧。
# 正好等于旧默认值 0.72 的当作没动过；其它数值（比如特意调的 0.95）一律不碰。
# Patrick 9/21 拍板：自动改，只改没动过的。
# ---------------------------------------------------------------------------
def test_loading_a_draft_lifts_the_untouched_legacy_brightness(tmp_path, monkeypatch):
    monkeypatch.setattr(canvas_state, "CANVAS_DRAFT_ROOT", tmp_path / "drafts")
    canvas_state.save_draft("legacy", {
        "nodes": [
            {"id": "p1", "data": {"kind": "image_process", "backgroundBrightness": 0.72}},
            {"id": "p2", "data": {"kind": "image_process", "backgroundBrightness": 0.95}},
            {"id": "p3", "data": {"kind": "image_process"}},
            {"id": "assets", "data": {"kind": "input", "backgroundBrightness": 0.72}},
        ],
        "edges": [], "timeline": [],
    })

    loaded = canvas_state.load_draft("legacy")

    brightness = {node["id"]: node["data"].get("backgroundBrightness") for node in loaded["nodes"]}
    assert brightness["p1"] == 0.85, "没动过的旧默认值要跟上新默认值"
    assert brightness["p2"] == 0.95, "特意调过的不能动"
    assert brightness["p3"] is None, "没有这个字段的不要凭空补一个"
    assert brightness["assets"] == 0.72, "只认图片处理节点"
