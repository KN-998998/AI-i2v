"""OSS-backed asset discovery and download adapter.

The business layer only sees categories, dish folders and local files.  OSS
authentication stays here so an ECS RAM role can be swapped for another
object-storage provider without changing the video workflow.
"""
from __future__ import annotations

import mimetypes
import posixpath
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen

from web.core.settings import (
    OSS_ALLOWED_CATEGORIES,
    OSS_ASSET_PREFIX,
    OSS_BUCKET,
    OSS_ENDPOINT,
    OSS_MAX_IMAGE_BYTES,
    OSS_RAM_ROLE_NAME,
)

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})
_KEY_PART_RE = re.compile(r"^[^\\/]+$")
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024
_ECS_RAM_ROLE_CREDENTIALS_URL = "http://100.100.100.200/latest/meta-data/ram/security-credentials"


def _ecs_ram_role_auth_host() -> str:
    role_name = OSS_RAM_ROLE_NAME
    if not role_name:
        try:
            with urlopen(f"{_ECS_RAM_ROLE_CREDENTIALS_URL}/", timeout=5) as response:
                role_name = response.read().decode("utf-8").strip().splitlines()[0]
        except (IndexError, OSError, UnicodeError) as exc:
            raise OssProviderError(f"无法从 ECS 元数据服务发现 RAM 角色: {exc}") from exc
    if not role_name or "/" in role_name or "\\" in role_name:
        raise OssProviderError("ECS RAM 角色名无效")
    return f"{_ECS_RAM_ROLE_CREDENTIALS_URL}/{quote(role_name, safe='')}"


class OssProviderError(RuntimeError):
    """A recoverable OSS or asset-library error."""


class OssNotConfiguredError(OssProviderError):
    """Raised when the server has no non-sensitive OSS configuration."""


class InsufficientAssetsError(OssProviderError):
    """Raised before generation when a category has too few usable dishes."""

    def __init__(self, category: str, requested: int, available: int):
        self.category = category
        self.requested = requested
        self.available = available
        super().__init__(f"分类“{category}”可用菜品仅 {available} 个，无法满足 {requested} 个")


def _join_key(*parts: str) -> str:
    values = [str(part or "").replace("\\", "/").strip("/") for part in parts]
    return "/".join(value for value in values if value)


def _safe_file_stem(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", value).strip("._-")
    return cleaned[:80] or "asset"


def _is_image_key(key: str) -> bool:
    return Path(key).suffix.lower() in IMAGE_SUFFIXES


class OssAssetProvider:
    """Read-only OSS provider using ECS RAM role credentials by default."""

    def __init__(self, bucket: Any | None = None):
        self._bucket = bucket

    @property
    def bucket(self) -> Any:
        if self._bucket is None:
            if not OSS_BUCKET or not OSS_ENDPOINT:
                raise OssNotConfiguredError("OSS_BUCKET 和 OSS_ENDPOINT 尚未配置")
            try:
                import oss2
            except ImportError as exc:  # pragma: no cover - deployment-only branch
                raise OssNotConfiguredError("未安装 aliyun-oss-python-sdk，请先安装 requirements.txt") from exc

            try:
                credentials = oss2.credentials.EcsRamRoleCredentialsProvider(_ecs_ram_role_auth_host())
                auth = oss2.ProviderAuth(credentials)
                self._bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET)
            except Exception as exc:  # pragma: no cover - SDK/metadata-service dependent
                raise OssProviderError(f"ECS RAM 角色凭证初始化失败: {exc}") from exc
        return self._bucket

    def _assert_category_allowed(self, category: str) -> str:
        category = str(category or "").strip()
        if not category or not _KEY_PART_RE.fullmatch(category) or category in {".", ".."}:
            raise ValueError("分类名称无效")
        if OSS_ALLOWED_CATEGORIES and category not in OSS_ALLOWED_CATEGORIES:
            raise ValueError(f"分类“{category}”不在允许列表中")
        return category

    def _list_objects(self, prefix: str, *, delimiter: str | None = None) -> list[Any]:
        """List all pages without exposing SDK pagination to callers."""
        result: list[Any] = []
        marker = ""
        while True:
            response = self.bucket.list_objects(
                prefix=prefix,
                delimiter=delimiter,
                marker=marker,
                max_keys=1000,
            )
            if delimiter:
                result.extend(getattr(response, "prefix_list", []) or [])
            else:
                result.extend(getattr(response, "object_list", []) or [])
            if not getattr(response, "is_truncated", False):
                break
            next_marker = str(getattr(response, "next_marker", "") or "")
            if not next_marker or next_marker == marker:
                break
            marker = next_marker
        return result

    def list_categories(self) -> list[str]:
        if OSS_ALLOWED_CATEGORIES:
            return list(OSS_ALLOWED_CATEGORIES)
        root_prefix = _join_key(OSS_ASSET_PREFIX)
        if root_prefix:
            root_prefix += "/"
        prefixes = self._list_objects(root_prefix, delimiter="/")
        return sorted({str(prefix).rstrip("/").split("/")[-1] for prefix in prefixes if str(prefix).strip("/")})

    def diagnose_layout(self) -> dict[str, Any]:
        """Return a safe, non-secret layout summary for deployment preflight."""
        # Force SDK initialization even when OSS_ALLOWED_CATEGORIES is set;
        # otherwise a misconfigured ECS role could look healthy from the UI.
        self.bucket
        categories = self.list_categories()
        summary: list[dict[str, Any]] = []
        for category in categories:
            folders = self.list_dish_folders(category)
            summary.append({
                "category": category,
                "dish_folder_count": len(folders),
                "image_count": sum(len(folder.get("images", [])) for folder in folders),
            })
        return {
            "configured": True,
            "read_only_provider": True,
            "asset_prefix": OSS_ASSET_PREFIX,
            "categories": summary,
            "layout_ready": bool(summary) and all(item["dish_folder_count"] > 0 for item in summary),
        }

    def list_dish_folders(self, category: str) -> list[dict[str, Any]]:
        category = self._assert_category_allowed(category)
        category_prefix = _join_key(OSS_ASSET_PREFIX, category) + "/"
        prefixes = self._list_objects(category_prefix, delimiter="/")
        folders: list[dict[str, Any]] = []
        for raw_prefix in prefixes:
            prefix = str(raw_prefix)
            if not prefix.startswith(category_prefix) or prefix == category_prefix:
                continue
            dish_name = prefix[len(category_prefix):].rstrip("/")
            if not dish_name or "/" in dish_name:
                continue
            images = self.list_images(prefix)
            if images:
                folders.append({"category": category, "dish_name": dish_name, "prefix": prefix, "images": images})
        return folders

    def list_images(self, dish_prefix: str) -> list[dict[str, Any]]:
        images: list[dict[str, Any]] = []
        for item in self._list_objects(str(dish_prefix), delimiter=None):
            key = str(getattr(item, "key", "") or "")
            if not key or not _is_image_key(key):
                continue
            suffix = Path(key).suffix.lower()
            images.append({
                "object_key": key,
                "filename": Path(key).name,
                "suffix": suffix,
                "size": int(getattr(item, "size", 0) or 0),
                "content_type": str(getattr(item, "content_type", "") or mimetypes.guess_type(key)[0] or "application/octet-stream"),
            })
        return images

    def select_unique_assets(self, selections: list[dict[str, Any]], rng: Any) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        for selection in selections:
            category = self._assert_category_allowed(str(selection["category"]))
            count = int(selection["count"])
            folders = self.list_dish_folders(category)
            if len(folders) < count:
                raise InsufficientAssetsError(category, count, len(folders))
            for folder in rng.sample(folders, count):
                image = rng.choice(folder["images"])
                selected.append({
                    "asset_id": f"asset_{len(selected) + 1:03d}",
                    "category": category,
                    "dish_name": folder["dish_name"],
                    "dish_prefix": folder["prefix"],
                    **image,
                    "status": "selected",
                })
        return selected

    def download_asset(self, asset: dict[str, Any], destination: Path) -> None:
        """Download one object with a bounded streaming write."""
        object_key = str(asset.get("object_key") or "")
        if not object_key or not _is_image_key(object_key):
            raise ValueError("OSS 对象不是支持的图片格式")
        declared_size = int(asset.get("size") or 0)
        if declared_size > OSS_MAX_IMAGE_BYTES:
            raise ValueError(f"图片超过 {OSS_MAX_IMAGE_BYTES // (1024 * 1024)} MB 限制")

        response = self.bucket.get_object(object_key)
        total = 0
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("wb") as stream:
                while True:
                    chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > OSS_MAX_IMAGE_BYTES:
                        raise ValueError(f"图片超过 {OSS_MAX_IMAGE_BYTES // (1024 * 1024)} MB 限制")
                    stream.write(chunk)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        if total == 0:
            raise ValueError("OSS 图片为空")
        asset["downloaded_size"] = total
        asset["content_type"] = str(getattr(response, "headers", {}).get("Content-Type") or asset.get("content_type") or "")


def asset_filename(asset: dict[str, Any], index: int, suffix: str | None = None) -> str:
    extension = suffix or str(asset.get("suffix") or Path(str(asset.get("filename") or "")).suffix or ".jpg")
    extension = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
    return f"{index:03d}_{_safe_file_stem(str(asset.get('dish_name') or 'asset'))}{extension}"
