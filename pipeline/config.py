# -*- coding: utf-8 -*-
"""
全局配置：API Key、路径、视频规格参数
========================================
所有画布领域模块共享此配置。

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
# 画布统一使用的 Kling 视频片段库。
CANVAS_CLIP_ROOT = Path(os.environ.get("CANVAS_CLIP_ROOT", OUTPUT_ROOT / "canvas_clips"))
BACKGROUND_TEMPLATE_DIR = Path(
    os.environ.get("BACKGROUND_TEMPLATE_DIR", OUTPUT_ROOT / "background_templates")
)

# ── API Keys（从 .env / 环境变量读取，代码里不硬编码）──────────────
KLING_API_KEY     = os.environ.get("KLING_API_KEY", "")
KLING_ACCESS_KEY  = os.environ.get("KLING_ACCESS_KEY", "")
KLING_SECRET_KEY  = os.environ.get("KLING_SECRET_KEY", "")
KLING_BASE_URL    = os.environ.get("KLING_BASE_URL", "https://api-beijing.klingai.com")
KLING_MODEL    = os.environ.get("KLING_MODEL", "kling-3.0-omni")

# TTS 配置（待选型，先留占位）
TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "qwen").strip().lower() or "qwen"
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "") or os.environ.get("DASHSCOPE_API_KEY", "")
QWEN_TTS_BASE_URL = os.environ.get("QWEN_TTS_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/audio/speech")
QWEN_TTS_NATIVE_BASE_URL = os.environ.get("QWEN_TTS_NATIVE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation")
QWEN_TTS_MODEL = os.environ.get("QWEN_TTS_MODEL", "qwen3-tts-flash")
QWEN_TTS_MODELS = os.environ.get("QWEN_TTS_MODELS", "")
QWEN_TTS_CLONE_MODEL = os.environ.get("QWEN_TTS_CLONE_MODEL", "qwen3-tts-vc-2026-01-22").strip()
QWEN_TTS_CLONED_VOICES = os.environ.get("QWEN_TTS_CLONED_VOICES", "")
QWEN_LLM_MODEL = os.environ.get("QWEN_LLM_MODEL", "qwen3.7-flash").strip() or "qwen3.7-flash"
QWEN_LLM_BASE_URL = os.environ.get("QWEN_LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").strip().rstrip("/")
QWEN_LLM_ENABLED = os.environ.get("QWEN_LLM_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
TTS_VOICE = os.environ.get("TTS_VOICE", "none")  # 音色标识

# 腾讯云数据万象商品抠图（可选）。密钥只从 .env / 系统环境读取。
BACKGROUND_REMOVAL_PROVIDER = os.environ.get("BACKGROUND_REMOVAL_PROVIDER", "").strip().lower()
TENCENTCLOUD_SECRET_ID = os.environ.get("TENCENTCLOUD_SECRET_ID", "")
TENCENTCLOUD_SECRET_KEY = os.environ.get("TENCENTCLOUD_SECRET_KEY", "")
TENCENTCLOUD_REGION = os.environ.get("TENCENTCLOUD_REGION", "ap-guangzhou")
TENCENT_COS_BUCKET = os.environ.get("TENCENT_COS_BUCKET", "")
TENCENT_COS_MODEL = os.environ.get("TENCENT_COS_MODEL", "GoodsMatting")

# ── 视频规格 ──────────────────────────────────────────────────────
VIDEO_RESOLUTION = "1080p"     # 1080p
VIDEO_ASPECT     = "9:16"      # 竖版
VIDEO_DURATION   = 3           # Kling 3.0 最短 3s（3.0 系列支持 3~15s 整数步进）
VIDEO_SILENT     = True        # 无声生成

# 片尾信息卡：店名 / 地址 / 定位，用 | 分隔，最多三行。
# 11 条已发布的参考片全都有这么一张卡，而工具原来一条都不加。店铺信息是固定的，
# 所以放在 .env 里配一次，之后每条成片自动带上，不用每次让人填。
#   .env 示例：BRAND_END_CARD_LINES=和心居酒屋|旺角登打士街 32 号 2 楼|搜尋「和心」
BRAND_END_CARD_LINES = [item.strip() for item in os.environ.get("BRAND_END_CARD_LINES", "").split("|") if item.strip()][:3]

# 成片规格（项目组 2026-08-20 确认：5-6 道菜 / 成片 12-15s）
FINAL_DURATION_RANGE = (12, 15)   # 成片 12-15s
FINAL_FPS            = 30
FINAL_RESOLUTION     = (1080, 1920)

# 成片的目标响度（EBU R128 Integrated）。11 条已发布的参考片实测全部落在
# −14.0 ~ −14.2 LUFS，也就是 Instagram / YouTube 的标准化目标；而工具合成的成片
# 实测是 −20.4 / −26.2 / −31.1，彼此差了 10.7 dB。统一到这个值，成片之间响度才一致。
FINAL_LOUDNESS_LUFS = -14.0

# 成片音轨的采样率。11 条已发布的参考片全部是 aac / 44100 Hz / 立体声。
# 必须显式收尾：loudnorm 内部按 192 kHz 工作，不加 aresample 的话 ffmpeg 会就近
# 给 aac 挑 96 kHz，同样的码率摊到两倍采样点上，白白折损音质。
FINAL_AUDIO_SAMPLE_RATE = 44100

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
