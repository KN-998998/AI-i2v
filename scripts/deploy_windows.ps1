[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
Set-Location -LiteralPath $ProjectRoot

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
New-Item -ItemType Directory -Force -Path $logsRoot, $outputRoot | Out-Null

$git = (Get-Command git.exe -ErrorAction Stop).Source
Invoke-Checked $git @("-c", "http.connectTimeout=20", "-c", "http.lowSpeedLimit=1", "-c", "http.lowSpeedTime=300", "pull", "--ff-only", "origin", "main")

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

Invoke-Checked $venvPython @("-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt")

$npm = (Get-Command npm.cmd -ErrorAction Stop).Source
Push-Location (Join-Path $ProjectRoot "frontend")
try {
    Invoke-Checked $npm @("ci", "--no-audit", "--no-fund")
    Invoke-Checked $npm @("run", "build")
} finally {
    Pop-Location
}

$pidFile = Join-Path $logsRoot "fastapi.pid"
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

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:APP_HOST = "0.0.0.0"
$env:APP_PORT = "8015"
$env:APP_RELOAD = "false"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stdoutLog = Join-Path $logsRoot "fastapi-$stamp.out.log"
$stderrLog = Join-Path $logsRoot "fastapi-$stamp.err.log"

$server = Start-Process -FilePath $venvPython `
    -ArgumentList @("-X", "utf8", "-m", "web.run_server") `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -WindowStyle Hidden `
    -PassThru
$server.Id | Set-Content -LiteralPath $pidFile -Encoding ascii

$ready = $false
for ($attempt = 1; $attempt -le 30; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8015/api/config" -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        if (-not (Get-Process -Id $server.Id -ErrorAction SilentlyContinue)) {
            break
        }
    }
}

if (-not $ready) {
    if (Get-Process -Id $server.Id -ErrorAction SilentlyContinue) {
        Stop-Process -Id $server.Id -Force
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "FastAPI failed to start. Recent error log:"
    if (Test-Path -LiteralPath $stderrLog) {
        Get-Content -LiteralPath $stderrLog -Tail 80
    }
    throw "FastAPI did not become ready within 30 seconds."
}

Write-Host "Native Windows deployment succeeded. PID=$($server.Id), health check http://127.0.0.1:8015/api/config"
Write-Host "Stdout: $stdoutLog"
Write-Host "Stderr: $stderrLog"
