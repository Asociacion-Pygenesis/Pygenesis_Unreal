"""Detección de tema de pregunta vs contexto activo en el Editor de Unreal."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ContextMode = Literal["contextual", "matched", "general", "mismatch"]

PAGE_LABELS: dict[str, str] = {
    "blueprints": "Blueprints",
    "lighting": "Lighting / Atmosphere",
    "materials": "Materials",
    "niagara": "Niagara",
    "sequencer": "Sequencer",
    "cplusplus": "C++",
    "performance": "Performance",
}

_EXPLICIT_PAGE_RE: dict[str, re.Pattern[str]] = {
    "blueprints": re.compile(
        r"\b(?:blueprint[s]?|bp-lite|event\s+graph|graph\s+editor)\b", re.IGNORECASE
    ),
    "lighting": re.compile(
        r"\b(?:lighting|iluminaci[oó]n|lumen|post[-\s]?process|sky\s*light|"
        r"directional\s*light|fog|niebla|lighting-spec)\b",
        re.IGNORECASE,
    ),
    "materials": re.compile(r"\b(?:material(?:es|es)?|shader|nanite)\b", re.IGNORECASE),
    "niagara": re.compile(r"\b(?:niagara|vfx|part[ií]cula[s]?)\b", re.IGNORECASE),
    "sequencer": re.compile(r"\b(?:sequencer|cinem[aá]tica[s]?|level\s+sequence)\b", re.IGNORECASE),
    "cplusplus": re.compile(r"\b(?:c\+\+|cpp|uproject|uclass|actor\s+component)\b", re.IGNORECASE),
    "performance": re.compile(
        r"\b(?:optimizaci[oó]n|performance|profiling|stat\s+unit|scalability)\b",
        re.IGNORECASE,
    ),
}

_TOPIC_SCORE_RE: list[tuple[str, re.Pattern[str]]] = [
    (
        "blueprints",
        re.compile(
            r"\b(?:blueprint|evento|branch|line\s*trace|cast\s+to|custom\s+event|"
            r"variable\s+get|bp-lite|nodo[s]?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "lighting",
        re.compile(
            r"\b(?:luz|light|lumen|exposure|bloom|vignette|fog|niebla|"
            r"post[-\s]?process|atm[oó]sfera|lighting-spec)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "materials",
        re.compile(r"\b(?:material|shader|albedo|roughness|metallic|nanite)\b", re.IGNORECASE),
    ),
    (
        "niagara",
        re.compile(r"\b(?:niagara|emitter|particle|sistema\s+de\s+part)\b", re.IGNORECASE),
    ),
    (
        "sequencer",
        re.compile(r"\b(?:sequencer|timeline|cinem[aá]tica|camera\s+cut)\b", re.IGNORECASE),
    ),
    (
        "cplusplus",
        re.compile(r"\b(?:c\+\+|uclass|beginplay|tick|subsystem)\b", re.IGNORECASE),
    ),
    (
        "performance",
        re.compile(r"\b(?:fps|optimiz|profiling|draw\s*calls|lod)\b", re.IGNORECASE),
    ),
]


@dataclass
class ContextAnalysis:
    mode: ContextMode
    pagina_activa: str | None
    tema_pregunta: str | None
    reason: str = ""


def _score_topics(prompt: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    for topic, pattern in _TOPIC_SCORE_RE:
        if pattern.search(prompt):
            scores[topic] = scores.get(topic, 0) + 1
    return scores


def detectar_tema_pregunta(prompt: str) -> str | None:
    scores = _score_topics(prompt)
    if not scores:
        return None
    return max(scores.items(), key=lambda kv: kv[1])[0]


def detectar_pagina_explicita(prompt: str) -> str | None:
    for page, pattern in _EXPLICIT_PAGE_RE.items():
        if pattern.search(prompt):
            return page
    return None


def pagina_para_revision(
    analysis: ContextAnalysis,
    prompt: str,
    es_revision: bool,
) -> str | None:
    if not es_revision:
        return analysis.pagina_activa
    return analysis.tema_pregunta or analysis.pagina_activa or detectar_pagina_explicita(prompt)


def analizar_modo_contexto(
    prompt: str,
    pagina_activa: str | None,
    *,
    es_revision: bool = False,
) -> ContextAnalysis:
    tema = detectar_tema_pregunta(prompt)
    if not pagina_activa and not tema:
        return ContextAnalysis("general", None, None, "sin contexto ni tema")
    if pagina_activa and tema and pagina_activa != tema:
        return ContextAnalysis(
            "mismatch",
            pagina_activa,
            tema,
            f"pregunta sobre {tema} estando en {pagina_activa}",
        )
    if pagina_activa and (not tema or pagina_activa == tema):
        return ContextAnalysis(
            "contextual" if not tema else "matched",
            pagina_activa,
            tema or pagina_activa,
            "contexto editor",
        )
    return ContextAnalysis("general", pagina_activa, tema, "tema general")
