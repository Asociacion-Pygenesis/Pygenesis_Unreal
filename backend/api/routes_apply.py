"""Apply BP-Lite / Lighting-Spec endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from middleware.bp_lite import prepare_apply_payload
from schemas import AplicarBpLiteRequest, AplicarLightingRequest

router = APIRouter()


@router.post("/aplicar/bp-lite")
async def aplicar_bp_lite(req: AplicarBpLiteRequest):
    """Normaliza BP-Lite desde texto/grafo y devuelve script Python + guía."""
    source: str | dict[str, Any]
    if req.graph:
        source = req.graph
    else:
        source = req.texto
    result = prepare_apply_payload(source, user_prompt=req.prompt)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "BP-Lite invalido")
    # Regenerar script con asset_path pedido
    from middleware.bp_lite import bplite_to_apply_script

    graph = result["graph"]
    result["script"] = bplite_to_apply_script(graph, asset_path=req.asset_path or "/Game/Pygenesis")
    result["asset_path"] = req.asset_path or "/Game/Pygenesis"
    return result


@router.post("/aplicar/lighting-spec")
async def aplicar_lighting_spec(req: AplicarLightingRequest):
    """Normaliza Lighting-Spec desde texto/spec y lo devuelve listo para el Editor."""
    from middleware.lighting import prepare_lighting_payload

    source: str | dict[str, Any]
    if req.spec:
        source = req.spec
    else:
        source = req.texto
    result = prepare_lighting_payload(source)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400, detail=result.get("error") or "Lighting-Spec invalido"
        )
    return result
