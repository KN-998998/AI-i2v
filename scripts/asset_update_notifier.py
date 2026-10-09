from __future__ import annotations

import json
import os
import smtplib
import sys
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path, PurePosixPath
from typing import Callable

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class ScanResult:
    status: str
    new_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssetDigest:
    new_files: tuple[str, ...]
    folder_count: int
    total_bytes: int


def collect_snapshot(root: Path) -> dict[str, dict[str, int]]:
    source = root.expanduser().resolve()
    if not source.is_dir():
        raise ValueError("素材目录不存在或不是文件夹")

    snapshot: dict[str, dict[str, int]] = {}

    def raise_walk_error(error: OSError) -> None:
        raise error

    for current_root, directory_names, file_names in os.walk(
        source, followlinks=False, onerror=raise_walk_error
    ):
        current = Path(current_root)
        directory_names[:] = [
            name for name in directory_names if not (current / name).is_symlink()
        ]
        for file_name in file_names:
            path = current / file_name
            if path.is_symlink() or not path.is_file():
                continue
            metadata = path.stat()
            relative_path = path.relative_to(source).as_posix()
            snapshot[relative_path] = {
                "size": metadata.st_size,
                "mtime_ns": metadata.st_mtime_ns,
            }
    return snapshot


def _read_snapshot(state_path: Path) -> dict[str, dict[str, int]] | None:
    if not state_path.exists():
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("扫描记录无法读取，请检查本机状态文件") from error
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("扫描记录版本无效，请检查本机状态文件")
    if not isinstance(files, dict) or any(
        not isinstance(path, str)
        or not isinstance(metadata, dict)
        or not isinstance(metadata.get("size"), int)
        or not isinstance(metadata.get("mtime_ns"), int)
        for path, metadata in files.items()
    ):
        raise ValueError("扫描记录格式无效，请检查本机状态文件")
    return files


def _write_snapshot(state_path: Path, snapshot: dict[str, dict[str, int]]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = state_path.with_name(f"{state_path.name}.{uuid.uuid4().hex}.tmp")
    payload = {"version": 1, "files": snapshot}
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary_path.replace(state_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def run_scan(
    root: Path,
    state_path: Path,
    send_digest: Callable[[AssetDigest], None],
) -> ScanResult:
    snapshot = collect_snapshot(root)
    previous = _read_snapshot(state_path)
    if previous is None:
        _write_snapshot(state_path, snapshot)
        return ScanResult("baseline")

    new_files = tuple(sorted(snapshot.keys() - previous.keys(), key=str.casefold))
    if new_files:
        if not any(PurePosixPath(path).suffix.casefold() in IMAGE_EXTENSIONS for path in new_files):
            _write_snapshot(state_path, snapshot)
            return ScanResult("no_images", new_files)
        folders = {
            PurePosixPath(relative_path).parent
            for relative_path in new_files
            if PurePosixPath(relative_path).parent != PurePosixPath(".")
        }
        digest = AssetDigest(
            new_files=new_files,
            folder_count=len(folders),
            total_bytes=sum(snapshot[path]["size"] for path in new_files),
        )
        send_digest(digest)
        _write_snapshot(state_path, snapshot)
        return ScanResult("notified", new_files)

    _write_snapshot(state_path, snapshot)
    return ScanResult("unchanged")


def _required_setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"缺少本机环境变量：{name}")
    return value


def _default_state_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home()
    return base / "AssetUpdateNotifier" / "state.json"


def _format_bytes(byte_count: int) -> str:
    amount = float(byte_count)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.2f} {unit}" if unit != "B" else f"{byte_count} B"
        amount /= 1024
    return f"{amount:.2f} TB"


def send_qq_email(digest: AssetDigest) -> None:
    sender = _required_setting("QQ_SMTP_USER")
    auth_code = _required_setting("QQ_SMTP_AUTH_CODE")
    recipient = _required_setting("ASSET_UPDATE_EMAIL_TO")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"公司素材库新增 {len(digest.new_files)} 个文件"
    message.set_content(
        "本次新增素材汇总：\n"
        f"涉及子文件夹：{digest.folder_count} 个\n"
        f"新增文件：{len(digest.new_files)} 个\n"
        f"新增数据量：{_format_bytes(digest.total_bytes)}\n\n"
        "请及时检查并上传到 OSS。新增文件路径：\n"
        + "\n".join(f"- {path}" for path in digest.new_files)
    )

    with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=30) as smtp:
        smtp.login(sender, auth_code)
        smtp.send_message(message)


def main() -> int:
    try:
        root = Path(_required_setting("ASSET_UPDATE_SCAN_ROOT"))
        _required_setting("ASSET_UPDATE_EMAIL_TO")
        _required_setting("QQ_SMTP_USER")
        _required_setting("QQ_SMTP_AUTH_CODE")
        state_path = Path(
            os.environ.get("ASSET_UPDATE_STATE_PATH", "").strip()
            or _default_state_path()
        )
        result = run_scan(root, state_path, send_qq_email)
    except Exception:
        print(
            "扫描提醒失败；请检查本机环境变量、共享目录权限、网络和邮件配置。",
            file=sys.stderr,
        )
        return 1

    if result.status == "baseline":
        print("首次扫描完成：已记录现有素材，本次不发送邮件。")
    elif result.status == "notified":
        print(f"发现 {len(result.new_files)} 个新增素材，提醒邮件已发送。")
    elif result.status == "no_images":
        print("发现新增文件，但不包含支持的图片格式，本次不发送邮件。")
    else:
        print("扫描完成：没有新增素材。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
