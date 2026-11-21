"""Backend FastAPI para Pygenesis UnrealExpert AI (inferencia local GGUF + RAG opcional)."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

BACKEND_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.routes_apply import router as apply_router  # noqa: E402
from api.routes_chat import router as chat_router  # noqa: E402
from api.routes_health import router as health_router  # noqa: E402
from schemas import (  # noqa: E402
    AplicarBpLiteRequest,
    AplicarLightingRequest,
    Consulta,
)
from services.intent import (  # noqa: E402
    _es_pregunta_tema_nuevo,
    _es_seguimiento_uso,
    _pide_json_lighting,
)
from services.prompt_builder import construir_prompt  # noqa: E402
from services.startup import lifespan  # noqa: E402

app = FastAPI(title="Pygenesis UnrealExpert AI Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(apply_router)
app.include_router(health_router)

__all__ = [
    "app",
    "Consulta",
    "AplicarBpLiteRequest",
    "AplicarLightingRequest",
    "construir_prompt",
    "_es_pregunta_tema_nuevo",
    "_es_seguimiento_uso",
    "_pide_json_lighting",
]
