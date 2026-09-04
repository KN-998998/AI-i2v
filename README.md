# AI 餐饮引流视频工作台

面向餐饮品牌的本地视频生产工作台。它将菜品静态图处理为图生视频首帧，生成短视频片段，再组合为多条竖版成片，并在时间线上加入 BGM、TTS 人声和同步画面文字。

工作台同时提供流程画布总览和七个独立操作页面。画布用于搭建、连接和管理流程节点；独立页面用于集中完成每一步的业务编辑。

## 生产流程

```text
素材与菜品
  -> 图片处理
  -> 提示词装配
  -> 生成视频片段
  -> 成片合成
  -> 声音与文字
  -> 成片结果
```

| 步骤 | 页面 | 路径 | 主要职责 |
| --- | --- | --- | --- |
| 总览 | 流程画布 | `/canvas-mvp` | 节点 CRUD、拖拽、缩放、连线和各步骤入口 |
| 1 | 素材与菜品 | `/workflow/assets` | 上传菜品图，维护菜名、分类、冷热属性和主体类型 |
| 2 | 图片处理 | `/workflow/image-processing` | GoodsMatting 抠图、背景模板、主体位置和 9:16 首帧合成 |
| 3 | 提示词装配 | `/workflow/prompts` | 每个节点独立编辑 L0/L1/L2、镜头、景别和动作，并预览提示词 |
| 4 | 生成视频片段 | `/workflow/generator` | 创建 Kling 任务、查看状态、恢复未完成任务和管理片段版本 |
| 5 | 成片合成 | `/workflow/compose` | 选择、排序、裁剪片段，创建多个无声成片工作区 |
| 6 | 声音与文字 | `/workflow/sound` | BGM、人声、文字、多轨时间线和最终有声合成 |
| 7 | 成片结果 | `/workflow/output` | 查看、预览和下载最终成片 |

## 核心规则

- 生成片段统一保存到 `output/canvas_clips/`；草稿和任务状态保存到 `output/canvas_drafts/<draft_id>/`。
- 每个素材节点可对应多个生成版本。确认一个版本后，合成页面默认使用该版本；运营仍可切换或重新生成。
- Kling 任务在拿到 `task_id` 后会落盘。后端重启时会重新轮询状态为 `queued` 或 `running` 的任务，并在完成后自动下载到片段库。
- 片段质量分数来自本地规则（画幅、时长、帧率、分辨率和编码），仅用于排序提示，不是训练模型评分。
- 批量合成支持多个工作区。推荐会考虑质量和菜品多样性，甜品或水果最多保留一段并置于末尾；运营可手动覆盖。
- 人声与画面文字共用文案来源。TTS 生成后会按实际音频时长同步更新对应文字和人声轨道；旧草稿文本会在读取时兼容修复。
- 文字轨道支持多轨、重叠、时间范围、拖拽位置、字体、字号、颜色、描边、背景框和打字机效果。
- 菜品图、背景模板、提示词动作和最终片段组合仍需运营确认，系统不替代品牌判断。

## 快速开始

### 1. 安装依赖

使用项目的 Conda `PY3_11` 环境或其他 Python 3.11 环境：

```bat
python -m pip install -r requirements.txt
cd frontend
npm.cmd install
cd ..
```

还需要安装 `ffmpeg` 和 `ffprobe`，并确保它们可在命令行中调用。

### 2. 配置 `.env`

```bat
copy .env.example .env
```

| 能力 | 配置 |
| --- | --- |
| Kling 图生视频 | `KLING_API_KEY`，或 `KLING_ACCESS_KEY` 与 `KLING_SECRET_KEY` |
| 商品抠图 | `BACKGROUND_REMOVAL_PROVIDER=tencent`、腾讯云 SecretId/SecretKey、`TENCENT_COS_BUCKET` |
| 阿里云 Qwen TTS | `QWEN_API_KEY` 或 `DASHSCOPE_API_KEY`、TTS 模型和音色配置 |
| BGM | 在“声音与文字”页面直接上传音频文件 |

`.env`、素材、视频、草稿、日志和构建产物均被 Git 忽略，不能提交到远程仓库。

### 3. 启动工作台

双击根目录的：

```bat
start_dev.bat
```

脚本会结束旧的 `8015` 服务，构建前端，启动 FastAPI 并自动打开：

```text
http://127.0.0.1:8015/canvas-mvp
```

后端启用 reload。修改 Python 后端后刷新浏览器即可；修改 `frontend/` 后重新运行一次 `start_dev.bat`。API 文档位于 `http://127.0.0.1:8015/docs`。

### 4. 全量验证

```bat
scripts\verify.bat
```

该脚本构建前端，并执行前端模型测试和 Python 测试。

## 本地数据目录

```text
output/
├── background_templates/       # 可复用背景模板
├── canvas_clips/               # 生成或导入的视频片段
│   └── .previews/              # 浏览器兼容的本地代理预览
└── canvas_drafts/
    └── <draft_id>/
        ├── draft.json          # 节点、连线、时间线和工作区状态
        ├── files/              # 上传的菜品图、尾帧、BGM 等
        ├── generate-*.json     # 可恢复的 Kling 任务状态
        └── compositions/       # 无声/最终成片和任务记录
```

刷新浏览器后，节点、连线、素材引用、合成工作区和轨道配置会从草稿恢复。单个合成工作区失败不会覆盖其他工作区的成片。

## 工程结构

```text
frontend/                 # React、TypeScript、React Flow 前端源码和模型测试
web/                      # FastAPI 应用、API 路由、后台任务和服务层
pipeline/                 # Kling、ffmpeg、TTS、提示词等可复用领域适配器
tests/                    # 后端和领域模块测试
scripts/                  # 构建、验证、服务器部署脚本
docs/                     # 工程和部署说明
```

前端构建结果写入 `web/static/canvas-app/`，由 FastAPI 提供服务；该目录可再生，不提交 Git。详细约定见 [docs/工程结构说明.md](docs/工程结构说明.md)。

## 发布

当前正式发布入口是 `deploy_cloud.bat`：它推送已提交的 `main`，然后通过 SSH 在 ECS 拉取、构建并健康检查。GitHub Actions 工作流仅支持在仓库 Actions 页面手动触发，作为远程验证和部署的可选入口。详见 [docs/手动部署说明.md](docs/手动部署说明.md) 与 [docs/CI-CD部署说明.md](docs/CI-CD部署说明.md)。
