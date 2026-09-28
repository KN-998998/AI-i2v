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
$env:PYTHONUNBUFFERED = "1"
$env:LOG_COLOR = "false"

# ECS 与 OSS Bucket 同在深圳，固定走内网 Endpoint；这些值不含凭据，
# 并且进程环境优先于 .env，避免旧的外网地址继续触发 OSS 403。
$env:OSS_BUCKET = "patrick0619"
$env:OSS_ENDPOINT = "https://oss-cn-shenzhen-internal.aliyuncs.com"
$env:OSS_ASSET_PREFIX = [string]::Concat([char]0x56FE, [char]0x7247, [char]0x7D20, [char]0x6750, [char]0x5E93)
$env:OSS_REGION = "cn-shenzhen"
$env:OSS_RAM_ROLE_NAME = "EcsOssAssetReadOnly"

# Windows PowerShell 5.1 会把 Uvicorn 写到 stderr 的普通日志包装成 ErrorRecord。
# 服务运行期间不能使用 Stop，否则第一条 INFO 日志就会终止启动器和整个计划任务。
$ErrorActionPreference = "Continue"
& $python -X utf8 -m web.run_server 1> $OutputLog 2> $ErrorLog
$exitCode = $LASTEXITCODE

"$(Get-Date -Format o) FastAPI exited with code $exitCode" |
    Add-Content -LiteralPath $OutputLog -Encoding Unicode
if ($exitCode -ne 0) {
    "$(Get-Date -Format o) FastAPI failed. See $ErrorLog" |
        Add-Content -LiteralPath $ErrorLog -Encoding Unicode
    exit $exitCode
}
