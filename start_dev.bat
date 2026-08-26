@echo off
setlocal EnableExtensions

cd /d "%~dp0"

chcp 65001 >nul

set "PYTHONUTF8=1"
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

set "PYTHON_EXE="
if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PYTHON_EXE=%CONDA_PREFIX%\python.exe"

if not defined PYTHON_EXE for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P | findstr /I "WindowsApps" >nul
    if errorlevel 1 if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)

if not defined PYTHON_EXE for %%P in (
    "%~dp0.venv\Scripts\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "E:\ANACONDA\envs\PY3_11\python.exe"
    "E:\ANACONDA\python.exe"
) do if exist "%%~P" if not defined PYTHON_EXE set "PYTHON_EXE=%%~P"

if not defined PYTHON_EXE (
    echo A real Python interpreter was not found.
    echo WindowsApps\python.exe is only a Microsoft Store alias.
    echo Please install Python or set PYTHON_EXE in this file.
    pause
    exit /b 1
)

echo Using Python: %PYTHON_EXE%
"%PYTHON_EXE%" -X utf8 -c "import fastapi, uvicorn, colorama" >nul 2>nul
if errorlevel 1 (
    echo Python dependencies are missing in: %PYTHON_EXE%
    echo Run: "%PYTHON_EXE%" -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo Building React frontend...
call scripts\build_frontend.bat
if errorlevel 1 (
    echo Frontend build failed. Development server was not started.
    pause
    exit /b 1
)

echo Starting FastAPI on http://%APP_HOST%:%APP_PORT%...
start "Restaurant Video Canvas - FastAPI" /D "%~dp0" cmd /k call "%~dp0web\run_backend.bat" "%PYTHON_EXE%"

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
