#Requires -Version 5.1
<#
.SYNOPSIS
  Parte 2: runtime Python 3.12, backend de inferencia y descarga del GGUF.

.DESCRIPTION
  Usa el resultado de check_environment.ps1. No copia el plugin al proyecto Unreal.

.PARAMETER Backend
  auto usa el backend escrito por la comprobación (cuda, vulkan o cpu).

.EXAMPLE
  .\installer\install_backend.ps1
  .\installer\install_backend.ps1 -Backend vulkan
#>
param(
    [ValidateSet("auto", "cuda", "vulkan", "cpu")]
    [string]$Backend = "auto"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step { param([int]$n, [int]$total, [string]$msg) Write-Host "`n[$n/$total] $msg" -ForegroundColor Cyan }
function Write-OK   { param([string]$msg) Write-Host "  OK  $msg" -ForegroundColor Green }

$InstallerRoot = $PSScriptRoot
$RepoRoot = Split-Path $InstallerRoot -Parent
$PygenesisHome = Join-Path $env:LOCALAPPDATA "PygenesisUnreal"
$RuntimeDir = Join-Path $PygenesisHome "runtime"
$RuntimePython = Join-Path $RuntimeDir "Scripts\python.exe"
$BridgeEnv = Join-Path $PygenesisHome "bridge.env"
$ModelSourcePath = Join-Path $InstallerRoot "model.source.json"
$CheckScript = Join-Path $InstallerRoot "check_environment.ps1"
$InferenceScript = Join-Path $RepoRoot "backend\scripts\install_inference.ps1"

function Set-BridgeEnvValue {
    param([string]$Path, [string]$Name, [string]$Value)
    $clean = ([string]$Value).Trim()
    if ($clean -match "[\r\n]") { throw "Valor inválido para ${Name}" }
    $lines = @()
    if (Test-Path $Path) {
        $lines = @(Get-Content $Path | Where-Object { $_ -notmatch "^\s*$([regex]::Escape($Name))\s*=" })
    }
    $lines += "$Name=$clean"
    New-Item -ItemType Directory -Force -Path (Split-Path $Path -Parent) | Out-Null
    $lines | Set-Content -Path $Path -Encoding UTF8
}

Write-Host ""
Write-Host "Pygenesis Unreal — runtime, backend y modelo" -ForegroundColor Magenta

Write-Step 1 4 "Comprobando el equipo"
& $CheckScript
if ($LASTEXITCODE -ne 0) { exit 1 }

$reportPath = Join-Path $PygenesisHome "environment.json"
if (-not (Test-Path $reportPath)) { throw "La comprobación no escribió $reportPath" }
$report = Get-Content $reportPath -Raw | ConvertFrom-Json
if ($Backend -eq "auto") { $Backend = [string]$report.backend }
if (-not $Backend) { throw "No hay backend recomendado." }
Write-OK "Backend: $Backend"

Write-Step 2 4 "Runtime Python 3.12"
$basePy = [string]$report.python
if (-not $basePy -or -not (Test-Path $basePy)) {
    throw "Python usable no encontrado. Instala 3.12 y vuelve a lanzar la comprobación."
}
$needsVenv = -not (Test-Path $RuntimePython)
if (-not $needsVenv) {
    $minorText = & $RuntimePython -c "import sys; print(sys.version_info.minor)"
    $minor = [int]$minorText.Trim()
    if ($minor -lt 10 -or $minor -gt 12) {
        Write-Host "  El runtime usa Python 3.$minor. Se recrea con $($report.python)." -ForegroundColor Yellow
        Remove-Item $RuntimeDir -Recurse -Force
        $needsVenv = $true
    }
}
if ($needsVenv) {
    Write-Host "  Creando $RuntimeDir" -ForegroundColor DarkGray
    & $basePy -m venv $RuntimeDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $RuntimePython)) {
        throw "No se pudo crear el runtime."
    }
    & $RuntimePython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade falló." }
}
Write-OK $RuntimePython
Set-BridgeEnvValue -Path $BridgeEnv -Name "PYGENESIS_PYTHON" -Value $RuntimePython

Write-Step 3 4 "Motor de inferencia ($Backend)"
& $InferenceScript -Backend $Backend -PythonExe $RuntimePython -AllowCpuFallback
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-OK "llama-cpp-python instalado"

Write-Step 4 4 "Modelo GGUF desde Hugging Face"
if (-not (Test-Path $ModelSourcePath)) { throw "Falta $ModelSourcePath" }
$source = Get-Content $ModelSourcePath -Raw | ConvertFrom-Json
$modelDir = Join-Path $PygenesisHome "models"
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
$modelPath = Join-Path $modelDir $source.filename
if (Test-Path $modelPath) {
    Write-OK "Ya estaba: $modelPath"
} else {
    Write-Host "  $($source.repo_id) / $($source.filename)" -ForegroundColor DarkGray
    & $RuntimePython -m pip install "huggingface-hub>=0.23,<2" --quiet
    if ($LASTEXITCODE -ne 0) { throw "No se pudo instalar huggingface-hub." }
    $py = @"
from pathlib import Path
from huggingface_hub import hf_hub_download
dest = Path(r'$modelDir')
dest.mkdir(parents=True, exist_ok=True)
path = hf_hub_download(
    repo_id=r'$($source.repo_id)',
    filename=r'$($source.filename)',
    revision=r'$($source.revision)',
    local_dir=str(dest),
)
print(path)
"@
    & $RuntimePython -c $py
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $modelPath)) {
        throw "La descarga no dejó $modelPath. Si el repo es privado, entra antes con el token de Hugging Face."
    }
    Write-OK $modelPath
}
Set-BridgeEnvValue -Path $BridgeEnv -Name "PYGENESIS_MODEL_PATH" -Value $modelPath
Set-BridgeEnvValue -Path $BridgeEnv -Name "PYGENESIS_GPU_BACKEND" -Value $Backend

Write-Host ""
Write-Host "Runtime y modelo listos." -ForegroundColor Green
Write-Host "  Python : $RuntimePython"
Write-Host "  Backend: $Backend"
Write-Host "  Modelo : $modelPath"
Write-Host ""
Write-Host "Siguiente parte: copiar el plugin al proyecto de Unreal." -ForegroundColor Cyan
