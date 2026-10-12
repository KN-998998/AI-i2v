from pathlib import Path

import pytest

from scripts import asset_update_notifier
from scripts.asset_update_notifier import AssetDigest, run_scan


def test_first_scan_only_creates_baseline(tmp_path: Path):
    root = tmp_path / "share"
    root.mkdir()
    (root / "existing.jpg").write_bytes(b"existing")
    sent: list[AssetDigest] = []

    result = run_scan(root, tmp_path / "state.json", sent.append)

    assert result.status == "baseline"
    assert sent == []


def test_notifies_only_new_files_and_updates_snapshot(tmp_path: Path):
    root = tmp_path / "share"
    root.mkdir()
    existing_file = root / "existing.jpg"
    existing_file.write_bytes(b"old")
    state_path = tmp_path / "state.json"
    run_scan(root, state_path, lambda _: None)

    existing_file.write_bytes(b"modified")
    added_file = root / "new folder" / "added.png"
    added_file.parent.mkdir()
    added_file.write_bytes(b"new")
    second_file = root / "another folder" / "second.jpg"
    second_file.parent.mkdir()
    second_file.write_bytes(b"12345")
    sent: list[AssetDigest] = []

    result = run_scan(root, state_path, sent.append)
    repeated_result = run_scan(root, state_path, sent.append)

    assert result.status == "notified"
    assert result.new_files == ("another folder/second.jpg", "new folder/added.png")
    assert sent == [
        AssetDigest(
            new_files=("another folder/second.jpg", "new folder/added.png"),
            folder_count=2,
            total_bytes=8,
        )
    ]
    assert repeated_result.status == "unchanged"


def test_failed_notification_does_not_mark_files_as_seen(tmp_path: Path):
    root = tmp_path / "share"
    root.mkdir()
    state_path = tmp_path / "state.json"
    run_scan(root, state_path, lambda _: None)
    (root / "added.jpg").write_bytes(b"new")

    def fail(_: AssetDigest) -> None:
        raise RuntimeError("SMTP unavailable")

    with pytest.raises(RuntimeError, match="SMTP unavailable"):
        run_scan(root, state_path, fail)

    sent: list[AssetDigest] = []
    result = run_scan(root, state_path, sent.append)

    assert result.status == "notified"
    assert sent == [AssetDigest(new_files=("added.jpg",), folder_count=0, total_bytes=3)]


def test_non_image_additions_do_not_notify_until_an_image_is_added(tmp_path: Path):
    root = tmp_path / "share"
    root.mkdir()
    state_path = tmp_path / "state.json"
    run_scan(root, state_path, lambda _: None)
    sent: list[AssetDigest] = []

    (root / "update" / "notes.txt").parent.mkdir()
    (root / "update" / "notes.txt").write_text("notes", encoding="utf-8")
    no_image_result = run_scan(root, state_path, sent.append)

    image_path = root / "update" / "dish.PNG"
    image_path.write_bytes(b"image")
    image_result = run_scan(root, state_path, sent.append)

    assert no_image_result.status == "no_images"
    assert image_result.status == "notified"
    assert sent == [AssetDigest(new_files=("update/dish.PNG",), folder_count=1, total_bytes=5)]


def test_qq_email_uses_ssl_and_includes_new_paths(monkeypatch: pytest.MonkeyPatch):
    sent_messages = []

    class FakeSMTP:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def login(self, username: str, auth_code: str) -> None:
            assert username == "sender@qq.com"
            assert auth_code == "test-auth-code"

        def send_message(self, message) -> None:
            sent_messages.append(message)

    monkeypatch.setenv("QQ_SMTP_USER", "sender@qq.com")
    monkeypatch.setenv("QQ_SMTP_AUTH_CODE", "test-auth-code")
    monkeypatch.setenv("ASSET_UPDATE_EMAIL_TO", "recipient@example.com")
    monkeypatch.setattr(
        asset_update_notifier.smtplib,
        "SMTP_SSL",
        lambda host, port, timeout: FakeSMTP()
        if (host, port, timeout) == ("smtp.qq.com", 465, 30)
        else pytest.fail("unexpected SMTP endpoint"),
    )

    asset_update_notifier.send_qq_email(
        AssetDigest(new_files=("素材/新图片.jpg",), folder_count=1, total_bytes=2048)
    )

    assert sent_messages[0]["To"] == "recipient@example.com"
    assert "1 个文件" in sent_messages[0]["Subject"]
    assert "素材/新图片.jpg" in sent_messages[0].get_content()
    assert "涉及子文件夹：1 个" in sent_messages[0].get_content()
    assert "新增数据量：2.00 KB" in sent_messages[0].get_content()
