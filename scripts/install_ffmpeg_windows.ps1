[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$runtimeRoot = Join-Path $ProjectRoot ".runtime"
$targetRoot = Join-Path $runtimeRoot "ffmpeg"
$targetEncoder = Join-Path $targetRoot "bin\ffmpeg.exe"
$targetProbe = Join-Path $targetRoot "bin\ffprobe.exe"

if ((Test-Path -LiteralPath $targetEncoder -PathType Leaf) -and (Test-Path -LiteralPath $targetProbe -PathType Leaf)) {
    Write-Host "Project-local FFmpeg runtime is already installed."
    exit 0
}
if (Test-Path -LiteralPath $targetRoot) {
    throw "Incomplete FFmpeg runtime exists at '$targetRoot'. Remove or repair that directory before deployment."
}

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$stagingRoot = Join-Path $runtimeRoot ("ffmpeg-install-" + [Guid]::NewGuid().ToString("N"))
$archivePath = Join-Path $stagingRoot "ffmpeg-release-essentials.zip"
$extractRoot = Join-Path $stagingRoot "extract"
New-Item -ItemType Directory -Force -Path $stagingRoot, $extractRoot | Out-Null

try {
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -UseBasicParsing -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $archivePath
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot -Force
    $buildRoot = Get-ChildItem -LiteralPath $extractRoot -Directory |
        Where-Object {
            (Test-Path -LiteralPath (Join-Path $_.FullName "bin\ffmpeg.exe") -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $_.FullName "bin\ffprobe.exe") -PathType Leaf)
        } |
        Select-Object -First 1
    if ($null -eq $buildRoot) {
        throw "Downloaded FFmpeg archive did not contain ffmpeg.exe and ffprobe.exe."
    }
    Move-Item -LiteralPath $buildRoot.FullName -Destination $targetRoot
    Write-Host "Installed project-local FFmpeg runtime at $targetRoot"
} finally {
    $resolvedRuntime = [IO.Path]::GetFullPath($runtimeRoot).TrimEnd('\') + '\'
    $resolvedStaging = [IO.Path]::GetFullPath($stagingRoot)
    if ($resolvedStaging.StartsWith($resolvedRuntime, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedStaging)) {
        Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
    }
}

