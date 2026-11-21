# Instalación — Pygenesis Unreal

Doble clic en `Install.bat`. Se abre una ventana que comprueba qué está instalado y qué falta, y lo instala por pasos:

1. Python 3.10–3.12
2. Runtime e inferencia (Vulkan, CUDA o CPU)
3. Modelo GGUF desde Hugging Face
4. Copia del plugin al `.uproject`

También se puede lanzar cada paso por separado, o pulsar **Instalar lo que falta**.

```powershell
.\installer\setup_window.ps1
```

Datos locales: `%LOCALAPPDATA%\PygenesisUnreal\`

## Build del release de Windows

```powershell
.\installer\build_release.ps1 -Version 0.1.0
```

Empaqueta `backend/`, `plugin/`, `installer/` y `middleware/` en `dist\PygenesisUnreal-0.1.0-windows.zip`. El modelo no va dentro del ZIP.
