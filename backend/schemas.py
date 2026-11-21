"""Pydantic request/response models for the Pygenesis Unreal backend API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Consulta(BaseModel):
    prompt: str
    contexto_proyecto: str = ""
    modo_json: bool = False
    # Última respuesta del asistente (follow-ups: "cómo usarlo")
    ultima_respuesta: str = ""


class AplicarBpLiteRequest(BaseModel):
    texto: str = ""
    graph: dict[str, Any] | None = None
    asset_path: str = "/Game/Pygenesis"
    # Petición original: sin ella el prune borra nodos legítimos (p.ej. PrintString suelto)
    prompt: str = ""


class AplicarLightingRequest(BaseModel):
    texto: str = ""
    spec: dict[str, Any] | None = None
