"""Motor de inferencia local con llama-cpp-python (GGUF, sin Ollama)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from config import (
    EOS_SEQUENCES,
    MODEL_NAME,
    N_BATCH,
    N_CTX,
    N_GPU_LAYERS,
    N_PREDICT,
    N_THREADS,
    OLLAMA_BP_MAX_TOKENS,
    OLLAMA_BP_PRESENCE_PENALTY,
    OLLAMA_BP_REPEAT_PENALTY,
    OLLAMA_BP_TEMPERATURE,
    OLLAMA_BP_TOP_K,
    OLLAMA_BP_TOP_P,
    STOP_SEQUENCES,
    gpu_backend,
    resolve_model_path,
)

_lock = threading.Lock()
_llm: Any | None = None
_status: dict[str, Any] = {
    "loaded": False,
    "backend": None,
    "model_path": None,
    "error": None,
}
# Si el GBNF provoca AV una vez, no reintentar grammar en este proceso.
_grammar_disabled_runtime = False


@dataclass
class GenerationOptions:
    temperature: float = 0.2
    top_p: float = 0.95
    top_k: int = 20
    repeat_penalty: float = 1.05
    presence_penalty: float = 0.0
    max_tokens: int = N_PREDICT
    use_bp_grammar: bool = False


def _ollama_bp_options(*, use_bp_grammar: bool = False) -> GenerationOptions:
    """Sampling alineado al Modelfile de Ollama (jobs BP/Lighting JSON)."""
    return GenerationOptions(
        temperature=OLLAMA_BP_TEMPERATURE,
        top_p=OLLAMA_BP_TOP_P,
        top_k=OLLAMA_BP_TOP_K,
        repeat_penalty=OLLAMA_BP_REPEAT_PENALTY,
        presence_penalty=OLLAMA_BP_PRESENCE_PENALTY,
        max_tokens=OLLAMA_BP_MAX_TOKENS,
        use_bp_grammar=use_bp_grammar,
    )


def _stops_for(*, json_mode: bool) -> list[str]:
    """En JSON solo cortar por fin de turno: los stops de prosa no aplican."""
    return list(EOS_SEQUENCES) if json_mode else list(STOP_SEQUENCES)


def _llama_kwargs(model_path: str, backend: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model_path": model_path,
        "n_ctx": N_CTX,
        "n_batch": N_BATCH,
        "verbose": False,
    }
    if N_THREADS > 0:
        kwargs["n_threads"] = N_THREADS
    if backend in {"cuda", "vulkan"}:
        kwargs["n_gpu_layers"] = N_GPU_LAYERS
    else:
        kwargs["n_gpu_layers"] = 0
    return kwargs


def load_model(*, force: bool = False) -> None:
    global _llm

    with _lock:
        if _llm is not None and not force:
            return

        backend = gpu_backend()
        model_path = resolve_model_path()
        _status.update(
            {
                "loaded": False,
                "backend": backend,
                "model_path": str(model_path),
                "error": None,
            }
        )

        if not model_path.is_file():
            _status["error"] = f"Modelo no encontrado: {model_path}"
            _llm = None
            return

        try:
            from llama_cpp import Llama
        except ImportError as exc:
            _status["error"] = (
                "llama-cpp-python no instalado. Ejecuta backend/scripts/install_inference.ps1"
            )
            _llm = None
            raise RuntimeError(_status["error"]) from exc

        print(f"Cargando modelo ({backend}): {model_path}")
        _llm = Llama(**_llama_kwargs(str(model_path), backend))
        _status["loaded"] = True
        print(f"Modelo listo: {MODEL_NAME} [{backend}]")


def unload_model() -> None:
    global _llm
    with _lock:
        _llm = None
        _status["loaded"] = False


def get_status() -> dict[str, Any]:
    return {
        "modelo": MODEL_NAME,
        "loaded": _status["loaded"],
        "backend": _status["backend"] or gpu_backend(),
        "model_path": _status["model_path"] or str(resolve_model_path()),
        "error": _status["error"],
        "grammar_disabled": _grammar_disabled_runtime,
    }


def _require_llm() -> Any:
    if _llm is None:
        load_model()
    if _llm is None:
        raise RuntimeError(_status.get("error") or "Modelo no cargado")
    return _llm


def _resolve_grammar(*, use_bp_grammar: bool) -> Any | None:
    global _grammar_disabled_runtime
    if not use_bp_grammar or _grammar_disabled_runtime:
        return None
    try:
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from middleware.bp_grammar import get_bp_lite_grammar

        return get_bp_lite_grammar(verbose=False)
    except Exception as exc:  # noqa: BLE001
        print(f"[inference] GBNF BP-Lite no disponible, sin grammar: {exc}")
        return None


def _is_grammar_crash(exc: BaseException) -> bool:
    # En Windows el AV nativo de llama.cpp llega como OSError sin mensaje fiable;
    # un falso positivo solo cuesta perder el GBNF (opcional) en este proceso.
    if isinstance(exc, OSError):
        return True
    msg = str(exc).lower()
    return (
        "access violation" in msg
        or "null pointer" in msg
        or "segmentation" in msg
    )


def _call_llm(
    llm: Any,
    prompt: str,
    *,
    tokens: int,
    temperature: float,
    top_p: float,
    top_k: int,
    repeat_penalty: float,
    grammar: Any | None,
    stream: bool,
    presence_penalty: float = 0.0,
    json_mode: bool = False,
) -> Any:
    stops = None if grammar is not None else _stops_for(json_mode=json_mode)
    kwargs: dict[str, Any] = {
        "max_tokens": tokens,
        "temperature": temperature,
        "top_p": top_p,
        "top_k": top_k,
        "repeat_penalty": repeat_penalty,
        "echo": False,
        "stream": stream,
    }
    if presence_penalty and presence_penalty > 0:
        kwargs["presence_penalty"] = presence_penalty
    if stops is not None:
        kwargs["stop"] = stops
    if grammar is not None:
        kwargs["grammar"] = grammar
    try:
        return llm(prompt, **kwargs)
    except TypeError:
        # Builds antiguos de llama-cpp sin presence_penalty
        kwargs.pop("presence_penalty", None)
        return llm(prompt, **kwargs)


def generate(
    prompt: str,
    *,
    modo_json: bool = False,
    max_tokens: int | None = None,
    use_bp_grammar: bool = False,
    repeat_penalty: float | None = None,
    presence_penalty: float | None = None,
) -> str:
    global _grammar_disabled_runtime
    llm = _require_llm()
    if modo_json or use_bp_grammar:
        opts = _ollama_bp_options(use_bp_grammar=use_bp_grammar)
    else:
        opts = GenerationOptions(use_bp_grammar=use_bp_grammar)
    tokens = max_tokens if max_tokens is not None else opts.max_tokens
    grammar = _resolve_grammar(use_bp_grammar=use_bp_grammar)
    penalty = repeat_penalty if repeat_penalty is not None else opts.repeat_penalty
    presence = (
        presence_penalty if presence_penalty is not None else opts.presence_penalty
    )
    json_mode = modo_json or use_bp_grammar

    with _lock:
        try:
            result = _call_llm(
                llm,
                prompt,
                tokens=tokens,
                temperature=opts.temperature,
                top_p=opts.top_p,
                top_k=opts.top_k,
                repeat_penalty=penalty,
                presence_penalty=presence,
                grammar=grammar,
                stream=False,
                json_mode=json_mode,
            )
        except Exception as exc:  # noqa: BLE001
            if grammar is not None and _is_grammar_crash(exc):
                print(f"[inference] grammar AV → reintento sin GBNF: {exc}")
                _grammar_disabled_runtime = True
                result = _call_llm(
                    llm,
                    prompt,
                    tokens=tokens,
                    temperature=opts.temperature,
                    top_p=opts.top_p,
                    top_k=opts.top_k,
                    repeat_penalty=penalty,
                    presence_penalty=presence,
                    grammar=None,
                    stream=False,
                    json_mode=json_mode,
                )
            else:
                raise

    return result["choices"][0]["text"]


def generate_stream(
    prompt: str,
    *,
    modo_json: bool = False,
    max_tokens: int | None = None,
    use_bp_grammar: bool = False,
) -> Iterator[str]:
    global _grammar_disabled_runtime
    llm = _require_llm()
    if modo_json or use_bp_grammar:
        opts = _ollama_bp_options(use_bp_grammar=use_bp_grammar)
    else:
        opts = GenerationOptions(use_bp_grammar=use_bp_grammar)
    tokens = max_tokens if max_tokens is not None else opts.max_tokens
    grammar = _resolve_grammar(use_bp_grammar=use_bp_grammar)
    penalty = opts.repeat_penalty
    json_mode = modo_json or use_bp_grammar

    def _iter(g: Any | None) -> Iterator[str]:
        with _lock:
            stream = _call_llm(
                llm,
                prompt,
                tokens=tokens,
                temperature=opts.temperature,
                top_p=opts.top_p,
                top_k=opts.top_k,
                repeat_penalty=penalty,
                presence_penalty=opts.presence_penalty,
                grammar=g,
                stream=True,
                json_mode=json_mode,
            )
            for chunk in stream:
                token = chunk["choices"][0]["text"]
                if token:
                    yield token

    try:
        yield from _iter(grammar)
    except Exception as exc:  # noqa: BLE001
        if grammar is not None and _is_grammar_crash(exc):
            print(f"[inference] grammar AV en stream → reintento sin GBNF: {exc}")
            _grammar_disabled_runtime = True
            yield from _iter(None)
        else:
            raise
