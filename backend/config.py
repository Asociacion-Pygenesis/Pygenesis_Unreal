"""Configuración del puente de inferencia (modelo GGUF y backend GPU)."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_ROOT.parent

MODEL_NAME = "pygenesis-unreal"
MODEL_FILENAME = "pygenesis-unreal-q4km.gguf"

# Llama 3.1 Instruct stop tokens (alineado con PlanUnreal.md).
EOT = "<|" + "eot_id|>"
# Fin de turno: válido en cualquier modalidad.
EOS_SEQUENCES = [
    EOT,
    "<|end_of_text|>",
]
# Cortes de prosa/bucle (Ollama no los tiene; aquí sí). Solo en prosa:
# en JSON un "\n\n{" o una frase así no aparece y el stop solo añade riesgo.
STOP_SEQUENCES = [
    *EOS_SEQUENCES,
    "\nEspero que",
    "\nEl flujo de ejecución",
    "\nPara crear este Blueprint",
    "\nRecuerda que este flujo",
    "\n¿Qué tipo de Blueprint",
    "\nEn resumen",
    "\n\n{",  # segundo JSON = eco
]

# Defaults: n_ctx alineado a Modelfile Ollama (4096); override con PYGENESIS_N_CTX.
N_CTX = int(os.environ.get("PYGENESIS_N_CTX", "4096"))
N_PREDICT = int(os.environ.get("PYGENESIS_N_PREDICT", "384"))
N_GPU_LAYERS = int(os.environ.get("PYGENESIS_N_GPU_LAYERS", "-1"))
N_BATCH = int(os.environ.get("PYGENESIS_N_BATCH", "256"))
N_THREADS = int(os.environ.get("PYGENESIS_N_THREADS", "0"))  # 0 = auto

# Profile jobs BP/Lighting (Modelfile Ollama PARAMETER *)
OLLAMA_BP_TEMPERATURE = float(os.environ.get("PYGENESIS_BP_TEMPERATURE", "0.25"))
OLLAMA_BP_TOP_P = float(os.environ.get("PYGENESIS_BP_TOP_P", "0.9"))
OLLAMA_BP_TOP_K = int(os.environ.get("PYGENESIS_BP_TOP_K", "30"))
# El JSON BP-Lite es repetitivo por diseño ('","name":"","inputs":[' por nodo).
# Con repeat 1.25 / presence 0.4 el 3er o 4º nodo pierde contra el token de fin
# y el grafo sale truncado: estas penalizaciones van casi neutras.
OLLAMA_BP_REPEAT_PENALTY = float(os.environ.get("PYGENESIS_BP_REPEAT_PENALTY", "1.02"))
OLLAMA_BP_PRESENCE_PENALTY = float(os.environ.get("PYGENESIS_BP_PRESENCE_PENALTY", "0.0"))
# Margen para A/D (4 nodos) + continue; override PYGENESIS_BP_MAX_TOKENS
OLLAMA_BP_MAX_TOKENS = int(os.environ.get("PYGENESIS_BP_MAX_TOKENS", "1280"))
OLLAMA_BP_CONTINUE_TOKENS = int(os.environ.get("PYGENESIS_BP_CONTINUE_TOKENS", "512"))


def pygenesis_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if local:
        return Path(local) / "PygenesisUnreal"
    return REPO_ROOT / ".pygenesis-unreal"


def default_model_dir() -> Path:
    return pygenesis_data_dir() / "models"


def resolve_model_path() -> Path:
    env = os.environ.get("PYGENESIS_MODEL_PATH", "").strip()
    if env:
        return Path(env)

    candidates = [
        default_model_dir() / MODEL_FILENAME,
        REPO_ROOT / MODEL_FILENAME,
    ]
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def gpu_backend() -> str:
    """cuda | vulkan | cpu (auto detecta NVIDIA → cuda, AMD → vulkan, si no cpu)."""
    backend = os.environ.get("PYGENESIS_GPU_BACKEND", "auto").strip().lower()
    if backend in {"cuda", "vulkan", "cpu"}:
        return backend
    return _detect_gpu_backend()


def _detect_gpu_backend() -> str:
    if _has_nvidia_gpu():
        return "cuda"
    if _has_amd_gpu():
        return "vulkan"
    return "cpu"


def _has_nvidia_gpu() -> bool:
    import shutil
    import subprocess

    if not shutil.which("nvidia-smi"):
        return False
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


def _has_amd_gpu() -> bool:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}",
        ) as key:
            index = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, index)
                    with winreg.OpenKey(key, subkey_name) as subkey:
                        try:
                            provider = winreg.QueryValueEx(subkey, "ProviderName")[0]
                            if provider and "AMD" in str(provider).upper():
                                return True
                        except OSError:
                            pass
                        try:
                            name = winreg.QueryValueEx(subkey, "DriverDesc")[0]
                            if name and ("AMD" in str(name).upper() or "RADEON" in str(name).upper()):
                                return True
                        except OSError:
                            pass
                    index += 1
                except OSError:
                    break
    except OSError:
        pass
    return False
