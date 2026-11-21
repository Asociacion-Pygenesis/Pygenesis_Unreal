#Requires -Version 5.1
<#
.SYNOPSIS
  Parte 3: copia el plugin Pygenesis Unreal dentro de un proyecto .uproject.

.DESCRIPTION
  Si no pasas -ProjectPath y solo hay un .uproject en Documentos\Unreal Projects, usa ese.
  No compila: Unreal tiene que recompilar el módulo al abrir el proyecto.

.PARAMETER ProjectPath
  Carpeta del proyecto o ruta al .uproject.

.EXAMPLE
  .\installer\install_unreal_plugin.ps1
  .\installer\install_unreal_plugin.ps1 -ProjectPath "C:\Users\navar\Documents\Unreal Projects\PygenUnrealSandbox"
#>
param(
    [string]$ProjectPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step { param([string]$msg) Write-Host "`n$msg" -ForegroundColor Cyan }
function Write-OK   { param([string]$msg) Write-Host "  OK  $msg" -ForegroundColor Green }

$InstallerRoot = $PSScriptRoot
$RepoRoot = Split-Path $InstallerRoot -Parent
$CopyScript = Join-Path $RepoRoot "plugin\scripts\install_plugin.ps1"
$BridgeEnv = Join-Path $env:LOCALAPPDATA "PygenesisUnreal\bridge.env"

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

function Find-UnrealProjects {
    $roots = @(
        (Join-Path $env:USERPROFILE "Documents\Unreal Projects"),
        (Join-Path $env:USERPROFILE "Documents\UnrealProjects")
    )
    $found = @()
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $found += @(Get-ChildItem -Path $root -Filter "*.uproject" -File -Recurse -Depth 2 -ErrorAction SilentlyContinue)
    }
    return $found
}

Write-Host ""
Write-Host "Pygenesis Unreal — plugin del Editor" -ForegroundColor Magenta

Write-Step "Proyecto Unreal"
if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    $projects = @(Find-UnrealProjects)
    if ($projects.Count -eq 0) {
        throw "No hay ningún .uproject en Documentos\Unreal Projects. Pasa -ProjectPath."
    }
    if ($projects.Count -gt 1) {
        Write-Host "Hay varios proyectos. Elige uno con -ProjectPath:" -ForegroundColor Yellow
        foreach ($item in $projects) { Write-Host "  $($item.FullName)" }
        exit 1
    }
    $ProjectPath = $projects[0].FullName
    Write-OK "Único proyecto encontrado: $ProjectPath"
} else {
    Write-OK $ProjectPath
}

Write-Step "Copiando PygenesisUnreal"
& $CopyScript -ProjectPath $ProjectPath -Force
if (-not $?) { exit 1 }

$uproject = $ProjectPath
if ($ProjectPath -notlike "*.uproject") {
    $file = Get-ChildItem -Path $ProjectPath -Filter "*.uproject" -File | Select-Object -First 1
    if (-not $file) { throw "No se encontró el .uproject tras copiar." }
    $uproject = $file.FullName
}
Set-BridgeEnvValue -Path $BridgeEnv -Name "PYGENESIS_UPROJECT" -Value $uproject

Write-Host ""
Write-Host "Plugin colocado." -ForegroundColor Green
Write-Host "  Proyecto: $uproject"
Write-Host ""
Write-Host "Abre ese proyecto en Unreal 5.7. Si el editor pide compilar, acepta." -ForegroundColor Cyan
Write-Host "La ventana queda en Window → Pygenesis Unreal." -ForegroundColor Cyan
