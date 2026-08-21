@echo off
setlocal EnableExtensions

cd /d "%~dp0"

chcp 65001 >nul

set "PYTHONUTF8="
set "PYTHONIOENCODING=utf-8"
set "LOG_COLOR=true"
set "APP_HOST=127.0.0.1"
set "APP_PORT=8015"
set "APP_RELOAD=true"

echo Checking port %APP_PORT%...
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":%APP_PORT% .*LISTENING"') do (
    echo Stopping old process %%P on port %APP_PORT%...
    taskkill /PID %%P /T /F >nul 2>nul
    if errorlevel 1 (
        echo Failed to stop process %%P. Please run this file as the same user that started the service.
        pause
        exit /b 1
    )
)

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo npm was not found on PATH.
    pause
    exit /b 1
)

echo Building React frontend...
pushd "web\canvas-react"
call npm run build
if errorlevel 1 (
    popd
    echo Frontend build failed. Development server was not started.
    pause
    exit /b 1
)
popd

echo Starting FastAPI on http://%APP_HOST%:%APP_PORT%...
start "Restaurant Video Canvas - FastAPI" /D "%~dp0" cmd /k "chcp 65001 >nul && python -X utf8 -m web.run_server"

echo Waiting for the service to become ready...
set "READY="
for /L %%N in (1,1,30) do (
    curl.exe --silent --show-error --fail --max-time 2 "http://%APP_HOST%:%APP_PORT%/canvas-mvp" >nul 2>nul
    if not errorlevel 1 (
        set "READY=1"
        goto :service_ready
    )
    timeout /t 1 /nobreak >nul
)

echo FastAPI did not become ready within 30 seconds.
echo Check the separate FastAPI window for the startup error.
pause
exit /b 1

:service_ready
echo Service is ready. Opening http://%APP_HOST%:%APP_PORT%/canvas-mvp
start "" "http://%APP_HOST%:%APP_PORT%/canvas-mvp"
exit /b 0
