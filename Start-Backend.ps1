#Requires -Version 5.1
<#
.SYNOPSIS
  Arranca (o reinicia) el puente Pygenesis en http://127.0.0.1:8000
#>
param([switch]$Force)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& "$PSScriptRoot\backend\scripts\start_backend.ps1" -Force:$true
