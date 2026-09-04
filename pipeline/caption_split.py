"""Deterministic caption splitting with an optional validated Qwen pass."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from pipeline.config import QWEN_API_KEY, QWEN_LLM_BASE_URL, QWEN_LLM_ENABLED, QWEN_LLM_MODEL


class CaptionSplitError(RuntimeError):
    """Raised for an invalid or unusable LLM split response."""


_BRACKETS = {"(": ")", "[": "]", "{": "}", "（": "）", "【": "】", "「": "」", "『": "』"}
_QUOTES = {"\"": "\"", "'": "'", "“": "”", "‘": "’"}
_STRONG_ENDINGS = set("。！？!?；;\n")
_SOFT_ENDINGS = set("，,、：:")
_DISPLAY_HIDDEN_PUNCTUATION = set("，,。")
_ASCII_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@/#:+-]*")


def _consume_protected(text: str, start: int) -> int | None:
    opener = text[start]
    if opener in _QUOTES:
        closer = _QUOTES[opener]
        end = text.find(closer, start + 1)
        return len(text) if end < 0 else end + 1
    closer = _BRACKETS.get(opener)
    if closer is None:
        return None
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opener:
            depth += 1
        elif text[index] == closer:
            depth -= 1
            if depth == 0:
                return index + 1
    return len(text)


def _tokenize(text: str) -> list[str]:
    """Tokenize without creating cuts inside words or protected groups."""
    units: list[str] = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            end = index + 1
            while end < len(text) and text[end].isspace():
                end += 1
            units.append(text[index:end])
            index = end
            continue
        match = _ASCII_WORD.match(text, index)
        if match:
            units.append(match.group(0))
            index = match.end()
            continue
        protected_end = _consume_protected(text, index)
        if protected_end is not None:
            units.append(text[index:protected_end])
            index = protected_end
            continue
        units.append(text[index])
        index += 1
    return units


def _visible_count(text: str) -> int:
    return sum(1 for char in text if not char.isspace() and char not in _STRONG_ENDINGS and char not in _SOFT_ENDINGS)


def _cjk_count(text: str) -> int:
    return sum("\u4e00" <= char <= "\u9fff" for char in text)


def _merge_short_segments(segments: list[str]) -> list[str]:
    if len(segments) < 2:
        return segments
    result: list[str] = []
    for segment in segments:
        if result and _cjk_count(segment) < 4 and _visible_count(result[-1]) + _visible_count(segment) <= 14:
            result[-1] += segment
        else:
            result.append(segment)
    if len(result) > 1 and _cjk_count(result[-1]) < 4:
        result[-2] += result[-1]
        result.pop()
    return result


def caption_display_text(text: str) -> str:
    """Remove punctuation used only as a visual caption split marker.

    Voice copy must remain verbatim so TTS can preserve natural pauses.  On-screen
    restaurant short-video captions usually omit commas and sentence stops, while
    expressive marks such as quotes, dashes, exclamation marks and ellipses remain.
    """
    result: list[str] = []
    units = _tokenize(text)
    for index, unit in enumerate(units):
        if unit in _DISPLAY_HIDDEN_PUNCTUATION:
            continue
        # Tokenization keeps ASCII words, quoted groups, decimals and version
        # numbers intact. A standalone dot is a sentence stop, except when it
        # is part of an ASCII ellipsis.
        if unit == "." and not any(candidate == "." for candidate in units[max(0, index - 2):index] + units[index + 1:index + 3]):
            continue
        result.append(unit)
    return "".join(result).strip()


def split_caption_text_local(text: str) -> list[str]:
    """Return deterministic segments targeting roughly 8-10 Chinese chars."""
    source = text.strip()
    if not source:
        return []
    segments: list[str] = []
    current: list[str] = []
    cjk_length = 0
    for unit in _tokenize(source):
        current.append(unit)
        cjk_length += _cjk_count(unit)
        ending = unit[-1] if unit else ""
        if ending in _STRONG_ENDINGS and cjk_length >= 4:
            segments.append("".join(current))
            current, cjk_length = [], 0
        elif ending in _SOFT_ENDINGS and cjk_length >= 8:
            segments.append("".join(current))
            current, cjk_length = [], 0
        elif cjk_length >= 10:
            segments.append("".join(current))
            current, cjk_length = [], 0
    if current:
        segments.append("".join(current))
    return _merge_short_segments([segment for segment in segments if segment.strip()])


def _safe_cut_positions(source: str) -> set[int]:
    position = 0
    positions = {0}
    for unit in _tokenize(source):
        position += len(unit)
        positions.add(position)
    return positions


def validate_caption_segments(source: str, segments: Any) -> list[str]:
    """Validate exact reconstruction and protected-token boundaries."""
    if not isinstance(segments, list) or not segments or not all(isinstance(item, str) and item for item in segments):
        raise CaptionSplitError("segments must be a non-empty string array")
    if "".join(segments) != source:
        raise CaptionSplitError("segments do not reconstruct the original text")
    safe_positions = _safe_cut_positions(source)
    offset = 0
    for segment in segments[:-1]:
        offset += len(segment)
        if offset not in safe_positions:
            raise CaptionSplitError("a segment cuts through a protected word or group")
    return segments


def _llm_content(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise CaptionSplitError("Qwen returned no choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise CaptionSplitError("Qwen returned no message")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    raise CaptionSplitError("Qwen returned an unsupported content format")


def _parse_llm_segments(content: str, source: str) -> list[str]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise CaptionSplitError("Qwen returned invalid JSON") from exc
    if isinstance(payload, dict):
        return validate_caption_segments(source, payload.get("voice_segments") or payload.get("segments"))
    return validate_caption_segments(source, payload)


def _split_with_qwen(source: str) -> list[str]:
    system_prompt = (
        "You split Chinese promotional copy for short vertical videos. "
        "Return JSON only: {\"voice_segments\":[\"...\"]}. "
        "Keep voice_segments as the original text exactly, in the same order, with no additions or deletions. "
        "Keep each comma or sentence stop at the end of its preceding voice segment. "
        "Target 8-10 Chinese characters per segment, prefer natural punctuation, "
        "and never split English words, numbers, brand names, or bracketed/quoted text."
    )
    payload = json.dumps({
        "model": QWEN_LLM_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": source},
        ],
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{QWEN_LLM_BASE_URL.rstrip('/')}/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CaptionSplitError("Qwen request failed") from exc
    if not isinstance(body, dict):
        raise CaptionSplitError("Qwen returned an invalid response")
    return _parse_llm_segments(_llm_content(body), source)


def split_caption_text(text: str, use_llm: bool = False) -> dict[str, Any]:
    """Split voice copy and derive matching, punctuation-clean display copy."""
    source = text.strip()
    local_voice_segments = split_caption_text_local(source)
    local_segments = [caption_display_text(segment) for segment in local_voice_segments]
    if not use_llm:
        return {"source": source, "segments": local_segments, "voice_segments": local_voice_segments, "mode": "local", "used_llm": False, "warning": None}
    if not QWEN_LLM_ENABLED or not QWEN_API_KEY:
        return {"source": source, "segments": local_segments, "voice_segments": local_voice_segments, "mode": "local_fallback", "used_llm": False, "warning": "Qwen 未配置，已使用本地规则拆分"}
    try:
        voice_segments = _split_with_qwen(source)
    except CaptionSplitError:
        return {"source": source, "segments": local_segments, "voice_segments": local_voice_segments, "mode": "local_fallback", "used_llm": False, "warning": "Qwen 拆分未通过校验，已回退本地规则"}
    return {"source": source, "segments": [caption_display_text(segment) for segment in voice_segments], "voice_segments": voice_segments, "mode": "qwen", "used_llm": True, "warning": None}
