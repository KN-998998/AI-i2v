# -*- coding: utf-8 -*-
"""Kling image-to-video client used by the canvas generation service."""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any

import jwt
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pipeline.config import (
    KLING_ACCESS_KEY,
    KLING_API_KEY,
    KLING_BASE_URL,
    KLING_MODEL,
    KLING_SECRET_KEY,
    VIDEO_ASPECT,
    VIDEO_DURATION,
    VIDEO_RESOLUTION,
    VIDEO_SILENT,
)

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 300
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
OMNI_TASK_PATH = "/omni-video/kling-3.0-omni"


def ensure_credentials() -> None:
    if not ((KLING_ACCESS_KEY and KLING_SECRET_KEY) or KLING_API_KEY):
        raise RuntimeError("未配置 Kling 鉴权信息，请在 .env 填写 KLING_API_KEY 或 KLING_ACCESS_KEY/KLING_SECRET_KEY")


def _is_omni_model() -> bool:
    return "omni" in KLING_MODEL.lower()


def _ok_code(payload: dict[str, Any]) -> bool:
    return payload.get("code") in (0, "0")


def _normalized_status(status: str | None) -> str:
    value = (status or "unknown").lower()
    if value in {"succeed", "success", "succeeded", "completed", "complete"}:
        return "succeeded"
    if value in {"failed", "failure", "fail"}:
        return "failed"
    return value


def _authorization_token() -> str:
    ensure_credentials()
    if KLING_ACCESS_KEY and KLING_SECRET_KEY:
        now = int(time.time())
        return jwt.encode(
            {"iss": KLING_ACCESS_KEY, "exp": now + 1800, "nbf": now - 5},
            KLING_SECRET_KEY,
            algorithm="HS256",
            headers={"alg": "HS256", "typ": "JWT"},
        )
    return KLING_API_KEY


def _headers(json_content: bool = False) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {_authorization_token()}"}
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers


def _parse_response(response: requests.Response, action: str) -> dict[str, Any]:
    try:
        return response.json()
    except ValueError as exc:
        detail = response.text.strip().replace("\n", " ")
        raise RuntimeError(f"{action}失败: HTTP {response.status_code} 非 JSON 响应: {detail[:300]}") from exc


def session_with_retry() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def image_to_base64(image_path: str | Path) -> str:
    path = Path(image_path)
    payload = path.read_bytes()
    if len(payload) > MAX_IMAGE_SIZE_BYTES:
        raise RuntimeError(f"图片过大: {len(payload) / 1024 / 1024:.1f}MB，Kling 限制为 10MB")
    return base64.b64encode(payload).decode("utf-8")


def create_task(
    session: requests.Session,
    image_base64: str,
    prompt: str,
    negative_prompt: str,
    duration: int = VIDEO_DURATION,
    sound: str | None = None,
    image_tail_base64: str | None = None,
) -> str:
    """Create one single-shot Kling image-to-video task and return its task id."""
    if not 3 <= int(duration) <= 15:
        raise ValueError("Kling 生成时长必须在 3-15 秒之间")
    if image_tail_base64 and VIDEO_RESOLUTION != "1080p":
        raise ValueError("Kling 首尾帧任务必须使用 1080p")

    audio = "off" if sound is None and VIDEO_SILENT else (sound or "native")
    contents = [
        {"type": "prompt", "text": prompt},
        {"type": "first_frame", "url": image_base64},
    ]
    if image_tail_base64:
        contents.append({"type": "last_frame", "url": image_tail_base64})

    settings: dict[str, Any] = {
        "audio": "native" if audio != "off" else "off",
        "resolution": VIDEO_RESOLUTION,
        "duration": int(duration),
        "multi_shot": False,
    }
    if _is_omni_model():
        contents[1]["id"] = "image_1"
        if image_tail_base64:
            contents[-1]["id"] = "image_2"
        settings["aspect_ratio"] = VIDEO_ASPECT
        url = f"{KLING_BASE_URL.rstrip('/')}{OMNI_TASK_PATH}"
    else:
        url = f"{KLING_BASE_URL.rstrip('/')}/image-to-video/{KLING_MODEL}"

    response = session.post(
        url,
        headers=_headers(json_content=True),
        json={"contents": contents, "settings": settings, "options": {"watermark_info": {"enabled": False}}},
        timeout=120,
    )
    payload = _parse_response(response, "创建 Kling 任务")
    if response.status_code != 200 or not _ok_code(payload):
        raise RuntimeError(f"创建 Kling 任务失败: {payload.get('message', response.text[:300])}")

    data = payload.get("data") or {}
    task_id = data.get("task_id") or data.get("id")
    if not task_id:
        raise RuntimeError("创建 Kling 任务失败: API 未返回 task_id")
    return str(task_id)


def query_task(session: requests.Session, task_id: str) -> dict[str, Any]:
    response = session.get(
        f"{KLING_BASE_URL.rstrip('/')}/tasks",
        params={"task_ids": task_id},
        headers=_headers(),
        timeout=30,
    )
    payload = _parse_response(response, "查询 Kling 任务")
    if response.status_code != 200 or not _ok_code(payload):
        raise RuntimeError(f"查询 Kling 任务失败: {payload.get('message', response.text[:300])}")
    data = payload.get("data") or {}
    tasks = data if isinstance(data, list) else data.get("tasks") or data.get("result") or []
    return tasks[0] if tasks else {}


def wait_for_video(session: requests.Session, task_id: str) -> tuple[str | None, dict[str, Any]]:
    """Poll one task until it yields a video URL, fails, or times out."""
    started_at = time.monotonic()
    while time.monotonic() - started_at < POLL_TIMEOUT_SECONDS:
        task = query_task(session, task_id)
        status = _normalized_status(task.get("status"))
        if status == "succeeded":
            for output in task.get("outputs") or []:
                if output.get("type") == "video" and output.get("url"):
                    return str(output["url"]), task
            return None, {"error": "Kling 任务完成但未返回视频地址"}
        if status == "failed":
            return None, {"error": task.get("status_detail") or task.get("task_status_msg") or "Kling 任务失败"}
        time.sleep(POLL_INTERVAL_SECONDS)
    return None, {"error": f"Kling 生成超时（>{POLL_TIMEOUT_SECONDS}s）"}


def download_video(session: requests.Session, url: str, output_path: str | Path) -> int:
    """Download a generated video atomically and return the byte count."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.download")
    response = session.get(url, stream=True, timeout=120)
    if response.status_code != 200:
        raise RuntimeError(f"下载 Kling 视频失败: HTTP {response.status_code}")
    try:
        with temporary.open("wb") as stream:
            for chunk in response.iter_content(64 * 1024):
                if chunk:
                    stream.write(chunk)
        if not temporary.stat().st_size:
            raise RuntimeError("下载 Kling 视频失败: 文件为空")
        temporary.replace(target)
        return target.stat().st_size
    finally:
        temporary.unlink(missing_ok=True)
