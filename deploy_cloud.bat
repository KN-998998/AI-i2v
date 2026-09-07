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
set "AHEAD_COUNT="
for /f "delims=" %%C in ('git rev-list --count origin/main..HEAD 2^>nul') do set "AHEAD_COUNT=%%C"
if "%AHEAD_COUNT%"=="" (
    echo [1/2] Remote tracking branch is unavailable. Pushing committed main branch to GitHub...
    git push origin main
    if errorlevel 1 (
        echo [ERROR] Git push failed. Check the network or remote configuration before deploying.
        pause
        exit /b 1
    )
) else if "%AHEAD_COUNT%"=="0" (
    echo [1/2] Local main is already on GitHub. Skipping redundant push.
) else (
    echo [1/2] Pushing %AHEAD_COUNT% committed local change^(s^) to GitHub...
    git push origin main
    if errorlevel 1 (
        echo [ERROR] Git push failed. Check the network or remote configuration before deploying.
        pause
        exit /b 1
    )
)

echo [2/2] Deploying to ECS and waiting for the health check...
ssh -i "%DEPLOY_KEY%" -p %DEPLOY_PORT% ^
    -o IdentitiesOnly=yes ^
    -o BatchMode=yes ^
    -o PreferredAuthentications=publickey ^
    -o PasswordAuthentication=no ^
    -o KbdInteractiveAuthentication=no ^
    -o ConnectTimeout=15 ^
    -o ServerAliveInterval=30 ^
    -o ServerAliveCountMax=20 ^
    -o StrictHostKeyChecking=accept-new ^
    "%DEPLOY_USER%@%DEPLOY_HOST%" ^
    "cd '%DEPLOY_PATH%' && test -f .env && for attempt in 1 2 3; do git -c http.connectTimeout=20 -c http.lowSpeedLimit=1 -c http.lowSpeedTime=300 pull --ff-only origin main && break; test $attempt -eq 3 && exit 1; sleep 10; done && bash scripts/deploy_server.sh"
if errorlevel 1 (
    echo [ERROR] ECS deployment failed. The server output above contains the cause.
    pause
    exit /b 1
)

echo [OK] ECS deployment completed. Refresh the browser to load the new version.
pause
exit /b 0
