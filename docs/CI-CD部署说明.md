# CI/CD 部署说明
本地推送 main 后，GitHub Actions 会先运行前端测试、前端构建、Python 编译检查和后端测试；全部通过后才会通过 SSH 更新 ECS。
服务器上的 Nginx 继续代理 127.0.0.1:8015，访问 URL 不变。
## 服务器一次性准备
使用 root 执行：
usermod -aG docker deploy
退出 SSH 后重新登录，并执行：
su - deploy
docker ps
sudo -n docker ps
如果 sudo -n docker ps 报需要密码，先检查 deploy 用户的 sudo 配置。
服务器项目目录必须为 /opt/apps/short-video，且已经存在 .env。
.env、output 和 logs 只保存在 ECS，不会由 GitHub Actions 覆盖。
## 创建部署密钥
在本机 PowerShell 创建部署专用密钥：
ssh-keygen -t ed25519 -C github-actions-short-video -f "$env:USERPROFILE\.ssh\short-video-github-actions"
Get-Content "$env:USERPROFILE\.ssh\short-video-github-actions.pub"
以 deploy 用户登录 ECS，将公钥整行追加到 ~/.ssh/authorized_keys，然后执行：
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo '这里粘贴公钥整行内容' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
本机验证：
ssh -i "$env:USERPROFILE\.ssh\short-video-github-actions" deploy@47.84.26.217
## GitHub Secrets
在仓库 Settings -> Secrets and variables -> Actions 中创建以下 Repository secrets：
DEPLOY_HOST = 47.84.26.217
DEPLOY_PORT = 22
DEPLOY_USER = deploy
DEPLOY_PATH = /opt/apps/short-video
DEPLOY_SSH_KEY = 部署私钥文件的完整内容
私钥只粘贴到 GitHub Secret，不要提交到项目。读取私钥：
Get-Content "$env:USERPROFILE\.ssh\short-video-github-actions" -Raw
## 日常发布
git add .
git commit -m "描述本次修改"
git push origin main
只有 verify 通过后才会执行部署。正常部署不会删除 ECS 上的 .env、output、logs 或 Nginx 配置。
## 排查
sudo docker compose ps
sudo docker compose logs --tail=100
curl --fail http://127.0.0.1:8015/api/config
## 回滚
git log --oneline -10
git reset --hard 目标提交ID
sudo docker compose build
sudo env APP_UID="$(id -u)" APP_GID="$(id -g)" docker compose up -d
服务器不要直接提交业务代码；修复后在本地提交并推送 main。
CI/CD 部署脚本会以 deploy 用户身份直接执行 docker 命令，因此必须先执行 usermod -aG docker deploy，并退出 SSH 后重新登录。
