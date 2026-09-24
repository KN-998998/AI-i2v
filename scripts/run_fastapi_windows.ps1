[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [Parameter(Mandatory = $true)]
    [string]$OutputLog,
    [string]$ErrorLog
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
Set-Location -LiteralPath $ProjectRoot
if ([string]::IsNullOrWhiteSpace($ErrorLog)) {
    $ErrorLog = $OutputLog -replace '\.out\.log$', '.err.log'
}

# 计划任务以 SYSTEM 启动，不继承 SSH 会话环境；这里显式固定公网监听地址。
$env:APP_HOST = "0.0.0.0"
$env:APP_PORT = "8015"
$env:APP_RELOAD = "false"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

try {
    "$(Get-Date -Format o) Starting FastAPI as $([Security.Principal.WindowsIdentity]::GetCurrent().Name)" |
        Add-Content -LiteralPath $OutputLog -Encoding UTF8
    # Windows PowerShell 5.1 会把原生程序写到 stderr 的普通日志包装成 ErrorRecord；
    # 用独立子进程等待退出，避免 Uvicorn 的 INFO 日志触发 Stop 策略并误杀服务。
    $server = Start-Process -FilePath $python `
        -ArgumentList @("-X", "utf8", "-m", "web.run_server") `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $OutputLog `
        -RedirectStandardError $ErrorLog `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    $exitCode = $server.ExitCode
    "$(Get-Date -Format o) FastAPI exited with code $exitCode" |
        Add-Content -LiteralPath $OutputLog -Encoding UTF8
    if ($exitCode -ne 0) {
        throw "FastAPI process exited with code $exitCode. See $ErrorLog"
    }
} catch {
    "$(Get-Date -Format o) Launcher failed: $($_.Exception.Message)" |
        Add-Content -LiteralPath $ErrorLog -Encoding UTF8
    throw
}
