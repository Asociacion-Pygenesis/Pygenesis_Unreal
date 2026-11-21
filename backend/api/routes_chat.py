"""Chat / consult endpoints."""

from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from schemas import Consulta
from services.job_runner import (
    _ensure_model_ready,
    _run_job,
    _stream_inference_sse,
    cancel_job,
    create_job,
    jobs,
    jobs_lock,
)

router = APIRouter()


@router.post("/consultar")
async def consultar(consulta: Consulta):
    """Versión síncrona del mismo pipeline que los jobs (sin polling)."""
    _ensure_model_ready()
    job_id = create_job()
    await asyncio.to_thread(_run_job, job_id, consulta)
    with jobs_lock:
        job = jobs.pop(job_id, None) or {}
    if job.get("error"):
        raise HTTPException(status_code=500, detail=job["error"])
    return {
        "respuesta": job.get("respuesta") or "",
        "fragmentos_usados": job.get("fragmentos_usados") or 0,
    }


@router.post("/consultar/async")
async def consultar_async(consulta: Consulta):
    """Encola la inferencia y devuelve job_id de inmediato (<1 s)."""
    _ensure_model_ready()
    job_id = create_job()
    threading.Thread(
        target=_run_job,
        args=(job_id, consulta),
        name=f"pygenesis-job-{job_id[:8]}",
        daemon=True,
    ).start()
    return {"job_id": job_id, "status": "running"}


@router.get("/consultar/job/{job_id}")
async def consultar_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_id desconocido")
    return {"job_id": job_id, **job}


@router.post("/consultar/job/{job_id}/cancel")
async def consultar_job_cancel(job_id: str):
    """Corta la generación y conserva lo ya producido (el plugin puede abandonar)."""
    if not cancel_job(job_id):
        raise HTTPException(status_code=404, detail="job_id desconocido")
    return {"job_id": job_id, "status": "cancelling"}


@router.post("/consultar/stream")
async def consultar_stream(consulta: Consulta):
    return StreamingResponse(
        _stream_inference_sse(consulta),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
