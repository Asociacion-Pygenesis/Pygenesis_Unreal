# Pygenesis UnrealExpert

Asistente IA local para **Unreal Engine 5** (Blueprints / BP-Lite, iluminación / Lighting-Spec, troubleshooting).

El chat se abre **dentro del Unreal Editor** como ventana del plugin. **No hay Companion.**

El modelo no va en este repositorio. El instalador lo descarga de [SuNavar/Pygenesis-Unreal](https://huggingface.co/SuNavar/Pygenesis-Unreal).

---

## Layout del repo

| Path | Rol |
|------|-----|
| [`backend/`](backend/) | Puente FastAPI + `llama-cpp-python` |
| [`middleware/`](middleware/) | Encoder/decoder BP-Lite + Lighting-Spec |
| [`plugin/`](plugin/) | Plugin Unreal Editor (ventana in-app) |
| [`installer/`](installer/) | Instalador Windows (sin Companion) |
| [`tests/`](tests/) | Pruebas del puente y del grafo |

---

## Quick start (Windows)

Hace falta Python 3.10–3.12 y Unreal Engine 5.7.

```powershell
.\installer\check_environment.ps1
.\installer\install_backend.ps1
.\installer\install_unreal_plugin.ps1 -ProjectPath "C:\Ruta\Al\Proyecto"
```

Abre el `.uproject`, compila si el editor lo pide y usa **Window → Pygenesis Unreal**.

Modelo: **Llama 3.1 8B Instruct**, archivo `pygenesis-unreal-q4km.gguf`.

---

## Privacidad

Inferencia **en tu máquina**. Solo se necesita red para descargar el GGUF la primera vez.

Licencia: [Apache-2.0](LICENSE).
