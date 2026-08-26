@echo off
setlocal EnableExtensions

cd /d "%~dp0.."

where npm.cmd >nul 2>nul
if errorlevel 1 (
    echo npm was not found on PATH. Install Node.js 20 or later.
    exit /b 1
)

if not exist "frontend\package.json" (
    echo Frontend package.json was not found.
    exit /b 1
)

pushd "frontend"
call npm.cmd run build
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
