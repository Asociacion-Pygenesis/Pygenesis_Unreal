#Requires -Version 5.1
<#
.SYNOPSIS
  Instala el plugin Pygenesis Unreal en un proyecto Unreal Engine.

.DESCRIPTION
  Copia plugin/PygenesisUnreal a <Project>/Plugins/PygenesisUnreal
  y habilita la entrada en el .uproject.

.PARAMETER ProjectPath
  Ruta al directorio del proyecto (.uproject en la raíz) o ruta al .uproject.

.PARAMETER Force
  Sobrescribe una instalación previa.

.EXAMPLE
  .\install_plugin.ps1 -ProjectPath "C:\Users\navar\Documents\Unreal Projects\PygenUnrealSandbox" -Force
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectPath,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$PluginRoot = Split-Path $PSScriptRoot -Parent
$SourceDir = Join-Path $PluginRoot "PygenesisUnreal"

if (-not (Test-Path $SourceDir)) {
    throw "No se encontró el plugin en: $SourceDir"
}

$projectDir = $ProjectPath
$uprojectPath = $null
if ($ProjectPath -like "*.uproject") {
    $uprojectPath = $ProjectPath
    $projectDir = Split-Path $ProjectPath -Parent
} else {
    $found = Get-ChildItem -Path $projectDir -Filter "*.uproject" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $uprojectPath = $found.FullName }
}

if (-not (Test-Path $projectDir)) {
    throw "No existe el proyecto: $projectDir"
}
if (-not $uprojectPath -or -not (Test-Path $uprojectPath)) {
    throw "No se encontró .uproject en: $projectDir"
}

$targetRoot = Join-Path $projectDir "Plugins"
$targetDir = Join-Path $targetRoot "PygenesisUnreal"

New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null

if (Test-Path $targetDir) {
    if (-not $Force) {
        Write-Host "El plugin ya está en: $targetDir" -ForegroundColor Yellow
        Write-Host "Usa -Force para actualizar."
        exit 1
    }
    # Si Unreal tiene el DLL bloqueado, sincroniza fuentes sin borrar Binaries.
    try {
        Remove-Item $targetDir -Recurse -Force -ErrorAction Stop
        Copy-Item -Path $SourceDir -Destination $targetRoot -Recurse -Force
    } catch {
        Write-Host "AVISO: no se pudo reemplazar todo (Unreal abierto?). Sincronizando Source/uplugin..." -ForegroundColor Yellow
        Copy-Item (Join-Path $SourceDir "PygenesisUnreal.uplugin") (Join-Path $targetDir "PygenesisUnreal.uplugin") -Force
        $srcSource = Join-Path $SourceDir "Source"
        $dstSource = Join-Path $targetDir "Source"
        if (Test-Path $dstSource) { Remove-Item $dstSource -Recurse -Force -ErrorAction SilentlyContinue }
        Copy-Item -Path $srcSource -Destination $dstSource -Recurse -Force
        Write-Host "Recompila el plugin en el Editor (Binaries bloqueados)." -ForegroundColor Cyan
    }
} else {
    Copy-Item -Path $SourceDir -Destination $targetRoot -Recurse -Force
}
Write-Host "Plugin copiado a: $targetDir" -ForegroundColor Green

# Habilitar en .uproject
$json = Get-Content -LiteralPath $uprojectPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $json.Plugins) {
    $json | Add-Member -NotePropertyName Plugins -NotePropertyValue @() -Force
}
$plugins = [System.Collections.Generic.List[object]]::new()
foreach ($p in @($json.Plugins)) {
    if ($null -ne $p -and $p.Name -ne "PygenesisUnreal") {
        $plugins.Add($p)
    }
}
$plugins.Add([pscustomobject]@{ Name = "PygenesisUnreal"; Enabled = $true })
$json.Plugins = $plugins.ToArray()

$out = $json | ConvertTo-Json -Depth 20
# ConvertTo-Json puede poner UTF8 BOM issues; escribir UTF8 sin BOM
[System.IO.File]::WriteAllText($uprojectPath, $out, [System.Text.UTF8Encoding]::new($false))
Write-Host "Plugin habilitado en: $uprojectPath" -ForegroundColor Green
Write-Host "Abre el .uproject con UE 5.7, compila si pide, y usa Window → Pygenesis Unreal." -ForegroundColor Cyan
