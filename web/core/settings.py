# -*- coding: utf-8 -*-
"""Web application settings."""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"
STATIC_DIR = WEB_ROOT / "static"
LOG_DIR = PROJECT_ROOT / "logs"
CANVAS_DRAFT_ROOT = PROJECT_ROOT / "output" / "canvas_drafts"
CANVAS_BACKGROUND_ROOT = PROJECT_ROOT / "output" / "background_templates"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

APP_HOST = os.environ.get("APP_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("APP_PORT", "8015"))
APP_RELOAD = os.environ.get("APP_RELOAD", "true").strip().lower() in {"1", "true", "yes", "on"}
MAX_UPLOAD_SIZE = 50 * 1024 * 1024
