"""Periodic read-only inventory of the fixed OSS asset library."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from web.core.settings import OSS_INVENTORY_INTERVAL_SECONDS, OSS_INVENTORY_PATH
from web.services.oss_asset_provider import OssAssetProvider

_LOCK = threading.RLock()
_REFRESHING = False
_STOP = threading.Event()
_THREAD: threading.Thread | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _read() -> dict[str, Any] | None:
    if not OSS_INVENTORY_PATH.is_file():
        return None
    try:
        payload = json.loads(OSS_INVENTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write(payload: dict[str, Any]) -> None:
    OSS_INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OSS_INVENTORY_PATH.with_suffix(f".{threading.get_ident()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OSS_INVENTORY_PATH)


def _scanned_at(payload: dict[str, Any] | None) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(payload.get("scanned_at")).replace("Z", "+00:00")) if payload else None
    except (TypeError, ValueError):
        return None
    return value if value and value.tzinfo else value.replace(tzinfo=timezone.utc) if value else None


def is_stale(payload: dict[str, Any] | None) -> bool:
    scanned = _scanned_at(payload)
    return scanned is None or _now() - scanned >= timedelta(seconds=OSS_INVENTORY_INTERVAL_SECONDS)


def _scan() -> dict[str, Any]:
    diagnostics = OssAssetProvider().diagnose_layout()
    scanned_at = _now()
    categories = [
        {
            "category": str(item["category"]),
            "dish_count": int(item.get("dish_folder_count", 0)),
            "image_count": int(item.get("image_count", 0)),
        }
        for item in diagnostics.get("categories", [])
        if isinstance(item, dict) and item.get("category")
    ]
    return {
        "status": "ready",
        "scanned_at": _iso(scanned_at),
        "next_scan_at": _iso(scanned_at + timedelta(seconds=OSS_INVENTORY_INTERVAL_SECONDS)),
        "categories": categories,
        "total_dish_count": sum(item["dish_count"] for item in categories),
        "layout_ready": bool(diagnostics.get("layout_ready")),
        "error": None,
    }


def refresh_inventory(force: bool = False) -> dict[str, Any]:
    """Scan OSS once and persist only safe category counts."""
    global _REFRESHING
    with _LOCK:
        current = _read()
        if not force and not is_stale(current):
            return current or {}
        if _REFRESHING:
            return current or {"status": "scanning", "categories": []}
        _REFRESHING = True
    try:
        payload = _scan()
        with _LOCK:
            _write(payload)
        return payload
    except Exception as exc:
        with _LOCK:
            current = _read() or {"categories": []}
            current.update({"status": "stale" if current.get("scanned_at") else "error", "error": str(exc), "last_attempt_at": _iso(_now())})
            _write(current)
            return current
    finally:
        with _LOCK:
            _REFRESHING = False


def request_refresh_if_stale() -> None:
    with _LOCK:
        current = _read()
        if _REFRESHING or not is_stale(current):
            return
        thread = threading.Thread(target=refresh_inventory, name="oss-inventory-refresh", daemon=True)
        thread.start()


def get_inventory() -> dict[str, Any]:
    with _LOCK:
        payload = _read()
        refreshing = _REFRESHING
    if is_stale(payload):
        request_refresh_if_stale()
        refreshing = True
    if payload is None:
        return {"status": "scanning" if refreshing else "error", "categories": [], "error": None if refreshing else "OSS 库存扫描尚未完成"}
    result = dict(payload)
    if refreshing and result.get("status") == "ready":
        result["status"] = "stale"
    result["refreshing"] = refreshing
    return result


def start_scheduler() -> None:
    global _THREAD
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return
        _STOP.clear()
        _THREAD = threading.Thread(target=_worker, name="oss-inventory-scheduler", daemon=True)
        _THREAD.start()
    request_refresh_if_stale()


def stop_scheduler() -> None:
    _STOP.set()


def _worker() -> None:
    while not _STOP.is_set():
        refresh_inventory()
        _STOP.wait(60)
