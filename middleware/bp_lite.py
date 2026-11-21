"""Encoder/decoder BP-Lite ↔ Unreal (PlanUnreal.md).

Arquitectura:
- Inferencia BP: GBNF opcional en ``middleware.bp_grammar``.
- Validación: Pydantic ``middleware.bp_models``.
- Dominio: registro de normalizadores ``middleware.bp_normalize``.
Filosofía: parseo strict-first; preservar la intención del modelo.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .bp_apply_script import build_apply_script
from .bp_complete import (
    is_syntactically_truncated,
    note_salvage,
    note_truncation,
    salvage_truncated_nodes,
)
from .bp_naming import ensure_distinct_graph_name
from .bp_normalize import normalize_graph


def ue_text_to_bplite(raw_ue_text: str) -> dict:
    object_blocks = re.findall(
        r"Begin Object Class=(.*?) End Object", raw_ue_text, re.DOTALL
    )

    if not object_blocks:
        return {"error": "No se encontraron nodos válidos de Unreal Engine."}

    name_to_id: dict[str, str] = {}
    node_data_list: list[tuple[str, str, str]] = []

    for idx, block in enumerate(object_blocks, start=1):
        name_match = re.search(r'Name="([^"]+)"', block)
        orig_name = name_match.group(1) if name_match else f"Unknown_{idx}"
        node_id = f"node_{idx:02d}"
        name_to_id[orig_name] = node_id
        node_data_list.append((node_id, orig_name, block))

    def simplify_type_and_name(block: str) -> tuple[str, str]:
        class_match = re.search(r"Class=([^\s]+)", block)
        class_path = class_match.group(1) if class_match else ""
        class_name = class_path.split(".")[-1].replace('"', "")

        type_map = {
            "K2Node_Event": "Event",
            "K2Node_IfThenElse": "Branch",
            "K2Node_CallFunction": "FunctionCall",
            "K2Node_VariableGet": "VariableGet",
            "K2Node_VariableSet": "VariableSet",
            "K2Node_ExecutionSequence": "Sequence",
        }
        node_type = type_map.get(class_name, class_name)

        node_name_match = re.search(r'NodeName="([^"]+)"', block) or re.search(
            r'MemberName="([^"]+)"', block
        )
        node_name = node_name_match.group(1) if node_name_match else node_type
        return node_type, node_name

    nodes_output: list[dict] = []

    for node_id, _orig_name, block in node_data_list:
        node_type, node_name = simplify_type_and_name(block)
        inputs: dict = {}
        outputs: dict = {}

        pin_lines = re.findall(r"CustomProperties Pin \((.*?)\)", block)
        for pin_str in pin_lines:
            pin_name_m = re.search(r'PinName="([^"]+)"', pin_str)
            dir_m = re.search(r'Direction="([^"]+)"', pin_str)
            linked_m = re.search(r"LinkedTo=\((.*?)\)", pin_str)
            default_m = re.search(r'DefaultValue="([^"]+)"', pin_str)

            if not pin_name_m:
                continue

            pin_name = pin_name_m.group(1)
            is_output = dir_m and dir_m.group(1) == "EGPD_Output"

            connection = None
            if linked_m:
                raw_links = linked_m.group(1).split()
                if raw_links:
                    parts = raw_links[0].split(".") if "." in raw_links[0] else raw_links
                    target_orig = parts[0]
                    target_pin = parts[1] if len(parts) > 1 else "connected_pin"
                    target_id = name_to_id.get(target_orig, target_orig)
                    connection = f"{target_id}.{target_pin}"

            default_val = default_m.group(1) if default_m else None

            if is_output:
                outputs[pin_name] = connection
            else:
                val = connection if connection else default_val
                if val is not None:
                    inputs[pin_name] = val

        nodes_output.append(
            {
                "id": node_id,
                "type": node_type,
                "name": node_name,
                "inputs": inputs,
                "outputs": outputs,
            }
        )

    return {"graph_name": "Unreal_Imported_Graph", "nodes": nodes_output}


def _sanitize_llm_json(raw: str) -> str:
    """Solo como fallback tras JSONDecodeError (no en el camino feliz)."""
    s = raw.strip()
    if s.endswith("}."):
        s = s[:-1]
    s = re.sub(r"//[^\n]*", "", s)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
    s = re.sub(
        r'"(inputs|outputs)"\s*:\s*"([^"]*)"\s*:\s*"([^"]*)"',
        r'"\1":{"\2":"\3"}',
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', s)
    s = re.sub(r",\s*([}\]])", r"\1", s)
    s = re.sub(r'"type"\s*:\s*null', '"type": "FunctionCall"', s, flags=re.IGNORECASE)
    s = re.sub(r'"name"\s*:\s*null', '"name": ""', s, flags=re.IGNORECASE)
    s = re.sub(
        r'"(InString|String|Message|Text)"\s*:\s*\[\s*"([^"]*)"\s*\]',
        r'"\1": "\2"',
        s,
        flags=re.IGNORECASE,
    )
    return s


def _raw_decode_object(text: str) -> dict[str, Any] | None:
    """Primer objeto JSON desde la primera '{' (sin regex codiciosa)."""
    start = text.find("{")
    if start < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _try_parse_json_object(raw: str) -> dict[str, Any] | None:
    """Strict-first: loads → raw_decode → sanitize+loads → cierre de braces."""
    s = (raw or "").strip()
    if not s:
        return None

    # 1) loads directo
    if s.startswith("{"):
        try:
            data = json.loads(s)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # 2) raw_decode desde primera {
    data = _raw_decode_object(s)
    if data is not None:
        return data

    # 3) sanitize solo tras fallo
    if s.startswith("{") or "{" in s:
        chunk = s[s.find("{") :]
        sanitized = _sanitize_llm_json(chunk)
        try:
            data = json.loads(sanitized)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        data = _raw_decode_object(sanitized)
        if data is not None:
            return data

        # 4) cierre sintáctico si truncado (sin inventar nodos)
        open_braces = sanitized.count("{") - sanitized.count("}")
        open_brackets = sanitized.count("[") - sanitized.count("]")
        if open_braces >= 0 and open_brackets >= 0:
            s2 = sanitized + ("]" * open_brackets) + ("}" * open_braces)
            try:
                data = json.loads(s2)
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
    return None


# Compat para response_filters / soft-stop
def _try_repair_json(raw: str) -> dict[str, Any] | None:
    return _try_parse_json_object(raw)


def normalize_bplite(
    graph: dict[str, Any], *, user_prompt: str = ""
) -> dict[str, Any]:
    return normalize_graph(graph, user_prompt=user_prompt)


def finalize_bplite_graph(
    graph: dict[str, Any] | None, user_prompt: str = "", raw_text: str = ""
) -> dict[str, Any] | None:
    """Normaliza y nombra; no inventa grafos. Truncado → None."""
    if graph is None:
        return None
    if is_syntactically_truncated(raw_text):
        return None
    try:
        g = normalize_bplite(graph, user_prompt=user_prompt)
    except Exception:  # noqa: BLE001
        return None
    return ensure_distinct_graph_name(g, user_prompt=user_prompt)


def extract_bplite_from_text(
    text: str, user_prompt: str = ""
) -> dict[str, Any] | None:
    if not text or not text.strip():
        return None

    candidates: list[str] = []
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        candidates.append(fence.group(1).strip())
    # Cuerpo completo / desde primera {
    candidates.append(text.strip())
    start = text.find("{")
    if start >= 0:
        candidates.append(text[start:].strip())

    graph: dict[str, Any] | None = None
    for raw in candidates:
        data = _try_parse_json_object(raw)
        if data and ("nodes" in data or "graph_name" in data):
            try:
                graph = normalize_bplite(data, user_prompt=user_prompt)
            except Exception:  # noqa: BLE001
                graph = data
            break

    return finalize_bplite_graph(graph, user_prompt=user_prompt, raw_text=text)


def validate_bplite(graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not graph.get("graph_name"):
        errors.append("Falta graph_name")
    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        errors.append("nodes vacío")
        return errors
    ids: set[str] = set()
    for n in nodes:
        nid = n.get("id")
        if not nid:
            errors.append("Nodo sin id")
        elif nid in ids:
            errors.append(f"id duplicado: {nid}")
        else:
            ids.add(str(nid))
        if not n.get("type"):
            errors.append(f"Nodo {nid}: falta type")
    return errors


def bplite_summary(graph: dict[str, Any]) -> str:
    nodes = graph.get("nodes") or []
    lines = [f"Grafo: {graph.get('graph_name')} ({len(nodes)} nodos)"]
    for n in nodes:
        lines.append(f"- [{n.get('id')}] {n.get('type')}: {n.get('name')}")
    return "\n".join(lines)


def bplite_to_ue_text(graph: dict[str, Any]) -> str:
    g = normalize_bplite(graph)
    lines = [
        f"// BP-Lite → guía: {g['graph_name']}",
        "// Monta estos nodos en el Event Graph.",
        "",
    ]
    for n in g["nodes"]:
        lines.append(f"Node {n['id']} | {n['type']} | {n['name']}")
        if n.get("inputs"):
            lines.append(f"  inputs: {json.dumps(n['inputs'], ensure_ascii=False)}")
        if n.get("outputs"):
            lines.append(f"  outputs: {json.dumps(n['outputs'], ensure_ascii=False)}")
        lines.append("")
    return "\n".join(lines)


def bplite_to_apply_script(graph: dict[str, Any], asset_path: str = "/Game/Pygenesis") -> str:
    return build_apply_script(normalize_bplite(graph), asset_path=asset_path)


def prepare_apply_payload(
    text_or_graph: str | dict[str, Any],
    user_prompt: str = "",
) -> dict[str, Any]:
    """Entrada para el endpoint: texto del modelo o grafo ya parseado."""
    raw_hint = ""
    warning = ""
    if isinstance(text_or_graph, dict):
        raw_hint = json.dumps(text_or_graph, ensure_ascii=False)
        if is_syntactically_truncated(raw_hint):
            return {
                "ok": False,
                "error": note_truncation(),
            }
        graph = finalize_bplite_graph(
            text_or_graph,
            user_prompt=user_prompt,
            raw_text=raw_hint,
        )
    else:
        raw_hint = text_or_graph or ""
        graph = None
        if is_syntactically_truncated(raw_hint) and not _raw_decode_object(raw_hint):
            # Cortado a medias: aplicar los nodos que sí cerraron en vez de perderlo todo
            salvaged = salvage_truncated_nodes(raw_hint)
            if salvaged is None:
                return {"ok": False, "error": note_truncation()}
            dropped = int(salvaged.pop("_salvaged_dropped", 0) or 0)
            graph = finalize_bplite_graph(
                salvaged,
                user_prompt=user_prompt,
                raw_text=json.dumps(salvaged, ensure_ascii=False),
            )
            if graph is None:
                return {"ok": False, "error": note_truncation()}
            warning = note_salvage(len(graph.get("nodes") or []), dropped)
        else:
            graph = extract_bplite_from_text(text_or_graph, user_prompt=user_prompt)

    if graph is None:
        if is_syntactically_truncated(raw_hint):
            return {"ok": False, "error": note_truncation()}
        return {
            "ok": False,
            "error": "No se encontró JSON BP-Lite válido en la respuesta del modelo",
        }

    errors = validate_bplite(graph)
    if errors:
        return {"ok": False, "error": "; ".join(errors), "graph": graph}

    payload: dict[str, Any] = {
        "ok": True,
        "graph": graph,
        "summary": bplite_summary(graph),
        "guide_text": bplite_to_ue_text(graph),
        "script": bplite_to_apply_script(graph),
    }
    if warning:
        payload["warning"] = warning
        payload["summary"] = f"{payload['summary']}\n{warning}"
    return payload
