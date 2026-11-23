# Pygenesis UnrealExpert

[Español](README.md) · [English](README.en.md)

Local AI assistant for **Unreal Engine 5** (Blueprints / BP-Lite, lighting / Lighting-Spec, and troubleshooting).

The chat opens **inside the Unreal Editor** as a plugin window. **There is no Companion app.**

The model is not stored in this repository. The installer downloads it from [SuNavar/Pygenesis-Unreal](https://huggingface.co/SuNavar/Pygenesis-Unreal).

---

## Repository layout

| Path | Role |
|------|------|
| [`backend/`](backend/) | FastAPI bridge + `llama-cpp-python` |
| [`middleware/`](middleware/) | BP-Lite and Lighting-Spec encoder/decoder |
| [`plugin/`](plugin/) | Unreal Editor plugin (in-editor window) |
| [`installer/`](installer/) | Windows installer (no Companion) |
| [`tests/`](tests/) | Bridge and graph tests |

---

## Quick start (Windows)

Unreal Engine 5.7 is required. The Windows release includes `Install.bat`: it opens a window that checks what is already installed and what is missing, then installs it (Python 3.10–3.12, the runtime, Vulkan or CUDA inference, the model, and the plugin).

```powershell
.\Install.bat
```

Open the `.uproject`, compile if the editor asks, and go to **Window → Pygenesis Unreal**.

Release: [v0.1.0](https://github.com/Asociacion-Pygenesis/Pygenesis_Unreal/releases/tag/v0.1.0).

Model: **Llama 3.1 8B Instruct**, file `pygenesis-unreal-q4km.gguf`.

---

## Privacy

Inference runs **on your machine**. A network connection is only needed to download the GGUF the first time.

License: [Apache-2.0](LICENSE).
