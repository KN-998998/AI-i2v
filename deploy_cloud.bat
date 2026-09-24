@echo off
setlocal EnableExtensions

cd /d "%~dp0"
chcp 65001 >nul

if not defined DEPLOY_HOST (
    echo [ERROR] Set DEPLOY_HOST to the Windows ECS public IP or domain first.
    exit /b 1
)
if not defined DEPLOY_PORT set "DEPLOY_PORT=22"
if not defined DEPLOY_USER set "DEPLOY_USER=Administrator"
if not defined DEPLOY_PATH set "DEPLOY_PATH=C:\短视频生产提效"
if not defined DEPLOY_KEY set "DEPLOY_KEY=%USERPROFILE%\.ssh\short-video-windows"

where git >nul 2>nul || (echo [ERROR] Git was not found in PATH. & exit /b 1)
where ssh >nul 2>nul || (echo [ERROR] OpenSSH Client was not found in PATH. & exit /b 1)
if not exist "%DEPLOY_KEY%" (
    echo [ERROR] Deployment SSH key was not found: %DEPLOY_KEY%
    exit /b 1
)

echo [1/2] Pushing committed code to GitHub...
git push origin main || exit /b 1

echo [2/2] Deploying to Windows ECS...
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
    "powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command \"& { Set-Location -LiteralPath '%DEPLOY_PATH%'; & (Join-Path '%DEPLOY_PATH%' 'scripts\\deploy_windows.ps1') -ProjectRoot '%DEPLOY_PATH%' }\""
if errorlevel 1 (
    echo [ERROR] Windows ECS deployment failed.
    exit /b 1
)

echo [OK] Windows ECS deployment completed.
