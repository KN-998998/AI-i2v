@echo off
setlocal EnableExtensions

cd /d "%~dp0.."
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if "%~1"=="" (
    echo Python interpreter argument is missing.
    pause
    exit /b 1
)

echo Starting FastAPI with:
echo %~1
echo.
"%~1" -X utf8 -m web.run_server
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo FastAPI process exited with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
