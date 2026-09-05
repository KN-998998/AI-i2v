# GitHub Actions 验证与部署说明

当前 `.github/workflows/ci-cd.yml` 同时监听 `main` 分支的 `push` 与 `workflow_dispatch`。本地提交后执行 `git push origin main`，工作流会自动运行；也可以在仓库 **Actions -> CI/CD -> Run workflow** 手动触发。

日常发布以 CI/CD 为准：等待验证和部署均成功后再让同事刷新页面。只有在需要检查本机 SSH 链路或自动部署故障后的人工排查时，才使用 [手动部署说明](手动部署说明.md) 中的 `deploy_cloud.bat`；该脚本会再次 `git push` 后直接部署，因此不要与同一提交的运行中工作流并用。

## 工作流行为

工作流按以下顺序执行：

1. 安装前端依赖，运行前端模型测试和构建。
2. 安装 Python 3.11 依赖，运行编译检查和后端/领域测试。
3. 验证成功后，通过 SSH 登录 ECS。
4. ECS 在 `/opt/apps/short-video` 拉取 `main`，运行 `scripts/deploy_server.sh` 构建镜像、重启服务并检查 `/api/config`。

服务器上的 Nginx 继续代理 `127.0.0.1:8015`，对外访问地址不变。

## 服务器一次性准备

以 root 执行：

```bash
usermod -aG docker deploy
```

重新登录 `deploy` 用户后确认：

```bash
docker ps
sudo -n docker ps
```

服务器目录必须是 `/opt/apps/short-video`，并且已有本机 `.env`。`.env`、`output/`、`logs/` 仅保留在 ECS，不由 Git 覆盖。

## GitHub Secrets

在仓库 **Settings -> Secrets and variables -> Actions** 中配置：

| Secret | 值 |
| --- | --- |
| `DEPLOY_HOST` | ECS 地址 |
| `DEPLOY_PORT` | SSH 端口，通常为 `22` |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_PATH` | `/opt/apps/short-video` |
| `DEPLOY_SSH_KEY` | GitHub Actions 专用私钥完整内容 |

私钥只能写入 GitHub Secret，不能提交到项目。

## 排查与回滚

```bash
sudo docker compose ps
sudo docker compose logs --tail=100
curl --fail http://127.0.0.1:8015/api/config
```

回滚应在本地确认目标提交后重新发布，不要在服务器直接提交业务代码。需要服务器级回滚时，先记录当前版本，再切换到明确的提交并重新运行 `scripts/deploy_server.sh`。
