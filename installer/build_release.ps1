#Requires -Version 5.1
<#
.SYNOPSIS
  Empaqueta release Windows de Pygenesis Unreal (sin Companion).

.EXAMPLE
  .\build_release.ps1 -Version 0.1.0
#>
param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$OutRoot = Join-Path $RepoRoot "dist\PygenesisUnreal"
$ZipPath = Join-Path $RepoRoot "dist\PygenesisUnreal-$Version-windows.zip"

if (Test-Path $OutRoot) { Remove-Item $OutRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $OutRoot | Out-Null

function Copy-TreeFiltered {
    param([string]$Source, [string]$Destination)
    if (-not (Test-Path $Source)) { return }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    robocopy $Source $Destination /E /NFL /NDL /NJH /NJS /nc /ns /np `
        /XD __pycache__ .venv node_modules .git `
        /XF *.gguf *.pyc *.log | Out-Null
}

Write-Host "=== Build release Pygenesis Unreal v$Version ===" -ForegroundColor Cyan

Copy-TreeFiltered (Join-Path $RepoRoot "backend") (Join-Path $OutRoot "backend")
Copy-TreeFiltered (Join-Path $RepoRoot "plugin") (Join-Path $OutRoot "plugin")
Copy-TreeFiltered (Join-Path $RepoRoot "installer") (Join-Path $OutRoot "installer")
Copy-TreeFiltered (Join-Path $RepoRoot "middleware") (Join-Path $OutRoot "middleware")

Copy-Item (Join-Path $RepoRoot "Install.bat") (Join-Path $OutRoot "Install.bat") -Force
Copy-Item (Join-Path $RepoRoot "LICENSE") (Join-Path $OutRoot "LICENSE") -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $RepoRoot "README.md") (Join-Path $OutRoot "README.md") -Force

@"
Pygenesis UnrealExpert — paquete de distribución Windows
Version: $Version
Modelo: SuNavar/Pygenesis_Unreal (descarga en instalacion)
Sin Companion: chat en ventana del Unreal Editor.
"@ | Set-Content (Join-Path $OutRoot "PACKAGE.txt") -Encoding UTF8

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $OutRoot "*") -DestinationPath $ZipPath -Force

Write-Host "OK: $OutRoot" -ForegroundColor Green
Write-Host "ZIP: $ZipPath" -ForegroundColor Green
