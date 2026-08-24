# -*- coding: utf-8 -*-
"""
全局配置：API Key、路径、视频规格参数
========================================
所有 step 脚本共享此配置。

密钥统一从 .env 文件读取（.env 已被 .gitignore 忽略，不会进仓库）：
  .env 格式：
    KLING_API_KEY=xxxx

也可以直接用系统环境变量覆盖（export / set 优先级最高）。
"""
import os
from pathlib import Path


def load_dotenv(env_path=None):
    """零依赖 .env 加载器：把 .env 中的 KEY=VALUE 写入 os.environ（不覆盖已有）。

    支持：
      - 空行 / # 注释行自动跳过
      - 值可带引号（'xxx' 或 "xxx"）
    """
    if env_path is None:
        env_path = Path(__file__).resolve().parent.parent / ".env"
    env_path = Path(env_path)
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip("\"'")
            if k and not os.environ.get(k):   # 不覆盖已存在的非空系统环境变量
                os.environ[k] = v


load_dotenv()

# ── 项目路径 ──────────────────────────────────────────────────────
# 所有路径优先读环境变量（可移植），未设置时用下方通用默认值。
PROJECT_ROOT = Path(__file__).resolve().parent.parent          # 仓库根目录
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
OUTPUT_ROOT  = Path(os.environ.get("OUTPUT_ROOT", PROJECT_ROOT / "output"))
# 新版画布统一使用的 Kling 视频片段库；旧版批处理仍写入 batch_*/03_clips。
CANVAS_CLIP_ROOT = Path(os.environ.get("CANVAS_CLIP_ROOT", OUTPUT_ROOT / "canvas_clips"))

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
BGM_FILE = Path(os.environ.get("BGM_FILE") or "结尾音乐.mp3")

# ── API Keys（从 .env / 环境变量读取，代码里不硬编码）──────────────
KLING_API_KEY     = os.environ.get("KLING_API_KEY", "")
KLING_ACCESS_KEY  = os.environ.get("KLING_ACCESS_KEY", "")
KLING_SECRET_KEY  = os.environ.get("KLING_SECRET_KEY", "")
KLING_BASE_URL    = os.environ.get("KLING_BASE_URL", "https://api-beijing.klingai.com")
KLING_MODEL    = os.environ.get("KLING_MODEL", "kling-3.0-omni")

# TTS 配置（待选型，先留占位）
TTS_PROVIDER = ""
TTS_API_KEY  = os.environ.get("TTS_API_KEY", "")
TTS_VOICE    = os.environ.get("TTS_VOICE", "female_warm")  # 音色标识

# ── 视频规格 ──────────────────────────────────────────────────────
VIDEO_RESOLUTION = "1080p"     # 1080p
VIDEO_ASPECT     = "9:16"      # 竖版
VIDEO_DURATION   = 3           # Kling 3.0 最短 3s（3.0 系列支持 3~15s 整数步进）
VIDEO_SILENT     = True        # 无声生成
ROLL_COUNT       = 3           # 每道菜生成 3 个版本供挑选

# 成片规格（项目组 2026-08-20 确认：5-6 道菜 / 成片 12-15s）
FINAL_DURATION_RANGE = (12, 15)   # 成片 12-15s
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
PROMPT_PREFIX = (
    "\u4fdd\u6301\u539f\u56fe\u4e2d\u7684\u83dc\u54c1\u5f62\u6001\u3001\u6446\u76d8\u3001\u9910\u5177\u548c\u53ef\u89c1\u98df\u6750\u4e0d\u53d8"
)

# 提示词固定约束后缀
PROMPT_SUFFIX = (
    "\u5f00\u573a\u6ca1\u6709\u9759\u6b62\u7b49\u5f85\uff0c\u8fd0\u52a8\u81ea\u7136\u7ed3\u675f\uff0c\u955c\u5934\u4e0d\u6296\u52a8\u3001\u4e0d\u7a81\u53d8"
)

# ── 成片结构模板 ──────────────────────────────────────────────────
# 项目组规则（2026-08-20）：每片 5-6 道菜；甜品有且仅有一个且必须最后展示；
# 成片 12-15s。源片段为 Kling 3s，掐头 0.5s 后每段最多取 2.5s：
#   5 道菜 × 2.5s = 12.5s；6 道菜 × 2.5s = 15.0s（含 outro CTA 叠加）
TEMPLATE_5_DISH = {
    "total_duration": 12.5,
    "segments": [
        {"index": 0, "duration": 2.5, "role": "hook"},      # 钩子：最馋的菜（2.5s）
        {"index": 1, "duration": 2.5, "role": "body"},
        {"index": 2, "duration": 2.5, "role": "body"},
        {"index": 3, "duration": 2.5, "role": "body"},
        {"index": 4, "duration": 2.5, "role": "body"},
        {"index": 5, "duration": 1.0, "role": "outro"},     # 片尾 CTA（叠加在最后一段）
    ],
}

TEMPLATE_6_DISH = {
    "total_duration": 15.0,
    "segments": [
        {"index": 0, "duration": 2.5, "role": "hook"},
        {"index": 1, "duration": 2.5, "role": "body"},
        {"index": 2, "duration": 2.5, "role": "body"},
        {"index": 3, "duration": 2.5, "role": "body"},
        {"index": 4, "duration": 2.5, "role": "body"},
        {"index": 5, "duration": 2.5, "role": "body"},
        {"index": 6, "duration": 1.0, "role": "outro"},
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
