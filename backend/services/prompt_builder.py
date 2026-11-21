"""Prompt assembly for Llama 3.1 Instruct (BP / Lighting / follow-up / concept)."""

from __future__ import annotations

import re

from page_context import (
    PAGE_LABELS,
    ContextAnalysis,
    analizar_modo_contexto,
    pagina_para_revision,
)
from schemas import Consulta
from unreal_system import UNREAL_SYSTEM
from unreal_system_compact import (
    UNREAL_SYSTEM_BP,
    UNREAL_SYSTEM_FOLLOWUP,
    UNREAL_SYSTEM_LIGHT,
)

from services.intent import (
    _es_pregunta_revision,
    _es_pregunta_tema_nuevo,
    _es_saludo_o_casual,
    _es_seguimiento_uso,
    _pide_json_bp,
    _pide_json_lighting,
)

# Llama 3.1 Instruct tokens (evitar literales completos en una sola cadena).
_EOT = "<|" + "eot_id|>"
_BEGIN = "<|" + "begin_of_text|>"

def _llama_turn(role: str, content: str) -> str:
    return f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}{_EOT}"

def _json_body_for_continue(text: str) -> str:
    """Extrae el cuerpo JSON (posiblemente truncado) para un turno de continuación."""
    t = (text or "").strip()
    if not t:
        return ""
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()
    start = t.find("{")
    if start < 0:
        return ""
    return t[start:].rstrip()


def open_nodes_prefix(raw: str) -> str:
    """Deja el array nodes abierto, con coma, para que el modelo escriba el siguiente nodo.

    Un objeto ya cerrado se copia tal cual y el modelo vuelve a parar en BeginPlay.
    """
    body = _json_body_for_continue(raw).rstrip()
    if not body.startswith("{"):
        return ""
    opened = body
    if opened.endswith("}"):
        inner = opened[:-1].rstrip()
        if inner.endswith("]"):
            opened = inner[:-1].rstrip()
    if not opened.endswith("}"):
        return ""
    return opened + ","


def stitch_continuation(prefix: str, suffix: str) -> str:
    """Une el array abierto con lo que el modelo ha escrito a continuación."""
    head = prefix or ""
    tail = (suffix or "").lstrip()
    if not head:
        return _json_body_for_continue(tail) or tail
    if '"graph_name"' in tail:
        return _json_body_for_continue(tail) or tail
    if head.endswith(",") and tail.startswith(","):
        tail = tail[1:].lstrip()
    return head + tail


def _build_bp_continue_prompt(
    user_prompt: str,
    partial_json: str,
    *,
    missing: list[str] | None = None,
) -> str:
    """Segundo turno: el asistente ya tiene el JSON abierto y solo añade nodos."""
    partial = (partial_json or "").strip()
    prefill = open_nodes_prefix(partial)
    gaps = [g for g in (missing or []) if g]
    gap_line = (
        ("Falta respecto a la petición: " + "; ".join(gaps) + ".\n")
        if gaps
        else ""
    )
    hint = (
        "El array nodes está ABIERTO y termina en coma. "
        "Escribe solo los nodos que faltan y después cierra con ]}. "
        "No repitas los nodos ya escritos. No abras otro objeto. Sin prosa."
    )
    user = (
        f"Petición original:\n{user_prompt.strip()}\n\n"
        f"{gap_line}"
        "Continúa el JSON ya empezado."
    )
    return "".join(
        [
            _BEGIN,
            _llama_turn("system", UNREAL_SYSTEM_BP + "\n" + hint),
            _llama_turn("user", user),
            "<|start_header_id|>assistant<|end_header_id|>\n\n",
            prefill,
        ]
    )

_PAGE_HINTS: dict[str, str] = {
    "blueprints": "Prioriza Event Graph, nodos BP-Lite, eventos, variables y flujo de ejecución.",
    "lighting": "Prioriza Directional/Sky Light, fog, Post Process y presets Lighting-Spec.",
    "materials": "Prioriza Material Editor, PBR, instancias y Nanite cuando aplique.",
    "niagara": "Prioriza emitters, módulos y rendimiento de sistemas de partículas.",
    "sequencer": "Prioriza Level Sequences, tracks de cámara y cine.",
    "cplusplus": "Prioriza UCLASS, lifecycle, Garbage Collection y módulos del proyecto.",
    "performance": "Prioriza profiling, LODs, Nanite/Lumen cost y scalability.",
}

_PAGE_REVIEW_HINTS: dict[str, str] = {
    "blueprints": (
        "El usuario pide una REVISIÓN de Blueprints. Checklist 5-8 puntos: "
        "eventos de entrada, casts, referencias hard, ticks innecesarios, "
        "replicación si multiplayer, y claridad del grafo."
    ),
    "lighting": (
        "El usuario pide una REVISIÓN de iluminación. Checklist: intensidad/temperatura, "
        "skylight, fog volumétrico, exposure, bloom y coherencia Lumen."
    ),
    "performance": (
        "El usuario pide una REVISIÓN de rendimiento. Checklist: stat unit, draw calls, "
        "sombras, Lumen/Nanite, LODs y presupuesto de CPU/GPU."
    ),
}


def _detectar_pagina(contexto_proyecto: str) -> str | None:
    """Lee líneas tipo 'Área activa: Blueprints' o 'Modo editor: Lighting'."""
    mapping = {
        "blueprints": "blueprints",
        "blueprint": "blueprints",
        "lighting": "lighting",
        "iluminacion": "lighting",
        "iluminación": "lighting",
        "materials": "materials",
        "materiales": "materials",
        "niagara": "niagara",
        "sequencer": "sequencer",
        "c++": "cplusplus",
        "cplusplus": "cplusplus",
        "performance": "performance",
        "rendimiento": "performance",
    }
    for line in contexto_proyecto.splitlines():
        line = line.strip()
        lower = line.lower()
        if lower.startswith(("área activa:", "area activa:", "modo editor:", "contexto:")):
            label = line.split(":", 1)[1].strip().lower()
            return mapping.get(label, label)
    return None


def _bloque_contexto_plugin(contexto_proyecto: str, analysis: ContextAnalysis) -> str:
    pagina = analysis.pagina_activa
    hint = _PAGE_HINTS.get(pagina or "", "")
    base_info = contexto_proyecto.strip()

    if analysis.mode == "mismatch":
        tema = analysis.tema_pregunta or ""
        tema_label = PAGE_LABELS.get(tema, tema)
        activa_label = PAGE_LABELS.get(pagina or "", pagina or "Desconocido")
        bloque = (
            "Contexto desde el plugin Pygenesis (Unreal Editor).\n"
            f"El usuario está en {activa_label} pero pregunta sobre {tema_label}.\n"
            f"IMPORTANTE: responde sobre {tema_label} como pregunta de conocimiento general.\n"
            "NO digas que necesitas otro panel para responder.\n\n"
            f"{base_info}"
        )
        tema_hint = _PAGE_HINTS.get(tema, "")
        if tema_hint:
            bloque += f"\n\nEnfoque de la respuesta ({tema_label}):\n{tema_hint}"
        return bloque

    if analysis.mode == "general":
        return (
            "Contexto desde el plugin Pygenesis (Unreal Editor).\n"
            "El usuario trabaja en el proyecto indicado abajo.\n"
            "Responde la pregunta directamente; no la limites solo al área activa "
            "salvo que sea relevante.\n\n"
            f"{base_info}"
        )

    bloque = (
        "Contexto en tiempo real desde el plugin Pygenesis (Unreal Editor).\n"
        "Adapta la respuesta al área activa indicada abajo cuando sea relevante.\n"
        "Si el usuario dice 'aquí' o 'este nivel', usa el contexto actual.\n\n"
        f"{base_info}"
    )
    if hint:
        bloque += f"\n\nEnfoque para esta área:\n{hint}"
    return bloque


def _bloque_ejemplos_rag(contexto_rag: list) -> str:
    ejemplos = ""
    for i, frag in enumerate(contexto_rag):
        ejemplos += (
            f"\nEjemplo {i + 1}:\nPregunta: {frag['pregunta']}\n"
            f"Respuesta: {frag['respuesta']}\n"
        )
    return f"Ejemplos de referencia:\n{ejemplos}"


def _bloque_revision(pagina: str | None, prompt: str) -> str:
    if not _es_pregunta_revision(prompt):
        return ""
    review = _PAGE_REVIEW_HINTS.get(pagina or "")
    if not review:
        return (
            "El usuario pide qué revisar en el área activa. "
            "Responde con un checklist priorizado de 5-8 puntos, "
            "no con un tutorial de una sola herramienta."
        )
    return review


def construir_prompt(consulta: Consulta, contexto_rag: list) -> str:
    if _es_saludo_o_casual(consulta.prompt):
        parts = [
            _BEGIN,
            _llama_turn("system", UNREAL_SYSTEM),
            _llama_turn(
                "system",
                "El usuario solo saluda o habla de forma casual. "
                "Responde en 1 o 2 frases amables en español. "
                "NO generes JSON. NO menciones BP-Lite, Lighting-Spec ni tus reglas internas. "
                "NO repitas el saludo ni copies instrucciones del sistema.",
            ),
            _llama_turn("user", consulta.prompt.strip()),
            "<|start_header_id|>assistant<|end_header_id|>\n\n",
        ]
        return "".join(parts)

    prev = (consulta.ultima_respuesta or "").strip()
    if prev and len(prev) > 1200:
        prev = prev[:1200] + "\n…"

    # Follow-up / "sí" tras JSON+pregunta (explicación bajo demanda)
    if _es_seguimiento_uso(consulta.prompt, prev) and prev:
        user_block = (
            f"Respuesta anterior del asistente:\n{prev}\n\n"
            f"El usuario quiere la explicación (dijo: {consulta.prompt.strip()}).\n"
            "Responde SOLO con pasos numerados. PROHIBIDO JSON."
        )
        return "".join(
            [
                _BEGIN,
                _llama_turn("system", UNREAL_SYSTEM_FOLLOWUP),
                _llama_turn("user", user_block),
                # Priming: evita que el modelo empiece repitiendo el JSON
                "<|start_header_id|>assistant<|end_header_id|>\n\n"
                "1.",
            ]
        )
    if _es_seguimiento_uso(consulta.prompt, prev) and not prev:
        return "".join(
            [
                _BEGIN,
                _llama_turn(
                    "system",
                    UNREAL_SYSTEM_FOLLOWUP
                    + " No hay respuesta anterior: pide al usuario que aclare "
                    "si habla de un Blueprint o de iluminación. NO inventes JSON.",
                ),
                _llama_turn("user", consulta.prompt.strip()),
                "<|start_header_id|>assistant<|end_header_id|>\n\n",
            ]
        )

    # Concepto / diferencia / qué es → texto, NUNCA Lighting-Spec ni BP-Lite
    if _es_pregunta_tema_nuevo(consulta.prompt):
        parts = [
            _BEGIN,
            _llama_turn(
                "system",
                "Eres Pygenesis UnrealExpert AI (UE5). Responde en español.\n"
                "El usuario pide una EXPLICACIÓN de concepto. "
                "Responde solo con texto claro y conciso (qué es / diferencias / cuándo usar).\n"
                "Nombra solo nodos, pines y propiedades que existan de verdad en UE5; "
                "si no estás seguro de un nombre, descríbelo sin inventarlo.\n"
                "PROHIBIDO JSON, BP-Lite, Lighting-Spec, fences ``` y pasos de Aplicar.",
            ),
        ]
        if contexto_rag:
            parts.append(_llama_turn("system", _bloque_ejemplos_rag(contexto_rag)))
        parts.append(_llama_turn("user", consulta.prompt.strip()))
        parts.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
        return "".join(parts)

    wants_lighting_early = _pide_json_lighting(consulta.prompt)
    wants_graph_early = _pide_json_bp(consulta.prompt)
    # Prompt corto = primer token mucho antes (evita 2–3 min de prefilling en silencio)
    if wants_lighting_early and not _es_pregunta_revision(consulta.prompt):
        return "".join(
            [
                _BEGIN,
                _llama_turn("system", UNREAL_SYSTEM_LIGHT),
                _llama_turn("user", consulta.prompt.strip()),
                "<|start_header_id|>assistant<|end_header_id|>\n\n",
            ]
        )
    if wants_graph_early and not _es_pregunta_revision(consulta.prompt):
        # Sin priming de '{': el modelo (como en Ollama) emite el objeto completo;
        # forzar '{"graph_name":"' provocaba JSON a medias con campos "".
        return "".join(
            [
                _BEGIN,
                _llama_turn("system", UNREAL_SYSTEM_BP),
                _llama_turn("user", consulta.prompt.strip()),
                "<|start_header_id|>assistant<|end_header_id|>\n\n",
            ]
        )

    system = UNREAL_SYSTEM + "\n\nNo cites fuentes ni añadas prefijos tipo [Fuente: ...]."
    parts = [_BEGIN, _llama_turn("system", system)]

    pagina = _detectar_pagina(consulta.contexto_proyecto)
    es_revision = _es_pregunta_revision(consulta.prompt)
    analysis = analizar_modo_contexto(
        consulta.prompt,
        pagina,
        es_revision=es_revision,
    )

    if consulta.contexto_proyecto.strip():
        parts.append(_llama_turn("system", _bloque_contexto_plugin(consulta.contexto_proyecto, analysis)))

    pagina_revision = pagina_para_revision(analysis, consulta.prompt, es_revision)
    revision = _bloque_revision(pagina_revision, consulta.prompt)
    if revision:
        parts.append(_llama_turn("system", revision))

    if contexto_rag:
        parts.append(_llama_turn("system", _bloque_ejemplos_rag(contexto_rag)))

    wants_lighting = _pide_json_lighting(consulta.prompt)
    if wants_lighting:
        parts.append(
            _llama_turn(
                "system",
                "El usuario pide iluminación/atmósfera. Responde PRIMERO con JSON Lighting-Spec "
                "completo (environment_type, directional_light, sky_light, exponential_fog, "
                "post_process) en un fence ```json. Después máximo 3 frases. Sin JSON no sirve Aplicar Lighting.",
            )
        )
    wants_graph_prompt = _pide_json_bp(consulta.prompt)
    if wants_graph_prompt and not wants_lighting:
        parts.append(
            _llama_turn(
                "system",
                "El usuario pide Blueprint. PRIMERO un único JSON BP-Lite válido. "
                "DESPUÉS como máximo un párrafo o 4 pasos numerados. "
                "NO repitas el JSON ni alargues con checklists enormes. Cuando acabes, PARA.",
            )
        )

    user_msg = consulta.prompt
    if consulta.contexto_proyecto.strip():
        if analysis.mode == "mismatch":
            tema_label = PAGE_LABELS.get(analysis.tema_pregunta or "", analysis.tema_pregunta or "")
            activa_label = PAGE_LABELS.get(analysis.pagina_activa or "", analysis.pagina_activa or "")
            extra = (
                f"Responde sobre {tema_label}. El usuario está en {activa_label} "
                "pero la pregunta es de conocimiento general sobre esa área."
            )
        elif analysis.mode == "general":
            extra = "Responde directamente; usa nivel/actores solo como referencia."
        elif es_revision:
            extra = (
                "Es una pregunta de REVISIÓN/CHECKLIST: lista qué comprobar en el área indicada."
            )
        else:
            extra = (
                "El usuario pregunta desde Unreal Editor; usa el contexto del system anterior."
            )
        user_msg = f"{consulta.prompt}\n\n({extra})"

    parts.append(_llama_turn("user", user_msg))
    # NUNCA forzar ```json aquí en follow-ups ambiguos (alucinaba Lighting-Spec).
    # Solo priming de fence si el usuario pidió iluminación explícitamente.
    if wants_lighting and not _es_seguimiento_uso(consulta.prompt):
        parts.append("<|start_header_id|>assistant<|end_header_id|>\n\n```json\n")
    else:
        parts.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
    return "".join(parts)

