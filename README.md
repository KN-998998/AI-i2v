# AI 引流视频批量生产流水线

餐饮品牌引流短视频自动化生产：**静态菜品图片 → AI 动态视频片段 → 合成成片 → 配音配乐**。

## 项目目标

每天批量产出 **~10 条** 引流短视频，供抖音/小红书等平台投放。
- **生产规模**：10 条/天（混合模式：不同菜品组合 + 同菜变体）
- **视频规格**：1080p / 9:16 竖版 / 12-15s
- **人工介入**：仅在片段审核环节（挑选每道菜最佳版本）

## Pipeline 流程

```
┌─────────────────────────────────────────────────────────┐
│  Step 1: 匹配素材 + 预处理                                │
│  菜品清单 → 素材库按菜名找图 → 9:16 / 1080p 裁切缩放       │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Step 2: 固定槽位装配提示词 + 手动文案                     │
│  L0/L1/L2 选择 → 生成图生视频提示词；运营填写字幕文案       │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Step 3: Kling API 批量图生视频                           │
│  图片 + 提示词 → 可灵 3.0 API → 3s 无声 9:16 视频       │
│  每道菜生成 3 个版本供挑选                                │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Step 4: 人工审核                                        │
│  生成 HTML 审核页 + CSV 清单，运营挑选每道菜最佳片段        │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Step 5: ffmpeg 合成无声成片                              │
│  掐头去尾 → 硬切拼接 → 字幕叠加 → 片尾 CTA → 无声成片       │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Step 6: 手动文案 + 配音 + 固定 BGM                       │
│  手动文案 → Qwen TTS 配音 → 固定 BGM 混音 → 最终成片       │
└─────────────────────────────────────────────────────────┘
```

## 技术栈

| 环节     | 工具                    | 说明                                |
|--------|-----------------------|-----------------------------------|
| 图生视频   | **可灵 Kling 3.0**      | 3s / 1080p / 无声 / 9:16，API Key 鉴权 |
| 提示词生成  | **固定槽位装配器**           | L0/L1/L2 选择后生成确定性提示词              |
| 文案编辑   | **画布节点手动填写**          | 人声文案与画面文字由运营直接编辑                  |
| TTS 配音 | **Qwen TTS**          | 通过 DashScope 兼容接口生成；画布支持“无”或男女音色 |
| BGM    | 固定音频文件                | 后续可升级为 AI 生成                      |
| 视频合成   | **ffmpeg**            | 裁切/拼接/字幕/混音                       |
| 图片处理   | **Pillow**            | 9:16 裁切、尺寸缩放、锐化                   |
| 图床     | **无需**                | Kling API 支持 base64 图片直传          |
| 配置管理   | **PyYAML**            | batch.yaml 驱动全流程                  |
| Web 后端 | **FastAPI + Uvicorn** | 运营工作台 API、文件服务、后台任务编排             |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

ffmpeg 已预装在系统中。

前端构建需要 Node.js 20+（已安装 npm 的电脑可跳过）。Python 依赖和 Node 依赖分开管理：

```bat
python -m pip install -r requirements.txt
cd frontend
npm.cmd install
```

### 2. 配置 API Key

```bash
# 必须：可灵（Step 3 图生视频）
set KLING_API_KEY=你的kling_api_key

# 可选：Qwen TTS（也可写入 .env）
set QWEN_API_KEY=你的qwen_api_key
set QWEN_TTS_MODEL=qwen3-tts-flash
```

### 3. 创建批量配置

复制模板并修改：

```bash
copy pipeline\batch_template.yaml pipeline\batch_20260814.yaml
```

编辑 `batch_20260814.yaml`：

```yaml
batch:
  date: "2026-08-14"

dishes:
  - name: "海胆天妇罗"
    category: "烤物/炸物"
    highlight: "酥脆外皮"
  # ... 添加更多菜品

videos:
  - id: v01
    type: multi_dish
    template: 5_dish
    dishes: [海胆天妇罗, 松叶蟹三吃, ...]
    hook_dish: 海胆天妇罗
  # ... 10条视频编排
```

### 4. 启动 Web 工作台

```bash
python web/app.py
```

开发环境固定使用 `8015` 端口，并默认启用 reload。浏览器打开：`http://127.0.0.1:8015`

推荐使用项目根目录的一键 BAT 开发入口：

```bat
start_dev.bat
```

双击脚本即可自动结束旧的 `8015` 服务、重新构建 React 前端、启动 FastAPI，并打开 `http://127.0.0.1:8015/canvas-mvp`。后端启用 reload；修改前端源码后重新运行一次 `start_dev.bat`，修改后端源码则刷新浏览器即可。停止开发服务请在独立的 FastAPI 窗口使用 `Ctrl+C`。

完整验证（构建、TypeScript 类型检查、前端模型测试、Python 测试）可运行：

```bat
scripts\verify.bat
```

FastAPI 文档：`http://127.0.0.1:8015/docs`

启动窗口使用 UTF-8 编码，并按日志级别显示彩色输出；日志文件保存在 `logs/app.log`，保持无颜色的 UTF-8 文本。

## 当前 Web 工作台

新版 Web 工作台由 React Flow 画布和 FastAPI 服务组成。画布只负责流程总览、节点拖拽、节点连接、节点 CRUD 和进入独立操作页；实际业务操作在各步骤页面完成，数据通过同一个持久化草稿贯通。

| 页面     | 路径                    | 主要功能                         |
|--------|-----------------------|------------------------------|
| 流程画布总览 | `/canvas-mvp`         | 节点拖拽、连接线、节点增删改、流程入口          |
| 素材与菜品  | `/workflow/assets`    | 菜品、首帧/尾帧图片和素材信息              |
| 提示词装配  | `/workflow/prompts`   | L0/L1/L2 槽位、提示词预览和编辑         |
| 生成视频片段 | `/workflow/generator` | 生成或刷新本地真实 MP4 片段             |
| 成片合成   | `/workflow/compose`   | 设置批量成片数量，选择、拖拽排序片段并合成 |
| 声音与文字  | `/workflow/sound`     | 合成后配置 BGM、人声和多段画面文字，并生成最终有声成片 |
| 成片结果   | `/workflow/output`    | 查看合成状态和最终视频                  |

### 持久化与文件流转

- 画布草稿和上传文件保存在 `output/canvas_drafts/<draft_id>/`，前端刷新后可恢复节点、连线、编辑内容和时间线。
- 新版画布下载的真实视频片段统一放在 `output/canvas_clips/`，不需要 `batch_id`；画布刷新会优先读取该目录。
- 为兼容旧项目，画布仍会扫描 `output/batch_*/03_clips/`，旧片段可继续复用，但旧版批处理仍按 `batch_id` 管理自己的目录和清单。
- 已完成的历史批次归档在 `output/_archive/batches/`，归档目录用于保留原始图片、提示词、清单和旧版成片，不作为新版片段库扫描入口。
- 生成视频节点会进入候选片段池；“成片合成”可设置成片数量和每条片段数，随机生成多套工作区，每个工作区可以独立拖拽、删除、补入片段。
- 批量合成会为每个工作区创建独立的 ffmpeg 任务和输出文件，单条失败不会覆盖其他工作区结果。
- 合成任务通过 `/api/canvas/drafts/{draft_id}/compose` 启动，状态和结果通过对应的查询接口获取。
- 初次合成生成无声成片；声音页面可将每条文字的时间段/位置、Qwen TTS 人声和上传 BGM 传入 ffmpeg，生成 `canvas_final.mp4`。
- 样片适配：文字默认支持上方品牌区、中上钩子区、中央和底部安全区；不再限制为一条固定底部字幕。
- `output/`、媒体文件、`.env`、日志和本地开发配置均不会提交到 Git；`.env.example` 只保存配置项名称和示例值。

### 主要画布 API

```text
GET  /api/canvas/drafts/{draft_id}
PUT  /api/canvas/drafts/{draft_id}
POST /api/canvas/drafts/{draft_id}/files
GET  /api/canvas/clips
POST /api/canvas/drafts/{draft_id}/compose
GET  /api/canvas/drafts/{draft_id}/compose/{job_id}
GET  /api/canvas/drafts/{draft_id}/compose/{job_id}/file
```

### 5. 运行流水线（CLI 可选）

```bash
# 方式一：全流程（Step 4 后暂停等人工审核）
python pipeline/run_batch.py --config pipeline/batch_20260814.yaml

# 方式二：分步执行
python pipeline/run_batch.py --config pipeline/batch_20260814.yaml --only 1   # 仅 Step 1
python pipeline/run_batch.py --config pipeline/batch_20260814.yaml --only 2   # 仅 Step 2

# 方式三：从指定步骤开始
python pipeline/run_batch.py --config pipeline/batch_20260814.yaml --start 5   # 审核后继续
```

### 6. 人工审核

Step 4 完成后：
1. 打开 `output/batch_YYYYMMDD/04_selected/review.html` 查看所有视频片段
2. 打开 `output/batch_YYYYMMDD/04_selected/checklist.csv`
3. 在 `selected` 列填 `y` 标记每道菜选用的片段
4. 运行 Step 5-6 继续

## 代码结构

```
pipeline/
├── config.py              # 全局配置（API Key、路径、规格、约束词、成片模板）
├── batch_template.yaml    # 批量配置模板
├── run_batch.py           # 统一入口脚本
├── step1_match_images.py  # 菜品→素材库找图→9:16/1080p 预处理
├── step2_gen_prompts.py   # 固定槽位装配图生视频提示词 + 手动文案
├── step3_gen_videos.py    # Kling API 批量图生视频（JWT 认证 + 轮询）
├── step4_manual_review.py # 生成 HTML 审核页 + CSV 清单
├── step5_compose.py       # ffmpeg 掐头去尾 + 拼接 + 字幕 + CTA
└── step6_voice_bgm.py     # 手动文案 + Qwen TTS 配音 + BGM 混音

web/
├── app.py                 # FastAPI 应用入口
├── run_server.py          # Windows 开发启动入口
├── api/routes.py          # HTTP 路由层（保持 /api 契约）
├── core/settings.py       # Web 配置与项目路径
├── core/logging.py        # 控制台 + 文件轮转日志
├── services/              # 状态、编排、后台任务服务
└── static/canvas-app/      # React 本地构建产物（不提交 Git）

frontend/
├── src/                    # React Flow 前端源码、组件、状态与领域模型
├── package.json            # 前端依赖、构建和模型测试命令
└── vite.config.ts          # 输出到 web/static/canvas-app 的构建配置

tests/
├── backend/                # FastAPI 路由、合成、图片处理测试
└── pipeline/               # 提示词与音频流水线测试

scripts/
├── build_frontend.bat      # 仅构建 React 前端
└── verify.bat              # 全量本地验证入口

docs/
└── 工程结构说明.md          # 模块职责与开发约定
```

## 输出目录结构

```
output/batch_YYYYMMDD/
├── 01_images/       # 预处理后的 9:16 图片
├── 02_prompts/      # 每道菜的提示词(.txt) + 元数据(.json)
├── 03_clips/        # Kling 生成的原始视频片段
├── 04_selected/     # 审核清单（review.html + checklist.csv）
├── 05_composed/     # ffmpeg 合成的无声成片
└── 06_final/        # 最终有声成片

output/canvas_drafts/
└── <draft_id>/       # 画布草稿、上传素材、合成任务和结果

output/canvas_clips/
└── *.mp4              # 新版画布统一片段库；文件名应包含菜名和变体标识
```

## 关键设计决策

| 决策                       | 理由                                  |
|--------------------------|-------------------------------------|
| **提示词 = 固定槽位装配 + 固定约束词** | L0/L1/L2 选择后确定性生成提示词，避免自由文本导致约束漂移   |
| **每菜 3 roll**            | 可灵一次生成多个版本，人工挑选最佳，废片率高时可回退          |
| **先生成无声，后期配音**           | 图生视频模型有声生成成本翻倍，且配音内容可控              |
| **生成 3s，成片只用 ~2s**       | Kling API 固定 3s，AI 动态在开头最自然，掐头去尾取精华 |
| **硬切无转场**                | 保证节奏感，转场在后续需要时再升级                   |
| **Qwen TTS 配音**           | 画布按模型和 voice ID 选择；未配置时可选择“无”       |
| **base64 图片直传**          | Kling API 原生支持，无需图床，简化流程            |

## 固定约束词（不可变）

所有提示词自动追加以下约束，不交给 AI 生成：

- **前缀**：`真实餐饮广告质感，`
- **后缀**：`画面稳定，高清，食欲感强，暖色餐厅灯光，浅景深，不生成文字，不生成Logo，不出现人物`
- **负向约束**：`不要改变菜品主体，不要让食物变形，不要凭空增加新食材，不要生成文字，不要生成Logo，不要生成二维码，不要出现人物手部，不要夸张动画，不要卡通风格，不要低清画质`

## 视频规格

| 参数   | 值                           |
|------|-----------------------------|
| 分辨率  | 1080p                       |
| 比例   | 9:16 竖版                     |
| 每段时长 | 3s（API 固定）→ 2.5s（成片掐头去尾）    |
| 成片时长 | 12-15s（5 道菜≈12.5s，6 道菜≈15s） |
| 帧率   | 30fps                       |
| 音频   | 无声生成 → 后期配音                 |

## 待办事项

- [x] Pipeline 框架搭建
- [x] Step 1-6 代码实现
- [ ] 可灵 API Key 申请（等开会定档位）
- [x] TTS 工具选型确认（Qwen TTS）
- [ ] 首个批次实测 + 调优
- [ ] 提示词效果数据收集 + 固化模板
- [x] 发布到 GitHub 仓库
