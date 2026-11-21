# Plugin Unreal Editor — Pygenesis Unreal

El chat **vive dentro de Unreal Editor** (ventana Nomad). No hay Companion.

## Arquitectura

```
Unreal Editor (plugin C++ / Slate)
        │  HTTP  localhost:8000
        ▼
backend/  (FastAPI + llama-cpp-python + GGUF)
```

Ver [`docs/ARQUITECTURA_PUENTE.md`](docs/ARQUITECTURA_PUENTE.md).

## Estado

| Pieza | Estado |
|-------|--------|
| `PygenesisUnreal.uplugin` | Editor module (UE 5.7) |
| Ventana chat Slate | `Window → Pygenesis Unreal` |
| Cliente HTTP | `/health` + jobs async + `/aplicar/bp-lite` + `/aplicar/lighting-spec` |
| Aplicar BP-Lite | Botón crea Blueprint en `/Game/Pygenesis` (nodos K2 básicos) |
| Aplicar Lighting | Botón aplica Lighting-Spec al nivel (sol/sky/fog/post-process) |

## Instalación en un proyecto

```powershell
Set-Location plugin\scripts
.\install_plugin.ps1 -ProjectPath "C:\Users\navar\Documents\Unreal Projects\PygenUnrealSandbox" -Force
```

Sandbox de desarrollo: **UE 5.7.4** — `PygenUnrealSandbox.uproject`.

Después: abre el `.uproject`, compila el plugin cuando Unreal lo pida.

## Uso

1. Arranca el puente: `backend\start_backend.ps1` (GGUF en `%LOCALAPPDATA%\PygenesisUnreal\models\`)
2. En el Editor: **Window → Pygenesis Unreal**
3. Pulsa **Health**, luego envía una pregunta
