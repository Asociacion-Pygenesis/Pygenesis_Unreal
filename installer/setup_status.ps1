#Requires -Version 5.1
<#
.SYNOPSIS
  Estado de la instalación de Pygenesis Unreal, para la ventana de Setup.
#>
param(
    [string]$ProjectPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-PygenesisPythonCandidates {
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
    return @($found)
}

function Get-PygenesisVideoAdapters {
    try {
        return @(Get-CimInstance Win32_VideoController -ErrorAction Stop | Where-Object {
            $_.Name -and $_.Name -notmatch "Microsoft Basic"
        })
    } catch {
        return @()
    }
}

function Get-BridgeValue {
    param([string]$Name)
    $path = Join-Path $env:LOCALAPPDATA "PygenesisUnreal\bridge.env"
    if (-not (Test-Path $path)) { return "" }
    foreach ($line in @(Get-Content $path)) {
        if ($line -match "^\s*$([regex]::Escape($Name))\s*=\s*(.*)$") {
            return $Matches[1].Trim()
        }
    }
    return ""
}

function Find-UnrealProjectFiles {
    $roots = @(
        (Join-Path $env:USERPROFILE "Documents\Unreal Projects"),
        (Join-Path $env:USERPROFILE "Documents\UnrealProjects")
    )
    $found = @()
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $found += @(Get-ChildItem -Path $root -Filter "*.uproject" -File -Recurse -Depth 2 -ErrorAction SilentlyContinue)
    }
    return @($found)
}

function New-SetupCheck {
    param([string]$Id, [string]$Label, [string]$Detail, [ValidateSet("Ok", "Warning", "Critical")][string]$Severity)
    [PSCustomObject]@{
        Id       = $Id
        Label    = $Label
        Detail   = $Detail
        Severity = $Severity
    }
}

function Get-PygenesisSetupStatus {
    param([string]$ProjectPath = "")

    $checks = New-Object System.Collections.Generic.List[object]
    $pygenesisHome = Join-Path $env:LOCALAPPDATA "PygenesisUnreal"
    $runtimePython = Join-Path $pygenesisHome "runtime\Scripts\python.exe"

    $pythons = @(Get-PygenesisPythonCandidates)
    $usable = @($pythons | Where-Object { $_.Usable }) | Select-Object -First 1
    if ($usable) {
        $checks.Add((New-SetupCheck "python" "Python 3.10–3.12" "$($usable.Version)  $($usable.Exe)" "Ok"))
    } else {
        $checks.Add((New-SetupCheck "python" "Python 3.10–3.12" "No está. El paso 1 lo instala con winget." "Critical"))
    }

    $adapters = @(Get-PygenesisVideoAdapters)
    $gpuName = if ($adapters.Count -gt 0) { $adapters[0].Name } else { "sin GPU listada" }
    $nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    $cudaName = ""
    if ($nvidia) {
        try {
            $cudaName = (& nvidia-smi --query-gpu=name --format=csv,noheader 2>$null | Select-Object -First 1)
            if ($cudaName) { $cudaName = $cudaName.Trim() }
        } catch { $cudaName = "" }
    }
    $vulkan = Test-Path (Join-Path $env:SystemRoot "System32\vulkan-1.dll")
    $backend = "cpu"
    if ($cudaName) { $backend = "cuda" }
    elseif ($vulkan -and $adapters.Count -gt 0) { $backend = "vulkan" }

    if ($backend -eq "cuda") {
        $checks.Add((New-SetupCheck "gpu" "GPU" "$gpuName. CUDA disponible." "Ok"))
    } elseif ($backend -eq "vulkan") {
        $checks.Add((New-SetupCheck "gpu" "GPU" "$gpuName. Vulkan disponible." "Ok"))
    } else {
        $checks.Add((New-SetupCheck "gpu" "GPU" "$gpuName. Sin CUDA ni Vulkan: la inferencia irá por CPU." "Warning"))
    }

    if (Test-Path $runtimePython) {
        $checks.Add((New-SetupCheck "runtime" "Runtime Python" $runtimePython "Ok"))
        $importOk = $false
        $importText = ""
        try {
            $importText = & $runtimePython -c "import llama_cpp; print(getattr(llama_cpp, '__version__', 'ok'))" 2>&1
            $importOk = ($LASTEXITCODE -eq 0)
        } catch {
            $importOk = $false
        }
        if ($importOk) {
            $checks.Add((New-SetupCheck "inference" "Inferencia llama-cpp" ("versión " + ($importText | Select-Object -Last 1)) "Ok"))
        } else {
            $checks.Add((New-SetupCheck "inference" "Inferencia llama-cpp" "El runtime está, y falta el wheel de llama-cpp-python." "Critical"))
        }
    } else {
        $checks.Add((New-SetupCheck "runtime" "Runtime Python" "Aún no existe en $pygenesisHome\runtime" "Critical"))
        $checks.Add((New-SetupCheck "inference" "Inferencia llama-cpp" "Se instala con el runtime." "Warning"))
    }

    $modelSource = Join-Path $PSScriptRoot "model.source.json"
    $fileName = "pygenesis-unreal-q4km.gguf"
    if (Test-Path $modelSource) {
        $source = Get-Content $modelSource -Raw | ConvertFrom-Json
        if ($source.filename) { $fileName = [string]$source.filename }
    }
    $modelPath = Join-Path $pygenesisHome "models\$fileName"
    if (Test-Path $modelPath) {
        $gb = [math]::Round((Get-Item $modelPath).Length / 1GB, 2)
        $checks.Add((New-SetupCheck "model" "Modelo GGUF" "$fileName ($gb GB)" "Ok"))
    } else {
        $checks.Add((New-SetupCheck "model" "Modelo GGUF" "No está. Se descarga de Hugging Face (~4,6 GB)." "Critical"))
    }

    $project = $ProjectPath
    if ([string]::IsNullOrWhiteSpace($project)) {
        $project = Get-BridgeValue "PYGENESIS_UPROJECT"
    }
    if ([string]::IsNullOrWhiteSpace($project)) {
        $projects = @(Find-UnrealProjectFiles)
        if ($projects.Count -eq 1) { $project = $projects[0].FullName }
    }

    if ([string]::IsNullOrWhiteSpace($project)) {
        $checks.Add((New-SetupCheck "plugin" "Plugin de Unreal" "Elige un .uproject. Hay cero o varios en Documentos." "Warning"))
    } else {
        $projectDir = $project
        if ($project -like "*.uproject") { $projectDir = Split-Path $project -Parent }
        $pluginFile = Join-Path $projectDir "Plugins\PygenesisUnreal\PygenesisUnreal.uplugin"
        if (Test-Path $pluginFile) {
            $checks.Add((New-SetupCheck "plugin" "Plugin de Unreal" $pluginFile "Ok"))
        } elseif (Test-Path $project) {
            $checks.Add((New-SetupCheck "plugin" "Plugin de Unreal" "El proyecto está y el plugin no se ha copiado." "Critical"))
        } else {
            $checks.Add((New-SetupCheck "plugin" "Plugin de Unreal" "No se encuentra el proyecto: $project" "Critical"))
        }
    }

    $pythonExe = ""
    if ($null -ne $usable -and $usable.Exe) { $pythonExe = [string]$usable.Exe }
    [PSCustomObject]@{
        Backend     = $backend
        ProjectPath = [string]$project
        PythonExe   = $pythonExe
        Checks      = @($checks.ToArray())
    }
}

if ($MyInvocation.InvocationName -ne ".") {
    Get-PygenesisSetupStatus -ProjectPath $ProjectPath | ConvertTo-Json -Depth 5
}
