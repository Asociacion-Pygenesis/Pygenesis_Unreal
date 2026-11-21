"""Utilidades de pines BP-Lite."""

from __future__ import annotations

import re
from typing import Any

_PIN_REF_RE = re.compile(r"^[\w]+\.[\w]+$", re.IGNORECASE)


def norm_node_id(node_id: Any, fallback_index: int) -> str:
    if node_id is None:
        return f"node_{fallback_index:02d}"
    s = str(node_id).strip()
    if s.isdigit():
        return f"node_{int(s):02d}"
    if re.fullmatch(r"node_?\d+", s, re.IGNORECASE):
        num = re.sub(r"\D", "", s)
        return f"node_{int(num):02d}"
    return s


def as_pin_map(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(v, dict) and "value" in v and len(v) <= 2:
                out[str(k)] = v.get("value")
            elif isinstance(v, list) and v and isinstance(v[0], dict) and "connection_id" in v[0]:
                links = []
                for x in v:
                    cid = x.get("connection_id")
                    if cid is None:
                        continue
                    links.append(
                        f"node_{int(cid):02d}" if str(cid).isdigit() else str(cid)
                    )
                out[str(k)] = links[0] if len(links) == 1 else links
            elif (
                isinstance(v, list)
                and len(v) == 1
                and isinstance(v[0], (str, int, float, bool))
            ):
                out[str(k)] = v[0]
            else:
                out[str(k)] = v
        return out
    return {}


def clean_pin_map(pins: dict[str, Any], *, is_outputs: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (pins or {}).items():
        if v in (None, ""):
            continue
        kl = str(k).lower().replace(" ", "").lstrip("/")
        if is_outputs:
            # Basura explícita del LLM
            if kl in {"nextnode", "next"} or (kl == "exec" and not _PIN_REF_RE.match(str(v))):
                continue
            if kl == "pressed":
                out["Pressed"] = v
            elif kl == "released":
                out["Released"] = v
            elif kl in {"then", "else"}:
                out[kl] = v
            elif kl == "completed":
                out["Completed"] = v
            elif kl in {"exec_out", "execout", "then_exec"}:
                out["exec_out"] = v
            elif kl == "returnvalue":
                out["ReturnValue"] = v
            else:
                # Preservar pines desconocidos (Released, custom, etc.)
                out[str(k)] = v
            continue
        if kl in {"nextnode", "next", "pressed"}:
            continue
        out[k] = v
    return out


def io_type_hint_blob(inputs: Any, outputs: Any) -> str:
    """Pistas mínimas: solo claves de pin, no valores (evita clasificar por cables)."""
    parts: list[str] = []
    for d in (inputs, outputs):
        if not isinstance(d, dict):
            continue
        for k in d.keys():
            parts.append(str(k))
    return "".join(parts).lower()
