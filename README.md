# AI-i2v · 餐饮图生视频批量生产流水线

利用 AI 图生视频模型（可灵 Kling / 阿里百炼 wan2.6 等），把**菜品静态照片**批量生成**动态视频片段**，再自动**合成剪辑**为完整的竖版引流视频（9:16, 1080p）。

```
菜品照片 → 找图匹配 → AI 写提示词 → API 生成片段 → 人工审核 → ffmpeg 合成 → 配音配乐 → 成片
```

## 项目结构

```
pipeline/                 # 主流水线（批量生产）
  config.py               # 全局配置（路径/API Key/视频规格，支持环境变量）
  batch_template.yaml     # 批量配置模板（菜品清单 + 视频编排）
  run_batch.py            # 批处理入口（按参数运行不同阶段）
  step1_match_images.py   # 菜品清单 → 匹配素材图片 → 预处理 9:16/1080p
  step2_gen_prompts.py    # 菜名 → DeepSeek 生成图生视频提示词 + 字幕文案
  step3_gen_videos.py     # 调图生视频 API（可灵/Kling）批量生成片段
  step4_manual_review.py  # 人工审核挑选最佳片段
  step5_compose.py        # ffmpeg 按编排模板合成无声成片
  step6_voice_bgm.py      # AI 文案 + TTS 配音 + BGM 混音 → 最终成片
scripts/                  # 独立工具脚本
  01_prep.py              # 备料：选图 + 压缩裁切 + 生成批次清单
  prep_images.py          # 图片预处理（大图 → API 可接受尺寸 + 9:16 裁切）
  check_image_sizes.py    # 检查素材库图片尺寸分布
  wan26_flash_api.py      # 阿里百炼 wan2.6-i2v-flash 图生视频 API 调用
```

## 快速开始

### 1. 配置

所有 API Key 走**环境变量**（不硬编码在代码里）：

```bash
# Windows (cmd)
set DEEPSEEK_API_KEY=sk-xxxx      # DeepSeek（提示词生成）
set KLING_API_KEY=xxxx            # 可灵（图生视频）
set KLING_API_SECRET=xxxx
set DASHSCOPE_API_KEY=sk-xxxx     # 阿里百炼（wan2.6，可选）

# macOS / Linux
export DEEPSEEK_API_KEY=sk-xxxx
export KLING_API_KEY=xxxx
export KLING_API_SECRET=xxxx
export DASHSCOPE_API_KEY=sk-xxxx
```

素材库路径（可选，默认相对路径）：

```bash
export IMAGE_LIBRARY="D:/素材库/菜品照片"    # 图生视频主库，按菜名分文件夹
export BGM_FILE="D:/音乐/结尾音乐.mp3"        # 固定 BGM
```

> 也可以在 `pipeline/` 下放一个 `config.local.py`（已被 .gitignore 忽略）覆盖路径变量。

### 2. 准备批量配置

复制 `pipeline/batch_template.yaml`，填入当天菜品清单：

```bash
cp pipeline/batch_template.yaml batch_20260814.yaml
# 编辑：dishes（菜名/类型/亮点）、videos（编排）、brand（品牌信息）
```

### 3. 运行

```bash
# 只跑某一步（推荐先用单步调试）
python pipeline/step1_match_images.py --config batch_20260814.yaml
python pipeline/step2_gen_prompts.py  --config batch_20260814.yaml
python pipeline/step3_gen_videos.py   --config batch_20260814.yaml
python pipeline/step4_manual_review.py --config batch_20260814.yaml
python pipeline/step5_compose.py      --config batch_20260814.yaml
python pipeline/step6_voice_bgm.py    --config batch_20260814.yaml

# 或一键跑完整流程
python pipeline/run_batch.py --config batch_20260814.yaml --stage all
```

## 视频规格

| 项 | 值 |
|---|---|
| 分辨率 | 1080p（9:16 竖版）|
| 单段时长 | 4-5s（每道菜生成 3 个版本供挑选）|
| 成片时长 | 10-12s（钩子 3s + 每道菜 2s + 片尾 CTA 1-2s）|
| 提示词 | DeepSeek 按菜名/类型/亮点自动生成，统一负向约束 |

## 环境依赖

- Python 3.10+
- `pip install pillow opencv-python requests pyyaml`
- ffmpeg（合成阶段必需）

## 免责声明

- 本仓库仅包含代码与模板，**不含任何品牌素材、图片、视频、字体或业务数据**，请自行准备素材。
- 使用即代表你已获得所用素材的合法使用授权。
