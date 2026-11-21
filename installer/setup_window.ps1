#Requires -Version 5.1
<#
.SYNOPSIS
  Ventana de instalación de Pygenesis Unreal. Muestra qué está y qué falta, e instala por pasos.
#>
param(
    [switch]$Smoke
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$InstallerRoot = $PSScriptRoot
. (Join-Path $InstallerRoot "setup_status.ps1")

$script:ProjectPath = ""
$script:Busy = $false
$script:LogCursor = 0
$sync = [hashtable]::Synchronized(@{
    Lines = New-Object System.Collections.Generic.List[string]
    Done  = $false
    Ok    = $true
    Error = ""
})

function New-Font {
    param([int]$Size = 9, [System.Drawing.FontStyle]$Style = "Regular")
    New-Object System.Drawing.Font("Segoe UI", $Size, $Style)
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Pygenesis Unreal — Setup"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(760, 720)
$form.MinimumSize = New-Object System.Drawing.Size(680, 620)
$form.BackColor = [System.Drawing.Color]::FromArgb(244, 245, 247)
$form.Font = New-Font 9

$title = New-Object System.Windows.Forms.Label
$title.Text = "Pygenesis Unreal"
$title.Font = New-Font 16 "Bold"
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(16, 12)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = "Comprueba qué está instalado y qué falta, y lo instala paso a paso."
$subtitle.AutoSize = $true
$subtitle.Location = New-Object System.Drawing.Point(18, 42)
$subtitle.ForeColor = [System.Drawing.Color]::FromArgb(70, 74, 82)

$banner = New-Object System.Windows.Forms.Label
$banner.Font = New-Font 11 "Bold"
$banner.AutoSize = $false
$banner.Location = New-Object System.Drawing.Point(16, 68)
$banner.Size = New-Object System.Drawing.Size(710, 24)

$gpuLabel = New-Object System.Windows.Forms.Label
$gpuLabel.Text = "Aceleración"
$gpuLabel.AutoSize = $true
$gpuLabel.Location = New-Object System.Drawing.Point(16, 100)

$gpuBox = New-Object System.Windows.Forms.ComboBox
$gpuBox.DropDownStyle = "DropDownList"
[void]$gpuBox.Items.AddRange(@("Vulkan (AMD / Intel)", "CUDA (NVIDIA)", "CPU"))
$gpuBox.Location = New-Object System.Drawing.Point(110, 96)
$gpuBox.Width = 220

$modelBox = New-Object System.Windows.Forms.CheckBox
$modelBox.Text = "Incluir el modelo GGUF (~4,6 GB desde Hugging Face)"
$modelBox.Checked = $true
$modelBox.AutoSize = $true
$modelBox.Location = New-Object System.Drawing.Point(350, 98)

$projectLabel = New-Object System.Windows.Forms.Label
$projectLabel.Text = "Proyecto"
$projectLabel.AutoSize = $true
$projectLabel.Location = New-Object System.Drawing.Point(16, 132)

$projectBox = New-Object System.Windows.Forms.TextBox
$projectBox.Location = New-Object System.Drawing.Point(110, 128)
$projectBox.Width = 500

$browse = New-Object System.Windows.Forms.Button
$browse.Text = "Examinar"
$browse.Location = New-Object System.Drawing.Point(620, 126)
$browse.Width = 100
$browse.Height = 26

$installAll = New-Object System.Windows.Forms.Button
$installAll.Text = "Instalar lo que falta"
$installAll.Font = New-Font 10 "Bold"
$installAll.Location = New-Object System.Drawing.Point(16, 164)
$installAll.Size = New-Object System.Drawing.Size(220, 36)

$recheck = New-Object System.Windows.Forms.Button
$recheck.Text = "Volver a comprobar"
$recheck.Location = New-Object System.Drawing.Point(246, 164)
$recheck.Size = New-Object System.Drawing.Size(160, 36)

$stepPython = New-Object System.Windows.Forms.Button
$stepPython.Text = "1. Python"
$stepPython.Location = New-Object System.Drawing.Point(16, 210)
$stepPython.Size = New-Object System.Drawing.Size(170, 28)

$stepRuntime = New-Object System.Windows.Forms.Button
$stepRuntime.Text = "2. Runtime e inferencia"
$stepRuntime.Location = New-Object System.Drawing.Point(196, 210)
$stepRuntime.Size = New-Object System.Drawing.Size(170, 28)

$stepModel = New-Object System.Windows.Forms.Button
$stepModel.Text = "3. Modelo"
$stepModel.Location = New-Object System.Drawing.Point(376, 210)
$stepModel.Size = New-Object System.Drawing.Size(170, 28)

$stepPlugin = New-Object System.Windows.Forms.Button
$stepPlugin.Text = "4. Plugin"
$stepPlugin.Location = New-Object System.Drawing.Point(556, 210)
$stepPlugin.Size = New-Object System.Drawing.Size(164, 28)

$checkTitle = New-Object System.Windows.Forms.Label
$checkTitle.Text = "Estado"
$checkTitle.Font = New-Font 10 "Bold"
$checkTitle.AutoSize = $true
$checkTitle.Location = New-Object System.Drawing.Point(16, 248)

$checkPanel = New-Object System.Windows.Forms.Panel
$checkPanel.Location = New-Object System.Drawing.Point(16, 272)
$checkPanel.Size = New-Object System.Drawing.Size(710, 168)
$checkPanel.AutoScroll = $true
$checkPanel.BackColor = [System.Drawing.Color]::White
$checkPanel.BorderStyle = "FixedSingle"

$logTitle = New-Object System.Windows.Forms.Label
$logTitle.Text = "Registro"
$logTitle.Font = New-Font 10 "Bold"
$logTitle.AutoSize = $true
$logTitle.Location = New-Object System.Drawing.Point(16, 448)

$logBox = New-Object System.Windows.Forms.TextBox
$logBox.Multiline = $true
$logBox.ReadOnly = $true
$logBox.ScrollBars = "Vertical"
$logBox.Font = New-Object System.Drawing.Font("Consolas", 9)
$logBox.Location = New-Object System.Drawing.Point(16, 472)
$logBox.Size = New-Object System.Drawing.Size(710, 180)

$form.Controls.AddRange(@(
    $title, $subtitle, $banner, $gpuLabel, $gpuBox, $modelBox,
    $projectLabel, $projectBox, $browse,
    $installAll, $recheck, $stepPython, $stepRuntime, $stepModel, $stepPlugin,
    $checkTitle, $checkPanel, $logTitle, $logBox
))

function Get-SelectedBackend {
    switch ($gpuBox.SelectedIndex) {
        1 { return "cuda" }
        2 { return "cpu" }
        default { return "vulkan" }
    }
}

function Set-BackendIndex {
    param([string]$Backend)
    switch ($Backend) {
        "cuda" { $gpuBox.SelectedIndex = 1 }
        "cpu" { $gpuBox.SelectedIndex = 2 }
        default { $gpuBox.SelectedIndex = 0 }
    }
}

function Update-Banner {
    param($Status)
    $critical = @($Status.Checks | Where-Object { $_.Severity -eq "Critical" })
    if ($critical.Count -eq 0) {
        $banner.Text = "Listo para abrir Unreal y usar Window → Pygenesis Unreal."
        $banner.ForeColor = [System.Drawing.Color]::FromArgb(31, 138, 59)
    } else {
        $banner.Text = "Faltan $($critical.Count) pieza(s). Pulsa «Instalar lo que falta»."
        $banner.ForeColor = [System.Drawing.Color]::FromArgb(180, 90, 20)
    }
}

function Update-Checklist {
    param($Status)
    $checkPanel.Controls.Clear()
    $y = 8
    foreach ($check in @($Status.Checks)) {
        $color = switch ($check.Severity) {
            "Ok" { [System.Drawing.Color]::FromArgb(31, 138, 59) }
            "Warning" { [System.Drawing.Color]::FromArgb(168, 104, 16) }
            default { [System.Drawing.Color]::FromArgb(180, 40, 40) }
        }
        $mark = switch ($check.Severity) {
            "Ok" { "OK" }
            "Warning" { "Aviso" }
            default { "Falta" }
        }
        $row = New-Object System.Windows.Forms.Label
        $row.Text = "$mark   $($check.Label) — $($check.Detail)"
        $row.ForeColor = $color
        $row.Font = New-Font 9
        $row.AutoSize = $false
        $row.Location = New-Object System.Drawing.Point(8, $y)
        $row.Size = New-Object System.Drawing.Size(670, 22)
        $checkPanel.Controls.Add($row)
        $y += 24
    }
    Update-Banner $Status
}

function Refresh-Status {
    $script:ProjectPath = $projectBox.Text.Trim()
    $status = Get-PygenesisSetupStatus -ProjectPath $script:ProjectPath
    if ([string]::IsNullOrWhiteSpace($projectBox.Text) -and $status.ProjectPath) {
        $projectBox.Text = [string]$status.ProjectPath
        $script:ProjectPath = $projectBox.Text.Trim()
    }
    if ($gpuBox.SelectedIndex -lt 0) {
        Set-BackendIndex $status.Backend
    }
    Update-Checklist $status
    return $status
}

function Set-Busy {
    param([bool]$Busy)
    $script:Busy = $Busy
    foreach ($control in @($installAll, $recheck, $stepPython, $stepRuntime, $stepModel, $stepPlugin, $browse, $gpuBox, $modelBox)) {
        $control.Enabled = -not $Busy
    }
    $form.Cursor = if ($Busy) { [System.Windows.Forms.Cursors]::WaitCursor } else { [System.Windows.Forms.Cursors]::Default }
}

function Add-Log {
    param([string]$Line)
    if ([string]::IsNullOrWhiteSpace($Line)) { return }
    $logBox.AppendText($Line.TrimEnd() + [Environment]::NewLine)
}

function Start-InstallJob {
    param([string]$Kind)

    if ($script:Busy) { return }
    Set-Busy $true
    $sync.Done = $false
    $sync.Ok = $true
    $sync.Error = ""
    $sync.Lines.Clear()
    $script:LogCursor = 0
    $backend = Get-SelectedBackend
    $project = $projectBox.Text.Trim()
    $includeModel = [bool]$modelBox.Checked
    Add-Log "— $Kind"

    $runspace = [runspacefactory]::CreateRunspace()
    $runspace.Open()
    $ps = [powershell]::Create()
    $ps.Runspace = $runspace
    [void]$ps.AddScript({
        param($Sync, $Kind, $Backend, $Project, $IncludeModel, $Root)
        function Write-Host {
            param($Object, $ForegroundColor, $NoNewline, $Separator, $BackgroundColor)
            if ($null -ne $Object) { $Sync.Lines.Add([string]$Object) }
        }
        try {
            switch ($Kind) {
                "python" {
                    $winget = Get-Command winget -ErrorAction SilentlyContinue
                    if (-not $winget) { throw "winget no está disponible. Instala Python 3.12 desde https://www.python.org/downloads/" }
                    & winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
                    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) {
                        throw "winget terminó con código $LASTEXITCODE"
                    }
                    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
                    $user = [Environment]::GetEnvironmentVariable("Path", "User")
                    $env:Path = "$machine;$user"
                    $Sync.Lines.Add("Python 3.12 instalado. Vuelve a comprobar.")
                }
                "runtime" {
                    $args = @{ Backend = $Backend }
                    if (-not $IncludeModel) { $args.SkipModel = $true }
                    & (Join-Path $Root "install_backend.ps1") @args
                    if (-not $?) { throw "El runtime no se instaló." }
                }
                "model" {
                    & (Join-Path $Root "install_backend.ps1") -ModelOnly -Backend $Backend
                    if (-not $?) { throw "El modelo no se descargó." }
                }
                "plugin" {
                    if ([string]::IsNullOrWhiteSpace($Project)) {
                        throw "Elige un .uproject antes de copiar el plugin."
                    }
                    & (Join-Path $Root "install_unreal_plugin.ps1") -ProjectPath $Project
                    if (-not $?) { throw "El plugin no se copió." }
                }
                "all" {
                    $py = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
                    if ($LASTEXITCODE -ne 0 -or -not $py) {
                        $winget = Get-Command winget -ErrorAction SilentlyContinue
                        if (-not $winget) { throw "Falta Python 3.12 y winget no está disponible." }
                        & winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
                        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) {
                            throw "winget terminó con código $LASTEXITCODE"
                        }
                        $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
                        $user = [Environment]::GetEnvironmentVariable("Path", "User")
                        $env:Path = "$machine;$user"
                    }
                    $runtimeArgs = @{ Backend = $Backend }
                    if (-not $IncludeModel) { $runtimeArgs.SkipModel = $true }
                    & (Join-Path $Root "install_backend.ps1") @runtimeArgs
                    if (-not $?) { throw "El runtime no se instaló." }
                    if ([string]::IsNullOrWhiteSpace($Project)) {
                        $Sync.Lines.Add("Runtime listo. Falta elegir el .uproject para copiar el plugin.")
                    } else {
                        & (Join-Path $Root "install_unreal_plugin.ps1") -ProjectPath $Project
                        if (-not $?) { throw "El plugin no se copió." }
                    }
                }
            }
        } catch {
            $Sync.Ok = $false
            $Sync.Error = $_.Exception.Message
            $Sync.Lines.Add($_.Exception.Message)
        } finally {
            $Sync.Done = $true
        }
    }).AddArgument($sync).AddArgument($Kind).AddArgument($backend).AddArgument($project).AddArgument($includeModel).AddArgument($InstallerRoot)
    $script:Job = $ps
    $script:Runspace = $runspace
    [void]$ps.BeginInvoke()
}

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 200
$timer.Add_Tick({
    while ($script:LogCursor -lt $sync.Lines.Count) {
        Add-Log $sync.Lines[$script:LogCursor]
        $script:LogCursor++
    }
    if ($sync.Done -and $script:Busy) {
        $timer.Stop()
        Set-Busy $false
        if ($sync.Ok) { Add-Log "Paso terminado." } else { Add-Log "Paso interrumpido." }
        try { Refresh-Status | Out-Null } catch { Add-Log $_.Exception.Message }
        if ($script:Job) { $script:Job.Dispose(); $script:Job = $null }
        if ($script:Runspace) { $script:Runspace.Close(); $script:Runspace.Dispose(); $script:Runspace = $null }
    }
})

$browse.Add_Click({
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Filter = "Proyecto Unreal (*.uproject)|*.uproject"
    $dialog.Title = "Elige el proyecto de Unreal"
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $projectBox.Text = $dialog.FileName
        Refresh-Status | Out-Null
    }
})

$recheck.Add_Click({ Refresh-Status | Out-Null })
$installAll.Add_Click({ $timer.Start(); Start-InstallJob "all" })
$stepPython.Add_Click({ $timer.Start(); Start-InstallJob "python" })
$stepRuntime.Add_Click({ $timer.Start(); Start-InstallJob "runtime" })
$stepModel.Add_Click({ $timer.Start(); Start-InstallJob "model" })
$stepPlugin.Add_Click({ $timer.Start(); Start-InstallJob "plugin" })

$form.Add_Shown({ Refresh-Status | Out-Null })
$form.Add_FormClosed({ $timer.Stop() })

if ($Smoke) {
    Refresh-Status | Out-Null
    if ($checkPanel.Controls.Count -lt 6) { throw "La lista de estado no se ha rellenado." }
    Write-Host "Ventana OK: $($checkPanel.Controls.Count) filas."
    Write-Host $banner.Text
    return
}

[void]$form.ShowDialog()
