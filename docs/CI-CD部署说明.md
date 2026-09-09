# CI/CD 部署说明

本项目的默认发布路径是：本地验证 → 推送 `main` → GitHub Actions 验证 → SSH 部署到 ECS。日常发布以 CI/CD 为准；不要对同一提交同时运行手动部署脚本，以免重复部署。

## 工作流触发条件

文件：`.github/workflows/ci-cd.yml`

| 触发方式 | 说明 |
| --- | --- |
| `push` 到 `main` | 日常发布入口 |
| `workflow_dispatch` | 在 GitHub Actions 页面手动触发 |

工作流使用并发组 `short-video-production`，同一组部署不会被自动取消。

## 验证与部署流水线

```mermaid
flowchart LR
  A[push main] --> B[Frontend test]
  B --> C[Frontend build]
  C --> D[Python compile]
  D --> E[pytest]
  E --> F[SSH 到 ECS]
  F --> G[git pull --ff-only]
  G --> H[deploy_server.sh]
  H --> I[容器健康检查]
```

### Verify 作业

运行环境为 Ubuntu，超时 20 分钟，执行：

1. Node.js 22 + `npm ci`
2. `frontend/npm test`
3. `frontend/npm run build`
4. Python 3.11 + `pip install -r requirements.txt`
5. `python -m compileall -q web pipeline`
6. `python -m pytest`

### Deploy 作业

仅在 Verify 成功后运行，超时 30 分钟：

1. 从 GitHub Secrets 临时写入 SSH 私钥并校验格式。
2. 使用密钥认证连接目标主机。
3. 在目标目录执行 `git pull --ff-only origin main`，网络失败时最多重试 3 次。
4. 运行 `bash scripts/deploy_server.sh` 构建镜像、重启服务并检查健康接口。

## GitHub Secrets

在仓库 **Settings → Secrets and variables → Actions** 配置以下 Secrets：

| Secret | 说明 |
| --- | --- |
| `DEPLOY_HOST` | ECS 主机地址或域名 |
| `DEPLOY_PORT` | SSH 端口；未设置时默认为 `22` |
| `DEPLOY_USER` | 部署用户 |
| `DEPLOY_PATH` | 服务器上的项目绝对路径 |
| `DEPLOY_SSH_KEY` | Actions 专用私钥完整内容 |

私钥只可存于 GitHub Secret，不可提交到仓库、写入 README 或粘贴到工单。

## 服务器前置条件

- 项目目录已经存在，且远程仓库可由部署用户拉取。
- 已安装 Docker 与 Docker Compose。
- 部署用户具备运行 Docker 的权限。
- 服务端保留自己的 `.env`、`output/` 与 `logs/`；部署不应覆盖这些运行数据。
- Nginx 代理到 `127.0.0.1:8015`，容器健康检查使用 `/api/config`。

建议在首次部署前由服务器管理员确认：

```bash
docker ps
docker compose version
curl --fail http://127.0.0.1:8015/api/config
```

## 日常发布步骤

```bash
scripts\verify.bat
git add <changed-files>
git commit -m "type: concise change summary"
git push origin main
```

随后在仓库 **Actions → CI/CD** 查看同一次提交的 Verify 与 Deploy 状态。只有两者成功后，才认为代码已部署；本地构建成功不能证明 ECS 已成功更新。

## 失败排查

| 现象 | 首先检查 |
| --- | --- |
| Verify 失败 | Actions 日志中的具体测试或构建步骤 |
| SSH 失败 | `DEPLOY_*` Secrets、主机网络、部署用户和公钥授权 |
| `git pull --ff-only` 失败 | 服务器工作树是否被人工修改；不要直接在服务器提交业务代码 |
| 容器未健康 | `docker compose ps`、`docker compose logs --tail=100`、`/api/config` |
| 构建被系统杀死 | 主机内存与磁盘空间；避免在低配环境并发构建多个镜像 |

## 回滚原则

1. 在本地确认要回滚到的已验证提交。
2. 用新提交或经过审查的发布操作使 `main` 指向目标版本。
3. 通过 CI/CD 发布并验证健康检查。

不要在服务器直接修改或提交业务源码来“回滚”；这会破坏 `git pull --ff-only` 和后续可追溯性。

## 相关文档

- [手动部署说明](手动部署说明.md)
- [运行与排障手册](运行与排障手册.md)
