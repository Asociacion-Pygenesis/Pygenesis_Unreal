# Instalación — Pygenesis UnrealExpert

Instalador Windows **sin Companion**. El chat se abre dentro de Unreal Editor.

## Requisitos

- Windows 10/11
- Python 3.10–3.12 en PATH (recomendado 3.12)
- Internet (primera descarga del GGUF)
- Unreal Engine 5 (para el plugin)

## Uso

```powershell
.\Install.bat
# o
.\installer\install_pygenesis.ps1 -UseLocalModel -ProjectPath "C:\Users\navar\Documents\Unreal Projects\PygenUnrealSandbox"
.\installer\install_pygenesis.ps1 -SkipModelDownload -SkipPlugin
```

Pasos del instalador:

1. Runtime + `llama-cpp-python` (CUDA/Vulkan/CPU)
2. Modelo GGUF: `-UseLocalModel` (copia desde el repo) o descarga HF (`model.source.json`)
3. Copia el plugin al proyecto Unreal (`-ProjectPath`)
4. Atajo menú Inicio → **Pygenesis Unreal Backend**

Datos locales: `%LOCALAPPDATA%\PygenesisUnreal\`

## Build release (sin Electron)

```powershell
.\installer\build_release.ps1 -Version 0.1.0
```

Empaqueta `backend/`, `plugin/`, `installer/`, `middleware/` en `dist/PygenesisUnreal/`.
