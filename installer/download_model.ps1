#Requires -Version 5.1
<#
  Descarga el GGUF público sin token de Hugging Face.
  Si el archivo ya está en la carpeta de destino y pesa más de 3 GB, no lo vuelve a bajar.
#>

function Test-PygenesisGgufFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    return ((Get-Item -LiteralPath $Path).Length -gt 3GB)
}

function Save-PygenesisGguf {
    param(
        [Parameter(Mandatory = $true)][string]$ModelSourcePath,
        [Parameter(Mandatory = $true)][string]$DestinationDirectory,
        [string]$PythonExe = ""
    )

    if (-not (Test-Path -LiteralPath $ModelSourcePath)) { throw "Falta $ModelSourcePath" }
    $source = Get-Content -LiteralPath $ModelSourcePath -Raw | ConvertFrom-Json
    $fileName = [string]$source.filename
    $repoId = [string]$source.repo_id
    $revision = "main"
    if ($source.PSObject.Properties.Name -contains "revision" -and $source.revision) {
        $revision = [string]$source.revision
    }

    New-Item -ItemType Directory -Force -Path $DestinationDirectory | Out-Null
    $dest = Join-Path $DestinationDirectory $fileName
    $partial = "$dest.partial"
    $url = "https://huggingface.co/$repoId/resolve/$revision/${fileName}?download=true"

    if (Test-PygenesisGgufFile $dest) {
        Write-Host "  Ya estaba: $dest" -ForegroundColor Green
        return $dest
    }
    if (Test-Path -LiteralPath $dest) {
        Write-Host "  El archivo local está incompleto. Se descarga de nuevo." -ForegroundColor Yellow
        Remove-Item -LiteralPath $dest -Force
    }
    if ((Test-Path -LiteralPath $partial) -and ((Get-Item -LiteralPath $partial).Length -lt 1MB)) {
        Remove-Item -LiteralPath $partial -Force
    }

    Write-Host "  Descargando sin token (~4,6 GB). Puede tardar varios minutos." -ForegroundColor DarkGray
    Write-Host "  $url" -ForegroundColor DarkGray

    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        & curl.exe -L --fail --retry 3 --retry-delay 2 -C - `
            -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" `
            --output $partial $url
        if ($LASTEXITCODE -eq 0 -and (Test-PygenesisGgufFile $partial)) {
            Move-Item -LiteralPath $partial -Destination $dest -Force
            Write-Host "  OK  $dest" -ForegroundColor Green
            return $dest
        }
        Write-Host "  La descarga directa no terminó (código $LASTEXITCODE)." -ForegroundColor Yellow
    } else {
        Write-Host "  curl.exe no está disponible." -ForegroundColor Yellow
    }

    if ($PythonExe -and (Test-Path -LiteralPath $PythonExe)) {
        Write-Host "  Reintento con huggingface-hub, sin usar el token guardado." -ForegroundColor DarkGray
        & $PythonExe -m pip install "huggingface-hub>=0.23,<2" --quiet
        if ($LASTEXITCODE -eq 0) {
            $py = @"
import os
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ.pop("HF_TOKEN", None)
os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)
from pathlib import Path
from huggingface_hub import hf_hub_download
dest = Path(r'$DestinationDirectory')
dest.mkdir(parents=True, exist_ok=True)
path = hf_hub_download(
    repo_id=r'$repoId',
    filename=r'$fileName',
    revision=r'$revision',
    local_dir=str(dest),
    token=False,
)
print(path)
"@
            $pyOut = & $PythonExe -c $py 2>&1
            $pyOut | ForEach-Object { Write-Host "  $_" }
            if ($LASTEXITCODE -eq 0 -and (Test-PygenesisGgufFile $dest)) {
                if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
                Write-Host "  OK  $dest" -ForegroundColor Green
                return $dest
            }
        }
    }

    throw @"
Hugging Face no dejó terminar la descarga sin token.
Descarga el archivo en el navegador y guárdalo con este nombre y en esta carpeta:

$dest

Enlace: $url

Cuando el archivo esté ahí, vuelve a lanzar el instalador. Si ya está y pesa más de 3 GB, no lo vuelve a bajar.
"@
}
