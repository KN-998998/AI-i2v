# -*- coding: utf-8 -*-
"""默认曲库：第 6 步没传自己的音乐时，成片用哪首 BGM。

起因（2026-09-21 实测）：种子里写着 `bgmName: "默认 BGM"`、`bgmUrl: ""`，界面三处都显示
「BGM：默认 BGM」，其实背后一个文件都没有；没配人声的成片连音轨都没有，批量生产照搬
样板，批量出的片子也全无声。而 11 条参考片全都有音乐。

现在 assets/bgm/default/ 就是默认曲库（音频文件不进 git，见那边的 README）。每条成片按
合成任务号稳定地挑一首：同一条片子重渲染还是那首，几条片子下来轮着用，不会全撞同一首。

模式判断（bgm_mode）要和前端 model.ts 的 bgmModeFor 同一套规则，否则界面上写的和真渲的
不是一回事。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pipeline.config import DEFAULT_BGM_DIR
from web.services.canvas_state import uploaded_file

# 模块级变量：测试和部署都可能换目录（monkeypatch 这个名字 / 环境变量 DEFAULT_BGM_DIR），
# 所以下面每个函数都现读 DEFAULT_BGM_DIR，不在 import 时把路径算死。
DEFAULT_BGM_DIR = DEFAULT_BGM_DIR

_AUDIO_SUFFIXES = {".mp3", ".m4a", ".wav", ".aac"}
# 老草稿里只有名字没有文件的那个「默认 BGM」，现在真的给它音乐。
_DEFAULT_NAMES = {"默认 BGM", "默认曲库"}


def bgm_mode(sound: dict[str, Any] | None) -> str:
    """default（用默认曲库）/ custom（自己传的）/ none（不要音乐）。"""
    config = sound or {}
    explicit = str(config.get("bgmMode") or "")
    if explicit in {"default", "custom", "none"}:
        return explicit
    if str(config.get("bgmUrl") or "").strip():
        return "custom"
    if str(config.get("bgmName") or "").strip() in _DEFAULT_NAMES:
        return "default"
    return "none"


def list_default_bgm() -> list[dict[str, str]]:
    """曲库里有哪些曲子，按文件名排序。目录不存在就是空曲库，不报错。"""
    directory = Path(DEFAULT_BGM_DIR)
    if not directory.is_dir():
        return []
    files = [
        item for item in directory.iterdir()
        if item.is_file() and not item.name.startswith(".") and item.suffix.lower() in _AUDIO_SUFFIXES
    ]
    return [{"name": item.name, "url": f"/api/canvas/bgm/default/{item.name}"} for item in sorted(files, key=lambda item: item.name)]


def has_default_track(name: str) -> bool:
    """这个名字是不是曲库里真有的一首。只认纯文件名，`../secret.mp3` 这种一律不认。"""
    if not name or Path(name).name != name:
        return False
    return any(item["name"] == name for item in list_default_bgm())


def pick_default_bgm(seed: str, track: str | None = None) -> Path | None:
    """这条成片用哪一首。

    指定了（track 是曲库里的一首）就用它：Patrick 9/22 拍板——指定之后这条成片和用这份
    样板批量生产的每条成片都用同一首。指定的曲子被人从文件夹里拿走了**不报错**，静默改用
    随机那一套，不能因为一首曲子没了就出不了片。

    没指定时按 seed（合成任务的 job_id）挑：同一个 seed 永远同一首，不同 seed 轮着来。
    用 sha1 而不是 random：随机数会让同一条成片每次重渲染换一首音乐，人会以为是工具在乱来。
    """
    if track and has_default_track(track):
        return Path(DEFAULT_BGM_DIR) / track
    names = [item["name"] for item in list_default_bgm()]
    if not names:
        return None
    digest = hashlib.sha1(str(seed).encode("utf-8")).hexdigest()[:8]
    return Path(DEFAULT_BGM_DIR) / names[int(digest, 16) % len(names)]


def resolve_bgm_path(draft_id: str, sound: dict[str, Any] | None, seed: str) -> Path | None:
    """这条成片实际要混哪个音频文件；不要音乐、或者文件不在，都返回 None。"""
    mode = bgm_mode(sound)
    if mode == "none":
        return None
    if mode == "default":
        return pick_default_bgm(seed, str((sound or {}).get("bgmTrack") or ""))
    url = str((sound or {}).get("bgmUrl") or "")
    if not url:
        return None
    return uploaded_file(draft_id, Path(url.split("?", 1)[0]).name)
