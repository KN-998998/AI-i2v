@echo off
setlocal EnableExtensions

cd /d "%~dp0"
chcp 65001 >nul

set "DEPLOY_HOST=47.84.26.217"
set "DEPLOY_PORT=22"
set "DEPLOY_USER=deploy"
set "DEPLOY_PATH=/opt/apps/short-video"
set "DEPLOY_KEY=%USERPROFILE%\.ssh\short-video-github-actions"

where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git was not found in PATH.
    pause
    exit /b 1
)

where ssh >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Windows OpenSSH Client was not found in PATH.
    pause
    exit /b 1
)

if not exist "%DEPLOY_KEY%" (
    echo [ERROR] Deployment SSH key was not found:
    echo %DEPLOY_KEY%
    pause
    exit /b 1
)

for /f "delims=" %%S in ('git status --porcelain') do (
    echo [WARN] Local uncommitted changes exist. Only committed code will be deployed.
    goto :push
)

:push
echo [1/2] Pushing committed main branch to GitHub...
git push origin main
if errorlevel 1 (
    echo [ERROR] Git push failed. Commit and resolve any Git errors before deploying.
    pause
    exit /b 1
)

echo [2/2] Deploying to ECS and waiting for the health check...
ssh -i "%DEPLOY_KEY%" -p %DEPLOY_PORT% ^
    -o BatchMode=yes ^
    -o ConnectTimeout=15 ^
    -o ServerAliveInterval=30 ^
    -o ServerAliveCountMax=20 ^
    -o StrictHostKeyChecking=accept-new ^
    "%DEPLOY_USER%@%DEPLOY_HOST%" ^
    "cd '%DEPLOY_PATH%' && test -f .env && git pull --ff-only origin main && bash scripts/deploy_server.sh"
if errorlevel 1 (
    echo [ERROR] ECS deployment failed. The server output above contains the cause.
    pause
    exit /b 1
)

echo [OK] ECS deployment completed. Refresh the browser to load the new version.
pause
exit /b 0
