# AI 图生视频工作流

<p align="center">
  面向餐饮品牌运营团队的图生视频生产工作台：从菜品素材到可发布的竖版短视频。
</p>

<p align="center">
  <a href="#快速开始">快速开始</a> ·
  <a href="#工作流">工作流</a> ·
  <a href="#项目架构">项目架构</a> ·
  <a href="#验证">验证</a> ·
  <a href="#部署">部署</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="Python 3.11" />
  <img src="https://img.shields.io/badge/React-19-149ECA?logo=react&logoColor=white" alt="React 19" />
  <img src="https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/License-Internal-lightgrey" alt="Internal project" />
</p>

> [!IMPORTANT]
> 这是一个内部生产工具。它辅助素材整理、提示词装配与任务编排，但不替代运营人员对菜品素材、品牌文案、模型生成片段和最终成片的审核。

## 为什么需要它？

餐饮图生视频通常跨越素材收集、抠图、镜头提示词、视频生成、剪辑、配音和字幕等多个环节。分散在不同工具中时，素材来源、生成版本和成片方案很容易失控。

本项目把这些环节组织为一份可恢复的画布草稿，并提供面向运营人员的独立操作页：

- 菜品素材、分类、冷热属性和画面主体统一管理
- 图片处理、提示词装配、Kling 任务、片段版本和成片方案可追踪
- 支持多个成片工作区、片段裁剪、BGM、人声与多轨画面文字
- 草稿自动保存；生成、抠图和合成任务支持服务重启后的状态恢复
- 通过顺序解锁避免跳过“上传素材 → 图片处理”等必要前置步骤

## 功能概览

| 模块 | 能力 | 状态 |
| --- | --- | --- |
| 流程画布 | 查看节点关系、连接节点、自动布局、从节点抽屉编辑参数 | 已实现 |
| 素材与菜品 | 上传菜品图、维护分类/冷热/主体类型、批量建稿 | 已实现 |
| 图片处理 | GoodsMatting 抠图、背景模板、9:16 首帧处理 | 需配置云服务 |
| 提示词装配 | L0/L1/L2、镜头、景别、动作及校验 | 已实现 |
| 视频生成 | Kling 图生视频、任务轮询、片段版本管理 | 需配置 Kling |
| 成片合成 | 候选片段、排序、裁剪、多工作区无声合成 | 已实现 |
| 声音与文字 | BGM、Qwen TTS、多轨文字及最终有声合成 | TTS 需配置 |
| 任务与周计划 | 任务中心、周计划生产、人工复核入口 | 已实现 |

## 工作流

```mermaid
flowchart LR
  A[1. 素材与菜品] --> B[2. 图片处理]
  B --> C[3. 提示词装配]
  C --> D[4. 生成视频片段]
  D --> E[5. 成片合成]
  E --> F[6. 声音与文字]
  F --> G[7. 成片结果]
```

每个步骤均由实际产物驱动：例如第 2 步需要处理后的图片，第 4 步需要选定的真实 MP4。第 3 步的“实时装配”也必须在素材上传和图片处理完成后才能执行。未满足前置条件的后续步骤会保持锁定。

流程画布、任务中心和周计划生产是辅助工作台，始终可访问；它们不会绕过上述制作步骤的产物校验。

## 快速开始

### 环境要求

- Windows 10 或更高版本
- Python 3.11（推荐 Conda `PY3_11` 环境）
- Node.js（前端构建使用 `npm.cmd`）
- `ffmpeg` 与 `ffprobe` 已加入 `PATH`

### 1. 安装依赖

```bat
python -m pip install -r requirements.txt
cd frontend
npm.cmd install
cd ..
```

### 2. 配置外部能力（按需）

```bat
copy .env.example .env
```

在 `.env` 中填写实际需要的服务配置。不要提交 `.env`、密钥、素材或生成结果。

| 能力 | 主要配置 |
| --- | --- |
| Kling 图生视频 | `KLING_API_KEY`，或 `KLING_ACCESS_KEY` 与 `KLING_SECRET_KEY` |
| 腾讯云抠图 | `BACKGROUND_REMOVAL_PROVIDER=tencent` 及腾讯云/COS 配置 |
| Qwen TTS / LLM | `TTS_PROVIDER=qwen`、`QWEN_API_KEY` 或 `DASHSCOPE_API_KEY` |
| BGM | 无需密钥，在“声音与文字”页面上传 |

完整字段请以 [.env.example](.env.example) 为准。

### 3. 启动

双击根目录的 `start_dev.bat`，脚本会构建前端并启动 FastAPI。

| 地址 | 用途 |
| --- | --- |
| `http://127.0.0.1:8015/canvas-mvp` | 流程画布 |
| `http://127.0.0.1:8015/workflow/assets` | 第一步：素材与菜品 |
| `http://127.0.0.1:8015/docs` | FastAPI OpenAPI 文档 |

> 修改 `frontend/` 后，请运行 `scripts\build_frontend.bat`，或重新执行 `start_dev.bat`。

## 日常使用

1. 在“素材与菜品”上传菜品首帧，填写菜名、分类、冷热属性和主体类型。
2. 在“图片处理”生成处理后的首帧；手部/厨师素材可保留原图。
3. 在“提示词装配”配置 L0/L1/L2、镜头和动作，校验后实时装配。
4. 在“生成视频片段”创建 Kling 任务，确认当前使用版本。
5. 在“成片合成”选择、排序和裁剪片段，生成无声方案。
6. 在“声音与文字”添加 BGM、TTS 和文字轨道，生成有声成片。
7. 在“成片结果”预览、审核和下载。

### 素材库批量建稿

“素材库批量建稿”会按菜品文件夹扫描素材，生成待确认流程。云端访问时请使用“上传本机文件夹”；只有 ECS 已挂载共享盘时，才填写服务器路径。批量流程仍需要人工确认分类和素材质量。

## 项目架构

```text
frontend/                 React + TypeScript + Vite + React Flow UI
  src/components/         画布、分步页面、编辑抽屉与业务组件
  src/workflowStore.ts    前端草稿状态与任务交互
web/                      FastAPI 应用、API 与服务编排
  api/                    HTTP 路由与请求校验
  services/               草稿、素材、图片处理、生成、合成与质量服务
  core/                   设置与日志
pipeline/                 Kling、GoodsMatting、FFmpeg、TTS、提示词领域能力
tests/                    后端与领域测试
scripts/                  构建、验证与部署入口
docs/                     工程、部署和任务规范
output/                   本地草稿、上传素材、片段与成片（不提交 Git）
```

前端构建产物写入 `web/static/canvas-app/`，由 FastAPI 统一提供。

### 数据与任务恢复

- 浏览器草稿 ID 保存在本地存储；同一浏览器会恢复同一份草稿。
- 草稿、上传文件、任务状态和成片记录保存在 `output/canvas_drafts/<draft_id>/`。
- 真实视频片段保存在 `output/canvas_clips/`，生成版本以“当前使用”状态进入合成候选池。
- 外部生成任务取得 `task_id` 后会持久化，后端重启后可继续轮询。

浏览器草稿隔离不是登录、认证或多租户权限控制；当前版本不提供账号体系和项目级权限隔离。

## 验证

### 全量验证

```bat
scripts\verify.bat
```

### 分项验证

```bat
cd frontend
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
cd ..
pytest
```

`npm.cmd run build` 会同时进行 TypeScript 检查并构建前端。涉及外部 API 的真实生成、抠图或 TTS 成功与否，取决于有效的服务配置和账户权限，不能由本地静态测试替代。

## 部署

生产环境采用 Docker Compose，Nginx 反向代理应用的 `127.0.0.1:8015` 服务。

- 常规发布：推送 `main`，由 GitHub Actions 执行 CI/CD（需要配置仓库 Secrets）
- 人工兜底：运行 `deploy_cloud.bat`
- 详细说明：[CI/CD 部署说明](docs/CI-CD部署说明.md) · [手动部署说明](docs/手动部署说明.md)

部署前请确认 `.env`、`output/` 和 `logs/` 位于服务器本地，不应写入 Git。

## 安全与运行边界

- 当前工具面向内部受控环境；未配置账号认证、权限管理或 HTTPS 时，不应上传敏感、受监管或不适合内部共享的素材。
- 单个上传文件限制为 50 MB。大规模素材库应分批导入，不建议使用一次性请求上传超大目录。
- ECS 上的 `output/` 是运行数据，不是备份策略。生产素材请备份到独立存储后再按保留策略清理。
- 外部服务的额度、并发、模型可用性和生成质量均不由本项目保证。

## 贡献约定

欢迎在内部协作中提交改进。提交前请遵守以下约定：

1. 前端交互改动放在 `frontend/src/`；业务服务放在 `web/services/` 或 `pipeline/`。
2. API 路由只处理 HTTP 职责，耗时任务和文件处理不直接堆放在路由层。
3. 不提交 `.env`、密钥、绝对素材路径、生成媒体、草稿或日志。
4. 为行为变更加上适当的测试，并运行 `scripts\verify.bat`。
5. UI 改动应在 `http://127.0.0.1:8015` 的实际页面验证。

## 相关文档

- [工程结构说明](docs/工程结构说明.md)
- [任务编排与媒体资产规范](docs/任务编排与媒体资产规范.md)
- [运行与排障手册](docs/运行与排障手册.md)
- [CI/CD 部署说明](docs/CI-CD部署说明.md)
- [手动部署说明](docs/手动部署说明.md)

---

如需反馈问题，请在内部协作渠道附上复现步骤、页面路径、浏览器控制台信息（脱敏后）以及相关任务/草稿 ID。
