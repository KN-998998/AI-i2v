# -*- coding: utf-8 -*-
"""Image matting and background composition jobs for the visual canvas."""
from __future__ import annotations

import io
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import requests
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from pipeline.config import (
    BACKGROUND_REMOVAL_PROVIDER,
    TENCENT_COS_BUCKET,
    TENCENT_COS_MODEL,
    TENCENTCLOUD_REGION,
    TENCENTCLOUD_SECRET_ID,
    TENCENTCLOUD_SECRET_KEY,
)
from web.services.canvas_quality import analyze_image
from web.services.canvas_state import background_file, draft_directory, generated_file_path, load_draft, uploaded_file

_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_JOB_LOCK = threading.RLock()
_CANVAS_SIZE = (1080, 1920)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _job_path(draft_id: str, job_id: str) -> Path:
    return draft_directory(draft_id) / f"image-process-{job_id}.json"


def _save_job(draft_id: str, job: dict[str, Any]) -> None:
    path = _job_path(draft_id, job["job_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(job, stream, ensure_ascii=False, indent=2)
    temporary.replace(path)


def _update_job(draft_id: str, job: dict[str, Any], **changes: Any) -> None:
    job.update(changes, updated_at=_now())
    with _JOB_LOCK:
        _save_job(draft_id, job)


def get_image_processing_job(draft_id: str, job_id: str) -> dict[str, Any] | None:
    if not _JOB_ID_RE.fullmatch(job_id or ""):
        return None
    path = _job_path(draft_id, job_id)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError):
        return None


def _node_by_id(draft: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    return next((node for node in draft.get("nodes", []) if node.get("id") == node_id), None)


def _upstream_node(draft: dict[str, Any], start_id: str, kind: str, allow_legacy_fallback: bool = True) -> dict[str, Any] | None:
    """Find the closest upstream node of a given kind in an acyclic canvas graph."""
    edges = draft.get("edges", [])
    pending = [start_id]
    seen: set[str] = set()
    while pending:
        target = pending.pop(0)
        if target in seen:
            continue
        seen.add(target)
        sources = [str(edge.get("source")) for edge in edges if edge.get("target") == target]
        for source_id in sources:
            node = _node_by_id(draft, source_id)
            if node and node.get("data", {}).get("kind") == kind:
                return node
            pending.append(source_id)
    if allow_legacy_fallback:
        return next((node for node in draft.get("nodes", []) if node.get("data", {}).get("kind") == kind), None)
    return None


def _draft_image(draft_id: str, url: str | None) -> Path | None:
    if not url:
        return None
    return uploaded_file(draft_id, Path(str(url).split("?", 1)[0]).name)


def tencent_matting_configured() -> bool:
    return bool(
        BACKGROUND_REMOVAL_PROVIDER == "tencent"
        and TENCENTCLOUD_SECRET_ID
        and TENCENTCLOUD_SECRET_KEY
        and TENCENTCLOUD_REGION
        and TENCENT_COS_BUCKET
    )


def _create_cos_client() -> Any:
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError as exc:  # pragma: no cover - exercised by deployment setup
        raise RuntimeError("缺少 cos-python-sdk-v5，请在 PY3_11 环境执行 pip install -r requirements.txt") from exc
    config = CosConfig(
        Region=TENCENTCLOUD_REGION,
        SecretId=TENCENTCLOUD_SECRET_ID,
        SecretKey=TENCENTCLOUD_SECRET_KEY,
        Scheme="https",
    )
    return CosS3Client(config)


def _find_values(payload: Any, keys: set[str]) -> Iterable[str]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in keys and isinstance(value, str) and value:
                yield value
            yield from _find_values(value, keys)
    elif isinstance(payload, list):
        for value in payload:
            yield from _find_values(value, keys)


def _response_image(client: Any, response: Any, bucket: str) -> bytes:
    """Resolve CI SDK response variants to PNG bytes without exposing COS publicly."""
    if isinstance(response, (bytes, bytearray)):
        return bytes(response)
    content = getattr(response, "content", None)
    if isinstance(content, (bytes, bytearray)) and content:
        return bytes(content)

    urls = list(_find_values(response, {"url", "location", "uri"}))
    for value in urls:
        if value.startswith(("https://", "http://")):
            downloaded = requests.get(value, timeout=60)
            downloaded.raise_for_status()
            return downloaded.content

    keys = list(_find_values(response, {"key", "objectkey", "object_key"}))
    for key in keys:
        key = key.lstrip("/")
        if not key.lower().endswith(".png"):
            continue
        result = client.get_object(Bucket=bucket, Key=key)
        body = result.get("Body") if isinstance(result, dict) else None
        if body and hasattr(body, "get_raw_stream"):
            return body.get_raw_stream().read()

    raise RuntimeError("GoodsMatting 未返回可下载的透明 PNG；请确认数据万象接口权限和 SDK 版本")


def _goods_matting(source: Path, destination: Path, draft_id: str) -> None:
    if not tencent_matting_configured():
        raise ValueError("未配置腾讯云抠图。请在 .env 填写 SecretId、SecretKey、Region 和 COS Bucket")
    client = _create_cos_client()
    suffix = source.suffix.lower() if source.suffix else ".jpg"
    object_key = f"canvas-matting/{draft_id}/{uuid.uuid4().hex}{suffix}"
    client.upload_file(Bucket=TENCENT_COS_BUCKET, LocalFilePath=str(source), Key=object_key)
    try:
        response = client.ci_process(
            Bucket=TENCENT_COS_BUCKET,
            Key=object_key,
            CiProcess=TENCENT_COS_MODEL or "GoodsMatting",
        )
    except AttributeError as exc:  # pragma: no cover - protects incompatible SDK releases
        raise RuntimeError("当前 COS SDK 不支持数据万象处理，请升级 cos-python-sdk-v5") from exc
    png_bytes = _response_image(client, response, TENCENT_COS_BUCKET)
    with Image.open(io.BytesIO(png_bytes)) as image:
        image.convert("RGBA").save(destination, "PNG")


def _cover_background(source: Image.Image) -> Image.Image:
    target_w, target_h = _CANVAS_SIZE
    source = ImageOps.exif_transpose(source).convert("RGB")
    scale = max(target_w / source.width, target_h / source.height)
    resized = source.resize((round(source.width * scale), round(source.height * scale)), Image.LANCZOS)
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def _compose_image(foreground_path: Path, background_path: Path | None, destination: Path, config: dict[str, Any]) -> None:
    blur_radius = max(0.0, min(24.0, float(config.get("backgroundBlur", 4) or 0)))
    brightness = max(0.35, min(1.0, float(config.get("backgroundBrightness", 0.72) or 0.72)))
    subject_scale = max(0.2, min(1.0, float(config.get("subjectScale", 0.68) or 0.68)))
    subject_x = max(0.05, min(0.95, float(config.get("subjectX", 0.5) or 0.5)))
    subject_y = max(0.05, min(0.95, float(config.get("subjectY", 0.58) or 0.58)))

    if background_path:
        with Image.open(background_path) as background:
            canvas = _cover_background(background)
    else:
        canvas = Image.new("RGB", _CANVAS_SIZE, "#1B2023")
    if blur_radius:
        canvas = canvas.filter(ImageFilter.GaussianBlur(blur_radius))
    canvas = ImageEnhance.Brightness(canvas).enhance(brightness).convert("RGBA")

    with Image.open(foreground_path) as foreground:
        subject = ImageOps.exif_transpose(foreground).convert("RGBA")
    alpha = subject.getchannel("A")
    bbox = alpha.getbbox()
    if bbox:
        subject = subject.crop(bbox)
    max_dimension = int(min(_CANVAS_SIZE) * subject_scale)
    resize_scale = min(max_dimension / subject.width, int(_CANVAS_SIZE[1] * 0.72) / subject.height)
    resize_scale = max(resize_scale, 0.05)
    subject = subject.resize((max(1, round(subject.width * resize_scale)), max(1, round(subject.height * resize_scale))), Image.LANCZOS)
    x = round(_CANVAS_SIZE[0] * subject_x - subject.width / 2)
    y = round(_CANVAS_SIZE[1] * subject_y - subject.height / 2)

    shadow_alpha = subject.getchannel("A").filter(ImageFilter.GaussianBlur(22)).point(lambda value: value * 0.32)
    shadow = Image.new("RGBA", subject.size, (0, 0, 0, 0))
    shadow.putalpha(shadow_alpha)
    canvas.alpha_composite(shadow, (x + 10, y + 20))
    canvas.alpha_composite(subject, (x, y))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(destination, "JPEG", quality=95, optimize=True)


def start_image_processing(draft_id: str, node_id: str) -> dict[str, Any]:
    draft = load_draft(draft_id)
    if draft is None:
        raise ValueError("画布草稿不存在，请先保存草稿")
    process_node = _node_by_id(draft, node_id)
    if not process_node or process_node.get("data", {}).get("kind") != "image_process":
        raise ValueError("图片处理节点不存在")
    input_node = _upstream_node(draft, node_id, "input", allow_legacy_fallback=False)
    input_data = input_node.get("data", {}) if input_node else {}
    source_image = _draft_image(draft_id, input_data.get("imagePreview"))
    if source_image is None or not source_image.is_file():
        raise ValueError("请将素材与菜品节点连接到当前图片处理节点，并上传菜品图片")

    job_id = uuid.uuid4().hex
    job = {
        "job_id": job_id,
        "draft_id": draft_id,
        "node_id": node_id,
        "status": "queued",
        "stage": "等待处理",
        "created_at": _now(),
        "updated_at": _now(),
        "result_url": None,
        "result_name": None,
        "analysis": None,
        "error": None,
    }
    with _JOB_LOCK:
        _save_job(draft_id, job)

    def worker() -> None:
        try:
            data = process_node.get("data", {})
            _update_job(draft_id, job, status="running", stage="上传图片并调用 GoodsMatting")
            cutout_path = generated_file_path(draft_id, ".png")
            _goods_matting(source_image, cutout_path, draft_id)
            _update_job(draft_id, job, stage="合成背景首帧")
            template_name = str(data.get("backgroundTemplateId") or "")
            template_path = background_file(template_name) if template_name else None
            result_path = generated_file_path(draft_id, ".jpg")
            _compose_image(cutout_path, template_path, result_path, data)
            analysis = analyze_image(result_path, str(input_data.get("dishName") or ""), input_data.get("dishCategory"))
            result_url = f"/api/canvas/drafts/{quote(draft_id, safe='')}/files/{quote(result_path.name, safe='')}"
            _update_job(
                draft_id,
                job,
                status="done",
                stage="图片处理完成",
                result_url=result_url,
                result_name=result_path.name,
                cutout_name=cutout_path.name,
                analysis=analysis,
            )
        except Exception as exc:
            _update_job(draft_id, job, status="error", stage="图片处理失败", error=str(exc))

    threading.Thread(target=worker, name=f"canvas-image-process-{job_id}", daemon=True).start()
    return job
