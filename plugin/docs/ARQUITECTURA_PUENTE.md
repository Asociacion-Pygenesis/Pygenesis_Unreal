# Arquitectura: plugin Unreal Editor ↔ puente de inferencia

Mismo patrón que **Pygenesis ResolveExpert / Unity**: el plugin **no** llama al motor LLM directamente.

**Sin Companion.** El chat es una ventana del Unreal Editor.

---

## Capas

```
┌─────────────────────────────────────┐
│  Unreal Editor                      │
│  Plugin PygenesisUnreal (C++/Slate) │
│  Window → Pygenesis Unreal          │
└──────────────┬──────────────────────┘
               │  HTTP  localhost:8000
               │  POST /consultar/stream (SSE)
               │  GET  /health
               ▼
┌─────────────────────────────────────┐
│  Puente de inferencia (backend/)    │
│  FastAPI · UNREAL_SYSTEM · RAG      │
│  llama-cpp-python · GGUF en memoria │
│  response_filters · contexto UE     │
│  + middleware BP-Lite / Lighting    │
└─────────────────────────────────────┘
```

**Sin Ollama en producción.** El puente carga el GGUF con `llama-cpp-python`.

---

## Backend GPU

| GPU detectada | Backend | Instalación |
|---------------|---------|-------------|
| NVIDIA | `cuda` | Wheel CUDA (`install_inference.ps1`) |
| AMD Radeon | `vulkan` | Build con `GGML_VULKAN=on` |
| Ninguna / fallback | `cpu` | Wheel CPU |

Config: `%LOCALAPPDATA%\PygenesisUnreal\bridge.env`

| Variable | Descripción |
|----------|-------------|
| `PYGENESIS_GPU_BACKEND` | `cuda` \| `vulkan` \| `cpu` \| `auto` |
| `PYGENESIS_MODEL_PATH` | Ruta al `.gguf` |
| `PYGENESIS_N_CTX` | Contexto (default 8192) |
| `PYGENESIS_N_GPU_LAYERS` | Capas en GPU (default -1) |

---

## Modelo

- Archivo: `pygenesis-unreal-q4km.gguf`
- Ubicación: `%LOCALAPPDATA%\PygenesisUnreal\models\`
- Repo HF (placeholder): `SuNavar/Pygenesis_Unreal`
- Ver `installer/model.source.json`

---

## API del puente (contrato plugin)

### `GET /health`

```json
{
  "status": "ok",
  "modelo": "pygenesis-unreal",
  "backend": "cuda",
  "model_loaded": true
}
```

### `POST /consultar/stream` (SSE)

```json
{"token": "fragmento"}
{"done": true, "respuesta": "texto limpio final", "fragmentos_usados": 0}
```

### `POST /consultar`

```json
{
  "prompt": "Crea un jump con LaunchCharacter",
  "contexto_proyecto": "Área activa: Blueprints\nNivel: L_Demo",
  "modo_json": false
}
```

El modelo puede devolver **BP-Lite** o **Lighting-Spec** (ver `PlanUnreal.md` y `middleware/`).
