#Requires -Version 5.1
<#
.SYNOPSIS
  Parte 1 del instalador: dependencias que faltan y backend de GPU (CUDA o Vulkan).

.DESCRIPTION
  No instala nada y no descarga el modelo. Escribe un resumen y sale con código 1
  si falta Python 3.10–3.12, que es lo único que bloquea el paso siguiente.

.EXAMPLE
  .\installer\check_environment.ps1
#>
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step { param([string]$msg) Write-Host "`n$msg" -ForegroundColor Cyan }
function Write-OK   { param([string]$msg) Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn { param([string]$msg) Write-Host "  !   $msg" -ForegroundColor Yellow }
function Write-Miss { param([string]$msg) Write-Host "  --  $msg" -ForegroundColor Red }

function Get-PythonCandidates {
    $found = @()
    foreach ($ver in @("3.12", "3.11", "3.10", "3.13", "3.14")) {
        try {
            $exe = & py "-$ver" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe -and (Test-Path $exe.Trim())) {
                $found += [PSCustomObject]@{
                    Version = $ver
                    Exe     = $exe.Trim()
                    Usable  = $ver -in @("3.10", "3.11", "3.12")
                }
            }
        } catch { }
    }
    foreach ($cmd in @("python", "python3")) {
        $command = Get-Command $cmd -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        if ($command.Source -match "WindowsApps\\python") { continue }
        try {
            $text = & $command.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}|{sys.executable}')" 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $text) { continue }
            $parts = $text.Trim().Split("|")
            $ver = $parts[0]
            $exe = $parts[1]
            if ($found.Exe -contains $exe) { continue }
            $minor = [int]($ver.Split(".")[1])
            $found += [PSCustomObject]@{
                Version = $ver
                Exe     = $exe
                Usable  = ($ver.StartsWith("3.") -and $minor -ge 10 -and $minor -le 12)
            }
        } catch { }
    }
    return $found
}

function Get-VideoAdapters {
    try {
        return @(Get-CimInstance Win32_VideoController -ErrorAction Stop | Where-Object {
            $_.Name -and $_.Name -notmatch "Microsoft Basic"
        })
    } catch {
        return @()
    }
}

function Test-NvidiaCuda {
    $nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $nvidiaSmi) { return $null }
    try {
        $name = & nvidia-smi --query-gpu=name --format=csv,noheader 2>$null | Select-Object -First 1
        if ($name) { return $name.Trim() }
    } catch { }
    return $null
}

function Test-VulkanRuntime {
    $dll = Join-Path $env:SystemRoot "System32\vulkan-1.dll"
    $info = Get-Command vulkaninfo -ErrorAction SilentlyContinue
    return [PSCustomObject]@{
        Loader = Test-Path $dll
        Info   = [bool]$info
    }
}

Write-Host ""
Write-Host "Pygenesis Unreal — comprobación del equipo" -ForegroundColor Magenta
Write-Host "Esta parte no instala nada."
Write-Host ""

$missing = New-Object System.Collections.Generic.List[string]

Write-Step "Python 3.10–3.12"
$pythons = @(Get-PythonCandidates)
$usable = $pythons | Where-Object { $_.Usable } | Select-Object -First 1
if ($usable) {
    Write-OK "$($usable.Version)  $($usable.Exe)"
} else {
    Write-Miss "No hay Python 3.10, 3.11 ni 3.12."
    Write-Host "      winget install Python.Python.3.12" -ForegroundColor DarkGray
    $missing.Add("Python 3.10–3.12")
}
foreach ($extra in @($pythons | Where-Object { -not $_.Usable })) {
    Write-Warn "$($extra.Version) está instalado y no sirve para el runtime: $($extra.Exe)"
}

Write-Step "GPU"
$adapters = @(Get-VideoAdapters)
if ($adapters.Count -eq 0) {
    Write-Warn "Windows no lista una GPU distinta del adaptador básico."
} else {
    foreach ($gpu in $adapters) {
        Write-OK $gpu.Name
    }
}

$cudaName = Test-NvidiaCuda
$vulkan = Test-VulkanRuntime
if ($cudaName) {
    Write-OK "CUDA  nvidia-smi ve: $cudaName"
} else {
    Write-Miss "CUDA  no hay nvidia-smi."
}
if ($vulkan.Loader) {
    Write-OK "Vulkan  vulkan-1.dll está en System32."
} else {
    Write-Miss "Vulkan  no está vulkan-1.dll. Instala el runtime de la GPU (AMD Adrenalin o el de NVIDIA)."
}
if ($vulkan.Info) {
    Write-OK "vulkaninfo está en el PATH."
}

$backend = "cpu"
if ($cudaName) {
    $backend = "cuda"
} elseif ($vulkan.Loader -and $adapters.Count -gt 0) {
    $backend = "vulkan"
} else {
    $missing.Add("GPU con CUDA o Vulkan")
}

Write-Step "Red hacia Hugging Face"
try {
    $response = Invoke-WebRequest -Uri "https://huggingface.co" -Method Head -TimeoutSec 8 -UseBasicParsing
    if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        Write-OK "huggingface.co responde."
    } else {
        Write-Warn "huggingface.co respondió $($response.StatusCode)."
    }
} catch {
    Write-Warn "No se ha podido contactar huggingface.co. La descarga del GGUF lo necesita."
}

$reportDir = Join-Path $env:LOCALAPPDATA "PygenesisUnreal"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$report = [ordered]@{
    python  = if ($usable) { $usable.Exe } else { "" }
    backend = $backend
    cuda    = [bool]$cudaName
    vulkan  = [bool]$vulkan.Loader
    ok      = ($missing.Count -eq 0)
}
$report | ConvertTo-Json | Set-Content -Path (Join-Path $reportDir "environment.json") -Encoding UTF8

Write-Host ""
Write-Host "Backend recomendado: $backend" -ForegroundColor Cyan
if ($missing.Count -eq 0) {
    Write-Host "Listo para la parte siguiente: runtime, backend $backend y descarga del modelo." -ForegroundColor Green
    exit 0
}

Write-Host "Falta:" -ForegroundColor Yellow
foreach ($item in $missing) {
    Write-Host "  - $item"
}
exit 1
