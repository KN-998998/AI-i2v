import json
from unittest.mock import patch

from pipeline import caption_split


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def test_local_split_preserves_voice_copy_and_targets_short_segments():
    source = "鮨政的招牌料理值得一试，今天到店享受限定优惠。现在就来预约吧！"
    segments = caption_split.split_caption_text_local(source)

    assert "".join(segments) == source
    assert len(segments) >= 3
    assert all(caption_split._cjk_count(segment) <= 10 for segment in segments[:-1])


def test_local_split_does_not_cut_english_or_bracketed_text():
    source = "本周推荐SushiABC（限定套餐），欢迎到店体验。"
    segments = caption_split.split_caption_text_local(source)

    assert "".join(segments) == source
    caption_split.validate_caption_segments(source, segments)
    assert any("SushiABC（限定套餐）" in segment for segment in segments)


def test_qwen_split_is_used_only_when_enabled_and_validated(monkeypatch):
    source = "欢迎来到鮨政，今天有特别推荐。"
    monkeypatch.setattr(caption_split, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(caption_split, "QWEN_LLM_ENABLED", True)
    monkeypatch.setattr(caption_split, "QWEN_LLM_MODEL", "qwen3.7-flash")
    monkeypatch.setattr(caption_split, "QWEN_LLM_BASE_URL", "https://example.invalid/v1")
    content = json.dumps({"voice_segments": ["欢迎来到鮨政，", "今天有特别推荐。"]}, ensure_ascii=False)
    body = json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False).encode()

    with patch.object(caption_split.urllib.request, "urlopen", return_value=_Response(body)) as urlopen:
        result = caption_split.split_caption_text(source, use_llm=True)

    assert result["mode"] == "qwen"
    assert result["used_llm"] is True
    assert result["voice_segments"] == ["欢迎来到鮨政，", "今天有特别推荐。"]
    assert result["segments"] == ["欢迎来到鮨政", "今天有特别推荐"]
    request = urlopen.call_args.args[0]
    assert request.full_url.endswith("/v1/chat/completions")
    assert json.loads(request.data.decode())["model"] == "qwen3.7-flash"


def test_invalid_qwen_result_falls_back_to_local(monkeypatch):
    source = "欢迎来到鮨政，今天有特别推荐。"
    monkeypatch.setattr(caption_split, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(caption_split, "QWEN_LLM_ENABLED", True)
    content = json.dumps({"segments": ["被改写的文案"]}, ensure_ascii=False)
    body = json.dumps({"choices": [{"message": {"content": content}}]}, ensure_ascii=False).encode()

    with patch.object(caption_split.urllib.request, "urlopen", return_value=_Response(body)):
        result = caption_split.split_caption_text(source, use_llm=True)

    assert result["mode"] == "local_fallback"
    assert result["used_llm"] is False
    assert "".join(result["voice_segments"]) == source


def test_unconfigured_qwen_does_not_make_network_request(monkeypatch):
    monkeypatch.setattr(caption_split, "QWEN_API_KEY", "")
    with patch.object(caption_split.urllib.request, "urlopen") as urlopen:
        result = caption_split.split_caption_text("这是一段测试文案。", use_llm=True)

    assert result["mode"] == "local_fallback"
    urlopen.assert_not_called()


def test_caption_display_hides_only_commas_and_sentence_stops():
    result = caption_split.split_caption_text("快传给你的x姓朋友，让ta请你吃omakase。", use_llm=False)

    assert result["voice_segments"] == ["快传给你的x姓朋友，", "让ta请你吃omakase。"]
    assert result["segments"] == ["快传给你的x姓朋友", "让ta请你吃omakase"]


def test_caption_display_preserves_quotes_dashes_and_ellipses():
    source = "“限时”套餐——错过就要等下次……快来！"

    assert caption_split.caption_display_text(source) == source


def test_caption_display_does_not_remove_decimal_or_quoted_punctuation():
    source = "新品3.5折，“Sushi,ABC”限时供应。"

    assert caption_split.caption_display_text(source) == "新品3.5折“Sushi,ABC”限时供应"
