"""Modelos Pydantic del contrato BP-Lite."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PinValue = str | int | float | bool | list[float] | None


class BPNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    type: str = "FunctionCall"
    name: str = ""
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "type", "name", mode="before")
    @classmethod
    def _as_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("inputs", "outputs", mode="before")
    @classmethod
    def _as_dict(cls, v: Any) -> dict[str, Any]:
        if v is None:
            return {}
        if isinstance(v, dict):
            return dict(v)
        return {}


class BPGraph(BaseModel):
    model_config = ConfigDict(extra="ignore")

    graph_name: str = "Pygenesis_Graph"
    nodes: list[BPNode] = Field(default_factory=list)

    @field_validator("graph_name", mode="before")
    @classmethod
    def _clean_name(cls, v: Any) -> str:
        s = str(v or "Pygenesis_Graph")
        s = re.sub(r"[^\w\-]+", "_", s).strip("_")
        return s or "Pygenesis_Graph"

    @model_validator(mode="after")
    def _need_nodes(self) -> BPGraph:
        if not self.nodes:
            raise ValueError("nodes vacío")
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")


def parse_bp_graph(data: dict[str, Any]) -> BPGraph:
    """Valida un dict crudo → BPGraph."""
    return BPGraph.model_validate(data)
