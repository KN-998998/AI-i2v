[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
)

$ErrorActionPreference = "Stop"
trap {
    $location = $_.InvocationInfo.PositionMessage
    Write-Host "Deployment failed at: $location"
    throw
}
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    throw "ProjectRoot was empty. Pass the ECS checkout path with -ProjectRoot."
}
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $FilePath $($ArgumentList -join ' ')"
    }
}

$logsRoot = Join-Path $ProjectRoot "logs"
$outputRoot = Join-Path $ProjectRoot "output"
if ([string]::IsNullOrWhiteSpace($logsRoot) -or [string]::IsNullOrWhiteSpace($outputRoot)) {
    throw "Deployment paths could not be derived from ProjectRoot '$ProjectRoot'."
}
New-Item -ItemType Directory -Force -Path $logsRoot, $outputRoot | Out-Null

$git = (Get-Command git.exe -ErrorAction Stop).Source
$gitPullCompleted = $false
for ($attempt = 1; $attempt -le 3; $attempt++) {
    try {
        # ECS 上可能保留一次仅用于现场修复的本地提交；合并远程 main，避免部署因分叉而中断。
        Invoke-Checked $git @("-c", "http.connectTimeout=20", "-c", "http.lowSpeedLimit=1", "-c", "http.lowSpeedTime=300", "pull", "--no-rebase", "--no-edit", "origin", "main")
        $gitPullCompleted = $true
        break
    } catch {
        if ($attempt -eq 3) {
            throw
        }
        Start-Sleep -Seconds (5 * $attempt)
    }
}

if (-not $gitPullCompleted) {
    throw "Git pull did not complete."
}

$pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
$pythonOnPath = Get-Command python.exe -ErrorAction SilentlyContinue
$venvRoot = Join-Path $ProjectRoot ".venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    if ($null -ne $pythonLauncher) {
        Invoke-Checked $pythonLauncher.Source @("-3.11", "-m", "venv", $venvRoot)
    } elseif ($null -ne $pythonOnPath) {
        Invoke-Checked $pythonOnPath.Source @("-m", "venv", $venvRoot)
    } else {
        throw "Python 3.11 was not found. Install it and enable Add Python to PATH."
    }
}

Invoke-Checked $venvPython @("-X", "utf8", "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt")

$npm = (Get-Command npm.cmd -ErrorAction Stop).Source
Push-Location (Join-Path $ProjectRoot "frontend")
try {
    Invoke-Checked $npm @("ci", "--no-audit", "--no-fund")
    Invoke-Checked $npm @("run", "build")
} finally {
    Pop-Location
}

$pidFile = Join-Path $logsRoot "fastapi.pid"
if ([string]::IsNullOrWhiteSpace($pidFile)) {
    throw "PID file path could not be derived from logs directory '$logsRoot'."
}
$taskName = "AI-i2v FastAPI"
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $pidFile) {
    $oldPidText = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    $oldPid = 0
    if ([int]::TryParse($oldPidText, [ref]$oldPid)) {
        $oldProcess = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($null -ne $oldProcess) {
            Stop-Process -Id $oldPid -Force
            $oldProcess.WaitForExit(10000)
        }
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

$env:APP_HOST = "0.0.0.0"
$env:APP_PORT = "8015"
$env:APP_RELOAD = "false"

# 固定 OSS 素材库的非敏感配置。只补写 ECS 本地 .env 中缺少的字段，
# 不覆盖服务器已有值；临时 RAM 凭证仍由 ECS 实例角色自动获取。
$ossAssetPrefix = [string]::Concat([char]0x56FE, [char]0x7247, [char]0x7D20, [char]0x6750, [char]0x5E93)
$ossDefaults = @(
    "OSS_BUCKET=patrick0619",
    "OSS_ENDPOINT=https://oss-cn-shenzhen.aliyuncs.com",
    ("OSS_ASSET_PREFIX=" + $ossAssetPrefix),
    "OSS_REGION=cn-shenzhen",
    "OSS_RAM_ROLE_NAME=EcsOssAssetReadOnly"
)
$envPath = (Get-Location).Path + "\.env"
$envLines = if (Test-Path -LiteralPath $envPath) { @(Get-Content -LiteralPath $envPath -Encoding UTF8) } else { @() }
$defaultMap = @{}
foreach ($default in $ossDefaults) {
    $parts = $default.Split('=', 2)
    $defaultMap[$parts[0]] = $default
}
$changedEnv = $false
if ($envLines.Count -gt 0) {
foreach ($index in 0..($envLines.Count - 1)) {
    if ($envLines[$index] -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $key = $matches[1]
        if ($defaultMap.ContainsKey($key) -and [string]::IsNullOrWhiteSpace($matches[2])) {
            $envLines[$index] = $defaultMap[$key]
            $changedEnv = $true
        }
        $defaultMap.Remove($key)
    }
}
}
if ($defaultMap.Count -gt 0) {
    $envLines += "# Fixed OSS asset library (deployment defaults)"
    $envLines += @($defaultMap.Values)
    $changedEnv = $true
}
if ($changedEnv) {
    [IO.File]::WriteAllLines($envPath, $envLines, (New-Object Text.UTF8Encoding($false)))
}

# 公网访问依赖 Windows 入站放行；规则按固定名称幂等更新，避免每次部署重复创建。
New-NetFirewallRule -Name "AI-i2v-FastAPI-8015" -DisplayName "AI-i2v FastAPI 8015" -Direction Inbound -Protocol TCP -LocalPort 8015 -Action Allow -Profile Any -ErrorAction SilentlyContinue | Out-Null

$portOwners = @(Get-NetTCPConnection -LocalPort ([int]$env:APP_PORT) -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($portOwner in $portOwners) {
    $oldProcess = Get-Process -Id $portOwner -ErrorAction SilentlyContinue
    if ($null -ne $oldProcess) {
        $ownerInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$portOwner" -ErrorAction SilentlyContinue
        $ownerCommand = [string]$ownerInfo.CommandLine
        if ([string]::IsNullOrWhiteSpace($ownerCommand) -or ($ownerCommand -notlike "*web.run_server*" -and $ownerCommand -notlike "*$ProjectRoot*")) {
            throw "Port $($env:APP_PORT) is occupied by an unexpected process (PID $portOwner)."
        }
        Stop-Process -Id $portOwner -Force
        $oldProcess.WaitForExit(10000)
    }
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stdoutLog = Join-Path $logsRoot "fastapi-$stamp.out.log"
$stderrLog = Join-Path $logsRoot "fastapi-$stamp.err.log"
$launcherScript = Join-Path $ProjectRoot "scripts\run_fastapi_windows.ps1"
foreach ($requiredPath in @($stdoutLog, $stderrLog, $launcherScript)) {
    if ([string]::IsNullOrWhiteSpace($requiredPath)) {
        throw "A required deployment path was empty."
    }
}

$taskAction = New-ScheduledTaskAction `
    -Execute (Get-Command powershell.exe -ErrorAction Stop).Source `
    -Argument "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$launcherScript`" -ProjectRoot `"$ProjectRoot`" -OutputLog `"$stdoutLog`" -ErrorLog `"$stderrLog`"" `
    -WorkingDirectory $ProjectRoot
$taskTrigger = New-ScheduledTaskTrigger -AtStartup
$taskPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$taskSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable
Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $taskTrigger -Principal $taskPrincipal -Settings $taskSettings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName

$ready = $false
$serverPid = 0
for ($attempt = 1; $attempt -le 30; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8015/api/config" -UseBasicParsing -TimeoutSec 3
        $openApiResponse = Invoke-WebRequest -Uri "http://127.0.0.1:8015/openapi.json" -UseBasicParsing -TimeoutSec 3
        $openApi = $openApiResponse.Content | ConvertFrom-Json
        $hasOssRoute = $null -ne $openApi.paths.PSObject.Properties["/api/oss/categories"]
        if ($response.StatusCode -eq 200 -and $openApiResponse.StatusCode -eq 200 -and $hasOssRoute) {
            $serverPid = (Get-NetTCPConnection -LocalPort 8015 -State Listen -ErrorAction Stop | Select-Object -First 1).OwningProcess
            $ready = $true
            break
        }
    } catch {
    }
}

if (-not $ready) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "FastAPI failed to start. Recent error log:"
    $taskInfo = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -ne $taskInfo) {
        Write-Host "Scheduled task state=$($taskInfo.State), lastResult=$($taskInfo.LastTaskResult), lastRun=$($taskInfo.LastRunTime)"
    }
    $registeredTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -ne $registeredTask) {
        $registeredTask.Actions | Format-List Execute,Arguments,WorkingDirectory
    }
    Get-ChildItem -LiteralPath $logsRoot -Filter "fastapi-*.log" -ErrorAction SilentlyContinue | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize
    if (Test-Path -LiteralPath $stdoutLog) {
        Get-Content -LiteralPath $stdoutLog -Tail 80
    }
    if (Test-Path -LiteralPath $stderrLog) {
        Get-Content -LiteralPath $stderrLog -Tail 80
    }
    throw "FastAPI did not become ready within 30 seconds."
}

$serverPid | Set-Content -LiteralPath $pidFile -Encoding ascii
Write-Host "Native Windows deployment succeeded. PID=$serverPid, health check http://127.0.0.1:8015/api/config"
Write-Host "Stdout: $stdoutLog"
Write-Host "Stderr: $stderrLog"
