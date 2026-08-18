# -*- coding: utf-8 -*-
"""Web application settings."""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"
TEMPLATE_DIR = WEB_ROOT / "templates"
STATIC_DIR = WEB_ROOT / "static"
LOG_DIR = PROJECT_ROOT / "logs"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

APP_HOST = os.environ.get("APP_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("APP_PORT", "5000"))
MAX_UPLOAD_SIZE = 50 * 1024 * 1024