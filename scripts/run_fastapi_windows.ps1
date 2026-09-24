[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [Parameter(Mandatory = $true)]
    [string]$OutputLog
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
Set-Location -LiteralPath $ProjectRoot

# 计划任务以 SYSTEM 启动，不继承 SSH 会话环境；这里显式固定公网监听地址。
$env:APP_HOST = "0.0.0.0"
$env:APP_PORT = "8015"
$env:APP_RELOAD = "false"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

& $python -X utf8 -m web.run_server *> $OutputLog
if ($LASTEXITCODE -ne 0) {
    throw "FastAPI process exited with code $LASTEXITCODE. See $OutputLog"
}
