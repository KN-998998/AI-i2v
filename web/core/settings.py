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
WEEKLY_PLAN_DB = PROJECT_ROOT / "output" / "weekly_plans.sqlite3"
WEEKLY_PLAN_TIMEZONE = os.environ.get("WEEKLY_PLAN_TIMEZONE", "Asia/Shanghai")

# OSS 素材抽取任务。真实凭据由 ECS RAM 角色通过 OSS SDK 获取，代码只读取
# Bucket、Endpoint 和任务资源配额等非敏感配置。
OSS_BUCKET = os.environ.get("OSS_BUCKET", "").strip()
OSS_ENDPOINT = os.environ.get("OSS_ENDPOINT", "").strip()
OSS_ASSET_PREFIX = os.environ.get("OSS_ASSET_PREFIX", "").strip().strip("/")
OSS_REGION = os.environ.get("OSS_REGION", "").strip()
OSS_RAM_ROLE_NAME = os.environ.get("OSS_RAM_ROLE_NAME", "EcsOssAssetReadOnly").strip()
OSS_ALLOWED_CATEGORIES = tuple(
    item.strip() for item in os.environ.get("OSS_ALLOWED_CATEGORIES", "").split(",") if item.strip()
)
OSS_JOB_ROOT = Path(os.environ.get("JOB_TEMP_DIR", PROJECT_ROOT / "output" / "oss_jobs"))
OSS_MAX_CONCURRENT_JOBS = max(1, int(os.environ.get("OSS_MAX_CONCURRENT_JOBS", "1")))
OSS_MAX_CATEGORIES = max(1, int(os.environ.get("OSS_MAX_CATEGORIES", "8")))
OSS_MAX_ASSETS_PER_CATEGORY = max(1, int(os.environ.get("OSS_MAX_ASSETS_PER_CATEGORY", "20")))
OSS_MAX_TOTAL_ASSETS = max(1, int(os.environ.get("OSS_MAX_TOTAL_ASSETS", "40")))
OSS_MAX_IMAGE_BYTES = max(1, int(os.environ.get("OSS_MAX_IMAGE_BYTES", str(50 * 1024 * 1024))))
OSS_MAX_REQUESTS_PER_MINUTE = max(1, int(os.environ.get("OSS_MAX_REQUESTS_PER_MINUTE", "30")))
OSS_JOB_RETENTION_HOURS = max(1, int(os.environ.get("OSS_JOB_RETENTION_HOURS", "72")))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

APP_HOST = os.environ.get("APP_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("APP_PORT", "8015"))
APP_RELOAD = os.environ.get("APP_RELOAD", "true").strip().lower() in {"1", "true", "yes", "on"}
MAX_UPLOAD_SIZE = 50 * 1024 * 1024
