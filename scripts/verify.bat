@echo off
setlocal EnableExtensions

cd /d "%~dp0.."
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHON_EXE="

if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PYTHON_EXE=%CONDA_PREFIX%\python.exe"
if not defined PYTHON_EXE if exist "E:\ANACONDA\envs\PY3_11\python.exe" set "PYTHON_EXE=E:\ANACONDA\envs\PY3_11\python.exe"
if not defined PYTHON_EXE for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P | findstr /I "WindowsApps" >nul
    if errorlevel 1 if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)

if not defined PYTHON_EXE (
    echo A real Python interpreter was not found.
    exit /b 1
)

call scripts\build_frontend.bat
if errorlevel 1 exit /b 1

pushd "frontend"
call npm.cmd run test
if errorlevel 1 (
    popd
    exit /b 1
)
popd

"%PYTHON_EXE%" -X utf8 -m pytest
exit /b %ERRORLEVEL%
