# AI 餐饮引流视频工作台

面向餐饮品牌的本地视频生产工作台：将菜品静态图处理为适合图生视频的首帧，生成短视频片段，组合为多条竖版成片，并在时间线上加入 BGM、TTS 人声和同步画面文字。

当前推荐入口是 **React Flow 画布工作台**。旧的 `pipeline/run_batch.py` 仅保留为历史批处理兼容能力，不是日常运营流程。

## 当前生产流程

```text
流程画布总览
    ↓
1. 素材与菜品
   上传菜品原图，可填写菜名、菜品分类，按需上传首帧/尾帧素材
    ↓
2. 图片处理
   腾讯云 GoodsMatting 抠出菜品主体 + 背景模板合成
   生成独立的 9:16 视频首帧，原图始终保留
    ↓
3. 提示词装配
   配置 L0/L1/L2 画面元素、主运动、镜头与固定约束词
   自动进行联动校验并预览最终 Kling 提示词
    ↓
4. 生成视频片段
   每个生成节点独立调用 Kling 图生视频
   完成后自动下载到本地片段库，并按本地规则给出质量提示
    ↓
5. 成片合成
   选择批量成片数量，创建多个合成工作区
   系统可随机或按质量推荐片段；可手动增删、拖拽排序、裁剪片段范围
   每个工作区独立生成无声成片
    ↓
6. 声音与文字
   上传 BGM；在多条人声、文字轨道中调整起止时间和位置
   同步的人声与画面文字共用文案，TTS 实际时长会回写到文字轨道
    ↓
7. 成片结果
   查看每个合成任务状态，播放或下载最终成片
```

## 工作台页面

| 步骤 | 页面 | 路径 | 主要职责 |
| --- | --- | --- | --- |
| 总览 | 流程画布 | `/canvas-mvp` | 节点 CRUD、拖拽、缩放、连线和流程入口 |
| 1 | 素材与菜品 | `/workflow/assets` | 菜品资料、分类、首帧和尾帧图片上传 |
| 2 | 图片处理 | `/workflow/image-processing` | 商品抠图、背景模板、主体位置和合成首帧 |
| 3 | 提示词装配 | `/workflow/prompts` | L0/L1/L2、镜头、动作、提示词校验与预览 |
| 4 | 生成视频片段 | `/workflow/generator` | 生成节点管理、Kling 任务状态、片段库刷新 |
| 5 | 成片合成 | `/workflow/compose` | 批量工作区、片段推荐、排序、裁剪和无声合成 |
| 6 | 声音与文字 | `/workflow/sound` | BGM、人声、文字、多轨时间线和最终有声合成 |
| 7 | 成片结果 | `/workflow/output` | 查看任务结果、预览和下载 |

## 核心能力与边界

- **图生视频**：Kling 3.0 图生视频。当前画布提供 3 秒、5 秒选项；后端支持 3-15 秒整数时长。
- **图片处理**：腾讯云数据万象 `GoodsMatting` 商品抠图。未配置腾讯云密钥时，图片处理步骤会明确提示，不会覆盖原图。
- **片段质量提示**：基于本地规则分析视频分辨率、画幅、时长、帧率与编码，生成质量分数和检查提示；这不是云端训练模型评分。
- **批量合成**：一个草稿可创建多个合成工作区。推荐逻辑优先考虑质量与菜品多样性，甜品或水果最多选一段并排在末尾；运营可以手工覆盖推荐结果。
- **声音与文字同步**：一段人声可绑定一段文字。最终渲染时按 TTS 的实际音频时长同步更新两条轨道。
- **文字轨道**：支持多条文字轨道、重叠、拖动位置、起止时间、字体、字号、颜色、描边、背景框及打字机效果。
- **人工决策仍然保留**：菜品图片、背景模板、提示词动作和最终片段组合由运营确认；系统不替代品牌判断。

## 快速开始

### 1. 安装依赖

Python 使用项目的 Conda `PY3_11` 环境或其他 Python 3.11 环境：

```bat
python -m pip install -r requirements.txt
cd frontend
npm.cmd install
cd ..
```

还需要安装 ffmpeg，并确保 `ffmpeg`、`ffprobe` 可在命令行中调用。

### 2. 配置 `.env`

复制模板并仅在本机填写密钥：

```bat
copy .env.example .env
```

| 能力 | 需要的配置 |
| --- | --- |
| Kling 生成视频 | `KLING_API_KEY` |
| 商品抠图与背景合成 | `BACKGROUND_REMOVAL_PROVIDER=tencent`、腾讯云 SecretId/SecretKey、`TENCENT_COS_BUCKET` |
| Qwen / 阿里云 TTS | `TTS_PROVIDER=qwen`、`QWEN_API_KEY`、音色及模型配置 |
| 素材库或默认 BGM | `IMAGE_LIBRARY`、`BGM_FILE`，可选 |

`.env`、视频、图片、草稿和日志都被 Git 忽略，不能提交到远程仓库。

### 3. 启动工作台

直接双击项目根目录的：

```bat
start_dev.bat
```

脚本会结束旧的 `8015` 服务、构建前端、启动 FastAPI，并自动打开：

```text
http://127.0.0.1:8015/canvas-mvp
```

后端启用 reload。修改 `frontend/` 后重新运行一次 `start_dev.bat`；修改 Python 后端后刷新浏览器即可。FastAPI API 文档位于 `http://127.0.0.1:8015/docs`。

### 4. 全量验证

```bat
scripts\verify.bat
```

该脚本依次执行 TypeScript 类型检查、React 前端模型测试和 Python 测试。

## 数据流与本地目录

```text
output/
├── background_templates/       # 可复用背景模板
├── canvas_clips/               # 画布生成或导入的真实视频片段
│   └── .previews/              # 非浏览器兼容编码的本地代理预览
├── canvas_drafts/
│   └── <draft_id>/
│       ├── draft.json          # 节点、连线、时间线与工作区状态
│       ├── files/              # 上传的菜品图、尾帧、BGM 等
│       └── compositions/       # 每个工作区的无声/最终成片和任务记录
└── _archive/batches/           # 历史 CLI 批次归档，不作为画布片段库
```

- 刷新浏览器后，画布节点、连线、素材引用、合成工作区和轨道配置都会从同一草稿恢复。
- Kling 成功后，视频会自动下载至 `output/canvas_clips/`；前端可刷新片段库获取新片段。
- 每个合成工作区各自创建 ffmpeg 任务，单条失败不会覆盖其他工作区的成片。
- 旧目录 `output/batch_*/03_clips/` 只为历史素材兼容而扫描，新片段不再写入其中。

## 工程结构

```text
frontend/                 # React Flow 前端源码、状态、组件和类型测试
web/                      # FastAPI 应用、API 路由、后台任务和服务层
pipeline/                 # Kling、ffmpeg、TTS 等可复用底层能力；含旧 CLI 兼容入口
tests/
├── backend/              # FastAPI、合成、图片处理测试
└── pipeline/             # 提示词、TTS 等底层能力测试
scripts/
├── build_frontend.bat    # 仅构建前端
└── verify.bat            # 本地全量验证
docs/
└── 工程结构说明.md        # 模块职责和开发约定
```

前端构建结果会写入 `web/static/canvas-app/`，由 FastAPI 提供服务；该目录是可再生文件，不提交 Git。

## 旧 CLI 兼容能力

`pipeline/run_batch.py`、`pipeline/batch_template.yaml` 与 `output/batch_*` 是旧批处理流程的兼容保留：它们用于维护历史批次、复用既有脚本或技术侧排查，不用于日常品牌部操作。新内容请始终从 `/canvas-mvp` 创建和管理。

## 开发约定

详细说明见 [docs/工程结构说明.md](docs/工程结构说明.md)。提交前运行 `scripts\verify.bat`；密钥、素材绝对路径和任何生成媒体不得写入源码或提交 Git。
