# -*- coding: utf-8 -*-
"""
全局配置：API Key、路径、视频规格参数
========================================
所有 step 脚本共享此配置。

环境变量（推荐）：
  set DEEPSEEK_API_KEY=sk-xxxx
  set KLING_API_KEY=xxxx

或直接编辑下方变量。
"""
import os
from pathlib import Path

# ── 项目路径 ──────────────────────────────────────────────────────
# 所有路径优先读环境变量（可移植），未设置时用下方通用默认值。
PROJECT_ROOT = Path(__file__).resolve().parent.parent          # 仓库根目录
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
OUTPUT_ROOT  = Path(os.environ.get("OUTPUT_ROOT", PROJECT_ROOT / "output"))

# 素材库路径（图生视频主库，按菜名分文件夹）
#   示例：export IMAGE_LIBRARY="D:/素材库/菜品照片"
#   或在本文件同级放一个 config.local.py（已被 .gitignore 忽略），
#   在其中覆盖 IMAGE_LIBRARY / EXTRA_IMAGE_LIBS / BGM_FILE 等变量。
IMAGE_LIBRARY = Path(os.environ.get("IMAGE_LIBRARY", "素材库/菜品照片"))
EXTRA_IMAGE_LIBS = [
    Path(os.environ.get("EXTRA_IMAGE_LIB_1", "")),
    Path(os.environ.get("EXTRA_IMAGE_LIB_2", "")),
]
EXTRA_IMAGE_LIBS = [p for p in EXTRA_IMAGE_LIBS if str(p)]

# 固定 BGM
BGM_FILE = Path(os.environ.get("BGM_FILE", "结尾音乐.mp3"))

# ── API Keys ──────────────────────────────────────────────────────
DEEPSEEK_API_KEY  = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL    = "deepseek-chat"

KLING_API_KEY  = os.environ.get("KLING_API_KEY", "")
KLING_BASE_URL = "https://api.klingai.com"
KLING_MODEL    = "kling-v2.6"          # 可灵 2.6

# TTS 配置（待选型，先留占位）
TTS_PROVIDER = ""        # 待定：cosyvoice / volcengine / doubao
TTS_API_KEY  = os.environ.get("TTS_API_KEY", "")
TTS_VOICE    = "female_warm"  # 音色标识

# ── 视频规格 ──────────────────────────────────────────────────────
VIDEO_RESOLUTION = "1080p"     # 1080p
VIDEO_ASPECT     = "9:16"      # 竖版
VIDEO_DURATION   = 5           # 每段 4-5s
VIDEO_SILENT     = True        # 无声生成
ROLL_COUNT       = 3           # 每道菜生成 3 个版本供挑选

# 成片规格
FINAL_DURATION_RANGE = (10, 12)   # 成片 10-12s
FINAL_FPS            = 30
FINAL_RESOLUTION     = (1080, 1920)

# 图片预处理规格
PREP_TARGET_SHORT = 1080          # 目标短边 1080（1080×1920）
PREP_MAX_LONG     = 2048          # API 允许的最大长边
PREP_JPEG_QUALITY = 95

# ── 固定约束词 ────────────────────────────────────────────────────
# 负向约束（所有提示词统一追加）
NEGATIVE_PROMPT = (
    "不要改变菜品主体，不要让食物变形，不要凭空增加新食材，"
    "不要生成文字，不要生成Logo，不要生成二维码，"
    "不要出现人物手部，不要夸张动画，不要卡通风格，不要低清画质"
)

# 提示词固定约束前缀（AI 生成的动态描述拼接在前）
PROMPT_PREFIX = "真实餐饮广告质感，"

# 提示词固定约束后缀
PROMPT_SUFFIX = (
    "画面稳定，高清，食欲感强，暖色餐厅灯光，浅景深，"
    "不生成文字，不生成Logo，不出现人物"
)

# ── 成片结构模板 ──────────────────────────────────────────────────
# 半固定模板：镜头1 = 招牌菜（3s），其余 = 2s，片尾 1-2s
TEMPLATE_5_DISH = {
    "total_duration": 12,
    "segments": [
        {"index": 0, "duration": 3.0, "role": "hook"},      # 钩子：最馋的菜
        {"index": 1, "duration": 2.0, "role": "body"},
        {"index": 2, "duration": 2.0, "role": "body"},
        {"index": 3, "duration": 2.0, "role": "body"},
        {"index": 4, "duration": 2.0, "role": "body"},
        {"index": 5, "duration": 1.0, "role": "outro"},     # 片尾 CTA
    ],
}

TEMPLATE_3_DISH = {
    "total_duration": 10,
    "segments": [
        {"index": 0, "duration": 3.0, "role": "hook"},
        {"index": 1, "duration": 2.5, "role": "body"},
        {"index": 2, "duration": 2.5, "role": "body"},
        {"index": 3, "duration": 2.0, "role": "outro"},
    ],
}


def get_batch_dir(batch_date: str = None) -> Path:
    """获取当次批量的输出目录。"""
    import datetime
    if batch_date is None:
        batch_date = datetime.date.today().strftime("%Y%m%d")
    d = OUTPUT_ROOT / f"batch_{batch_date}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def batch_subdirs(batch_dir: Path) -> dict:
    """返回批量目录下的标准子目录路径。"""
    dirs = {
        "images":   batch_dir / "01_images",       # 预处理后的 9:16 图片
        "prompts":  batch_dir / "02_prompts",       # 每道菜的提示词 .txt
        "clips":    batch_dir / "03_clips",         # Kling 生成的原始视频片段
        "selected": batch_dir / "04_selected",      # 人工挑选后的最佳片段
        "composed": batch_dir / "05_composed",      # ffmpeg 合成的无声成片
        "final":    batch_dir / "06_final",         # 配音配乐后的最终成片
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs
