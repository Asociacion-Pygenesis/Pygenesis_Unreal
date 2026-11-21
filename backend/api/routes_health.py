"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

import inference
from services.rag import rag_stats
from services.startup import startup_state

router = APIRouter()


@router.get("/health")
async def health():
    model_status = inference.get_status()
    ok = model_status["loaded"]
    phase = startup_state.get("phase") or "unknown"
    if ok:
        status = "ok"
    elif phase in {"starting", "loading_rag", "loading_model"}:
        status = "starting"
    else:
        status = "degraded"
    stats = rag_stats()
    return {
        "status": status,
        "modelo": model_status["modelo"],
        "backend": model_status["backend"],
        "model_path": model_status["model_path"],
        "model_loaded": ok,
        "startup_phase": phase,
        "startup_detail": startup_state.get("detail"),
        "fragmentos": stats["fragmentos"],
        "rag_activo": stats["rag_activo"],
        "error": model_status.get("error")
        or (startup_state.get("detail") if phase == "error" else None),
    }
