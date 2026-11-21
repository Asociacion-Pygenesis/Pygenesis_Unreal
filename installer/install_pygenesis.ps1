#Requires -Version 5.1
<#
.SYNOPSIS
  Instalador cerrado: GPU + inferencia + modelo HF + plugin Unreal Editor.

.DESCRIPTION
  1. Crea runtime Python en %LOCALAPPDATA%\PygenesisUnreal\runtime\
  2. Detecta GPU e instala llama-cpp-python
  3. Descarga GGUF desde Hugging Face (SuNavar/Pygenesis_Unreal)
  4. Instala el plugin Unreal Editor (stub)
  5. Crea atajos en el menú Inicio (solo Backend; sin Companion)

.PARAMETER Backend
  Forzar backend: auto | cuda | vulkan | cpu

.PARAMETER SkipModelDownload
  No descarga ni copia el modelo

.PARAMETER UseLocalModel
  Copia pygenesis-unreal-q4km.gguf desde la raíz del repo (sin Hugging Face)

.PARAMETER ProjectPath
  Proyecto Unreal (.uproject o carpeta) donde instalar el plugin

.PARAMETER SkipPlugin
  Solo instala puente + modelo

.PARAMETER SkipShortcuts
  No crea atajos del menú Inicio

.EXAMPLE
  .\install_pygenesis.ps1 -UseLocalModel -ProjectPath "C:\Users\navar\Documents\Unreal Projects\PygenUnrealSandbox"
  .\install_pygenesis.ps1 -Backend vulkan
#>
param(
    [ValidateSet("auto", "cuda", "vulkan", "cpu")]
    [string]$Backend = "auto",
    [switch]$SkipModelDownload,
    [switch]$UseLocalModel,
    [string]$ProjectPath = "",
    [switch]$SkipPlugin,
    [switch]$SkipShortcuts
)

$ErrorActionPreference = "Stop"
$InstallerRoot = $PSScriptRoot
$RepoRoot = Split-Path $InstallerRoot -Parent
$BackendScripts = Join-Path $RepoRoot "backend\scripts"
$PluginScripts = Join-Path $RepoRoot "plugin\scripts"
$ModelSourcePath = Join-Path $InstallerRoot "model.source.json"
$PygenesisHome = Join-Path $env:LOCALAPPDATA "PygenesisUnreal"
$RuntimeDir = Join-Path $PygenesisHome "runtime"
$RuntimePython = Join-Path $RuntimeDir "Scripts\python.exe"
$AppDir = Join-Path $PygenesisHome "app"
$BridgeEnv = Join-Path $PygenesisHome "bridge.env"

function Set-BridgeEnvValue {
    param([string]$Path, [string]$Name, [string]$Value)
    # Evitar valores multilinea / basura de pip mezclada en PowerShell returns
    $clean = ([string]$Value).Trim()
    if ($Name -eq "PYGENESIS_PYTHON") {
        if ($clean -match '(?i)((?:[A-Za-z]:\\|\\\\)[^\r\n]*python\.exe)\s*$') {
            $clean = $Matches[1].Trim()
        }
        if ($clean -notmatch '(?i)\.exe$') {
            throw "PYGENESIS_PYTHON invalido (no es una ruta .exe): $clean"
        }
    }
    if ($clean -match "[\r\n]") {
        throw "Valor de bridge.env invalido para ${Name}: contiene saltos de linea"
    }
    $lines = @()
    if (Test-Path $Path) {
        $lines = @(Get-Content $Path | Where-Object { $_ -notmatch "^\s*$([regex]::Escape($Name))\s*=" })
    }
    $lines += "$Name=$clean"
    New-Item -ItemType Directory -Force -Path (Split-Path $Path -Parent) | Out-Null
    $lines | Set-Content -Path $Path -Encoding UTF8
}

function Import-BridgeEnv {
    if (-not (Test-Path $BridgeEnv)) { return }
    Get-Content $BridgeEnv | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            Set-Item -Path "Env:$($matches[1].Trim())" -Value $matches[2].Trim()
        }
    }
}

function Get-SystemPython {
    # Preferir 3.12 / 3.11 / 3.10: llama-cpp-python suele tener wheels; 3.13+ fuerza compile y MAX_PATH.
    foreach ($ver in @("3.12", "3.11", "3.10")) {
        try {
            $resolved = & py "-$ver" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path $resolved.Trim())) {
                return $resolved.Trim()
            }
        } catch { }
    }

    $candidates = @()
    foreach ($cmd in @("python", "python3")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) { $candidates += $found.Source }
    }
    foreach ($exe in ($candidates | Select-Object -Unique)) {
        try {
            if ($exe -match 'WindowsApps\\python') { continue }
            $verText = & $exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $verText) { continue }
            $parts = $verText.Trim().Split('.')
            $major = [int]$parts[0]; $minor = [int]$parts[1]
            if ($major -eq 3 -and $minor -ge 10 -and $minor -le 12) {
                $resolved = & $exe -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path $resolved.Trim())) {
                    return $resolved.Trim()
                }
                return $exe
            }
        } catch { }
    }
    return $null
}

function Get-PythonMinorVersion {
    param([string]$PythonExe)
    try {
        $v = & $PythonExe -c "import sys; print(sys.version_info.minor)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) { return [int]$v.Trim() }
    } catch { }
    return -1
}

function Ensure-RuntimeVenv {
    if (Test-Path $RuntimePython) {
        $minor = Get-PythonMinorVersion -PythonExe $RuntimePython
        if ($minor -ge 0 -and $minor -le 12) {
            Write-Host "Runtime ya presente (Python 3.$minor): $RuntimePython" -ForegroundColor Green
            return $RuntimePython
        }
        Write-Host "Runtime usa Python 3.$minor; llama-cpp-python no suele tener wheels -> MAX_PATH al compilar." -ForegroundColor Yellow
        Write-Host "Recreando runtime con Python 3.12/3.11..." -ForegroundColor Cyan
        Remove-Item $RuntimeDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    $sysPy = Get-SystemPython
    if (-not $sysPy) {
        throw "Se necesita Python 3.10-3.12 en PATH (recomendado 3.12). Evita 3.13/3.14 para el runtime. https://www.python.org/downloads/"
    }

    $sysMinor = Get-PythonMinorVersion -PythonExe $sysPy
    Write-Host "Creando runtime en $RuntimeDir ..." -ForegroundColor Cyan
    Write-Host "  Base: $sysPy (3.$sysMinor)" -ForegroundColor DarkGray
    New-Item -ItemType Directory -Force -Path $PygenesisHome | Out-Null
    & $sysPy -m venv $RuntimeDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $RuntimePython)) {
        throw "No se pudo crear el venv en $RuntimeDir"
    }
    # Critico: redirigir salida de pip; si no, PowerShell la mezcla en el return de la funcion.
    & $RuntimePython -m pip install --upgrade pip 2>&1 | ForEach-Object { Write-Host $_ }
    if (-not (Test-Path $RuntimePython)) {
        throw "Runtime python desaparecio tras pip upgrade: $RuntimePython"
    }
    return [string]$RuntimePython
}

function Sync-AppPayload {
    $destBackend = Join-Path $AppDir "backend"
    $destInstaller = Join-Path $AppDir "installer"
    $destPlugin = Join-Path $AppDir "plugin"
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

    foreach ($pair in @(
        @{ Src = (Join-Path $RepoRoot "backend"); Dst = $destBackend },
        @{ Src = (Join-Path $RepoRoot "installer"); Dst = $destInstaller },
        @{ Src = (Join-Path $RepoRoot "plugin"); Dst = $destPlugin }
    )) {
        if (-not (Test-Path $pair.Src)) { continue }
        if (Test-Path $pair.Dst) {
            Remove-Item $pair.Dst -Recurse -Force
        }
        Copy-Item -Path $pair.Src -Destination $pair.Dst -Recurse
    }

    Get-ChildItem $AppDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "App instalada en: $AppDir" -ForegroundColor DarkGray
    return $destBackend
}

function Get-ModelSource {
    if (-not (Test-Path $ModelSourcePath)) {
        throw "Falta $ModelSourcePath"
    }
    return Get-Content $ModelSourcePath -Raw | ConvertFrom-Json
}

function Ensure-LocalModelCopied {
    $source = Get-ModelSource
    $modelDir = Join-Path $PygenesisHome "models"
    New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
    $dest = Join-Path $modelDir $source.filename
    if (Test-Path $dest) {
        Write-Host "Modelo ya presente: $dest" -ForegroundColor Green
        return $dest
    }
    $localCandidates = @(
        (Join-Path $RepoRoot $source.filename),
        (Join-Path $RepoRoot "models\$($source.filename)")
    )
    $src = $localCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $src) {
        throw "UseLocalModel: no se encontro $($source.filename) en la raiz del repo ($RepoRoot)"
    }
    Write-Host "Copiando modelo local..." -ForegroundColor Cyan
    Write-Host "  Desde: $src" -ForegroundColor DarkGray
    Write-Host "  Hacia: $dest" -ForegroundColor DarkGray
    Copy-Item -LiteralPath $src -Destination $dest -Force
    Write-Host "Modelo copiado: $dest" -ForegroundColor Green
    return $dest
}

function Ensure-ModelDownloaded {
    param([string]$PythonExe)
    $source = Get-ModelSource
    $modelDir = Join-Path $PygenesisHome "models"
    New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
    $dest = Join-Path $modelDir $source.filename

    if (Test-Path $dest) {
        Write-Host "Modelo ya presente: $dest" -ForegroundColor Green
        return $dest
    }

    Write-Host "Descargando modelo desde Hugging Face ($($source.repo_id))..." -ForegroundColor Cyan
    Write-Host "  Archivo: $($source.filename)  (puede tardar varios minutos)" -ForegroundColor DarkGray
    & $PythonExe -m pip install "huggingface-hub>=0.23" -q
    if ($LASTEXITCODE -ne 0) { throw "No se pudo instalar huggingface-hub" }

    $py = @"
import json
from pathlib import Path
from huggingface_hub import hf_hub_download

source = json.loads(Path(r'$ModelSourcePath').read_text(encoding='utf-8'))
dest_dir = Path(r'$modelDir')
dest_dir.mkdir(parents=True, exist_ok=True)
path = hf_hub_download(
    repo_id=source['repo_id'],
    filename=source['filename'],
    revision=source.get('revision') or 'main',
    local_dir=str(dest_dir),
    local_dir_use_symlinks=False,
)
print(path)
"@
    $downloaded = & $PythonExe -c $py
    if ($LASTEXITCODE -ne 0) {
        throw "Falló la descarga del modelo. Comprueba repo_id en installer/model.source.json y la red."
    }
    if (-not (Test-Path $dest)) {
        if ($downloaded -and (Test-Path "$downloaded")) {
            Copy-Item "$downloaded" $dest -Force
        }
    }
    if (-not (Test-Path $dest)) {
        throw "Descarga OK pero no se encontró $dest"
    }
    Write-Host "Modelo descargado: $dest" -ForegroundColor Green
    return $dest
}

function New-Shortcut {
    param(
        [string]$LinkPath,
        [string]$TargetPath,
        [string]$Arguments = "",
        [string]$WorkingDirectory = "",
        [string]$Description = ""
    )
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($LinkPath)
    $sc.TargetPath = $TargetPath
    if ($Arguments) { $sc.Arguments = $Arguments }
    if ($WorkingDirectory) { $sc.WorkingDirectory = $WorkingDirectory }
    if ($Description) { $sc.Description = $Description }
    $sc.Save()
}

function Install-StartMenuShortcuts {
    param(
        [string]$BackendStartScript
    )
    $programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Pygenesis Unreal"
    New-Item -ItemType Directory -Force -Path $programs | Out-Null

    $backendLink = Join-Path $programs "Pygenesis Unreal Backend.lnk"
    New-Shortcut -LinkPath $backendLink `
        -TargetPath "powershell.exe" `
        -Arguments "-NoExit -ExecutionPolicy Bypass -File `"$BackendStartScript`"" `
        -WorkingDirectory (Split-Path $BackendStartScript -Parent) `
        -Description "Arranca el puente de inferencia local (puerto 8000)"

    Write-Host "Atajos creados en: $programs" -ForegroundColor Green
}

Write-Host "=== Pygenesis UnrealExpert — Instalador ===" -ForegroundColor Cyan
Write-Host ""

$pythonExe = Ensure-RuntimeVenv
Set-BridgeEnvValue -Path $BridgeEnv -Name "PYGENESIS_PYTHON" -Value $pythonExe
$env:PYGENESIS_PYTHON = $pythonExe

Write-Host ""
Write-Host "[1/4] Sincronizando app e instalando motor de inferencia..." -ForegroundColor Cyan
$appBackend = Sync-AppPayload
$appBackendScripts = Join-Path $appBackend "scripts"
& (Join-Path $BackendScripts "install_inference.ps1") -Backend $Backend -PythonExe $pythonExe -AllowCpuFallback
if ($LASTEXITCODE -ne 0) { exit 1 }

Import-BridgeEnv

if (-not $SkipModelDownload) {
    Write-Host ""
    if ($UseLocalModel) {
        Write-Host "[2/4] Modelo GGUF (copia local)..." -ForegroundColor Cyan
        $modelPath = Ensure-LocalModelCopied
    } else {
        Write-Host "[2/4] Modelo GGUF (Hugging Face)..." -ForegroundColor Cyan
        $modelPath = Ensure-ModelDownloaded -PythonExe $pythonExe
    }
    Set-BridgeEnvValue -Path $BridgeEnv -Name "PYGENESIS_MODEL_PATH" -Value $modelPath
    Write-Host "PYGENESIS_MODEL_PATH=$modelPath" -ForegroundColor DarkGray
} else {
    Write-Host ""
    Write-Host "[2/4] Modelo omitido (-SkipModelDownload)" -ForegroundColor Yellow
}

if (-not $SkipPlugin) {
    Write-Host ""
    Write-Host "[3/4] Plugin Unreal Editor..." -ForegroundColor Cyan
    if (-not $ProjectPath) {
        Write-Host "Indica la carpeta o .uproject del proyecto Unreal donde instalar el plugin." -ForegroundColor Yellow
        $ProjectPath = Read-Host "ProjectPath"
    }
    if (-not $ProjectPath) {
        throw "ProjectPath vacio. Ejemplo: -ProjectPath `"C:\Users\navar\Documents\Unreal Projects\PygenUnrealSandbox`""
    }
    & (Join-Path $PluginScripts "install_plugin.ps1") -ProjectPath $ProjectPath -Force
    if ($LASTEXITCODE -ne 0) { exit 1 }
} else {
    Write-Host ""
    Write-Host "[3/4] Plugin omitido (-SkipPlugin)" -ForegroundColor Yellow
}

$backendStart = Join-Path $appBackendScripts "start_backend.ps1"
if (-not (Test-Path $backendStart)) {
    $backendStart = Join-Path $BackendScripts "start_backend.ps1"
}

$homeStartBackend = Join-Path $PygenesisHome "Start-Backend.ps1"
@"
#Requires -Version 5.1
& '$backendStart' @args
"@ | Set-Content -Path $homeStartBackend -Encoding UTF8

if (-not $SkipShortcuts) {
    Write-Host ""
    Write-Host "[4/4] Atajos del menú Inicio..." -ForegroundColor Cyan
    Install-StartMenuShortcuts -BackendStartScript $homeStartBackend
} else {
    Write-Host ""
    Write-Host "[4/4] Atajos omitidos (-SkipShortcuts)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Instalación completada ===" -ForegroundColor Green
Write-Host "  Runtime     : $RuntimeDir" -ForegroundColor DarkGray
Write-Host "  App         : $AppDir" -ForegroundColor DarkGray
Write-Host "  Config      : $BridgeEnv" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Siguiente paso:" -ForegroundColor Cyan
Write-Host "  1. Arranca el puente: menú Inicio → Pygenesis Unreal Backend"
Write-Host "     (o: powershell -File `"$homeStartBackend`")"
Write-Host "  2. En Unreal Editor: Window → Pygenesis Unreal (ventana del plugin)"
Write-Host "     (sin Companion: el chat vive dentro del Editor)"
Write-Host ""
