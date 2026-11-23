# Pygenesis UnrealExpert

[Español](README.md) · [English](README.en.md)

Asistente de IA local para **Unreal Engine 5** (Blueprints / BP-Lite, iluminación / Lighting-Spec y resolución de problemas).

El chat se abre **dentro del Unreal Editor**, como ventana del plugin. **No hay aplicación Companion.**

El modelo no va en este repositorio. El instalador lo descarga de [SuNavar/Pygenesis-Unreal](https://huggingface.co/SuNavar/Pygenesis-Unreal).

---

## Estructura del repositorio

| Ruta | Función |
|------|---------|
| [`backend/`](backend/) | Puente FastAPI + `llama-cpp-python` |
| [`middleware/`](middleware/) | Codificador y decodificador de BP-Lite y Lighting-Spec |
| [`plugin/`](plugin/) | Plugin del Unreal Editor (ventana dentro del editor) |
| [`installer/`](installer/) | Instalador de Windows (sin Companion) |
| [`tests/`](tests/) | Pruebas del puente y del grafo |

---

## Puesta en marcha (Windows)

Hace falta Unreal Engine 5.7. El release de Windows incluye `Install.bat`: abre una ventana que comprueba qué está instalado y qué falta, y lo instala (Python 3.10–3.12, runtime, inferencia Vulkan o CUDA, modelo y plugin).

```powershell
.\Install.bat
```

Abre el `.uproject`, compila si el editor lo pide y entra en **Window → Pygenesis Unreal**.

Release: [v0.1.0](https://github.com/Asociacion-Pygenesis/Pygenesis_Unreal/releases/tag/v0.1.0).

Modelo: **Llama 3.1 8B Instruct**, archivo `pygenesis-unreal-q4km.gguf`.

---

## Privacidad

La inferencia se ejecuta **en tu máquina**. Solo hace falta conexión para descargar el GGUF la primera vez.

Licencia: [Apache-2.0](LICENSE).
