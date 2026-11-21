"""Background startup: RAG + GGUF model load."""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

import inference
from services.rag import cargar_rag

startup_state: dict[str, Any] = {"phase": "starting", "detail": "Inicializando"}


def _startup_worker() -> None:
    try:
        cargar_rag(
            on_loading=lambda: startup_state.update(
                {"phase": "loading_rag", "detail": "Cargando RAG"}
            )
        )
        startup_state.update({"phase": "loading_model", "detail": "Cargando modelo GGUF"})
        try:
            inference.load_model()
        except RuntimeError as exc:
            print(f"AVISO: {exc}")
        status = inference.get_status()
        if status.get("loaded"):
            startup_state.update({"phase": "ready", "detail": "Listo"})
        else:
            startup_state.update(
                {
                    "phase": "degraded",
                    "detail": status.get("error") or "Modelo no cargado",
                }
            )
    except Exception as exc:  # noqa: BLE001 — no tumbar el proceso del puente
        print(f"ERROR en arranque en segundo plano: {exc}")
        startup_state.update({"phase": "error", "detail": str(exc)})


@asynccontextmanager
async def lifespan(_: FastAPI):
    startup_state.update({"phase": "starting", "detail": "Arranque en segundo plano"})
    worker = threading.Thread(
        target=_startup_worker, name="pygenesis-unreal-startup", daemon=True
    )
    worker.start()
    yield
    inference.unload_model()
