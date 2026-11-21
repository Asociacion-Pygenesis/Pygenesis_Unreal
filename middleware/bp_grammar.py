"""GBNF para sampling restringido de grafos BP-Lite (solo jobs BP).

Por defecto usa el JSON_GBNF estable de llama-cpp (evita AV por GBNF mal parseado).
``PYGENESIS_BP_GRAMMAR=bp`` activa el schema estricto BP-Lite; ``off`` desactiva.
"""

from __future__ import annotations

import os
from typing import Any

# GBNF estricto BP-Lite (estilo del JSON_GBNF oficial; una regla por bloque).
BP_LITE_GBNF = r"""
root ::= "{" ws "\"graph_name\"" ws ":" ws string "," ws "\"nodes\"" ws ":" ws "[" ws nodelist? "]" ws "}" ws

nodelist ::= node ("," ws node)*

node ::= "{" ws "\"id\"" ws ":" ws string "," ws "\"type\"" ws ":" ws string "," ws "\"name\"" ws ":" ws string "," ws "\"inputs\"" ws ":" ws object "," ws "\"outputs\"" ws ":" ws object "}" ws

object ::= "{" ws (member ("," ws member)*)? "}" ws

member ::= string ":" ws value

value ::= object | array | string | number | ("true" | "false" | "null") ws

array ::= "[" ws (value ("," ws value)*)? "]" ws

string ::= "\"" ([^"\\\x7F\x00-\x1F] | "\\" (["\\bfnrt] | "u" [0-9a-fA-F]{4}))* "\"" ws

number ::= ("-"? ([0-9] | [1-9] [0-9]{0,15})) ("." [0-9]+)? ([eE] [-+]? [0-9] [1-9]{0,15})? ws

ws ::= [ \t\n\r]*
"""


def bp_lite_json_schema() -> dict[str, Any]:
    """Schema JSON equivalente (documentación / from_json_schema)."""
    pin_value = {
        "oneOf": [
            {"type": "string"},
            {"type": "number"},
            {"type": "boolean"},
            {"type": "null"},
            {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 3,
            },
        ]
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["graph_name", "nodes"],
        "properties": {
            "graph_name": {"type": "string"},
            "nodes": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "type", "name", "inputs", "outputs"],
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string"},
                        "name": {"type": "string"},
                        "inputs": {
                            "type": "object",
                            "additionalProperties": pin_value,
                        },
                        "outputs": {
                            "type": "object",
                            "additionalProperties": pin_value,
                        },
                    },
                },
            },
        },
    }


def grammar_mode() -> str:
    """off | json | bp — default off (vulkan/llama-cpp AV con GBNF); activar con env."""
    return os.environ.get("PYGENESIS_BP_GRAMMAR", "off").strip().lower()


def get_bp_lite_grammar(*, verbose: bool = False) -> Any | None:
    """LlamaGrammar o None si grammar desactivada."""
    mode = grammar_mode()
    if mode in {"0", "off", "false", "none", "no"}:
        return None

    from llama_cpp import LlamaGrammar
    from llama_cpp.llama_grammar import JSON_GBNF

    if mode in {"bp", "bplite", "strict"}:
        gbnf = BP_LITE_GBNF
    else:
        # Default: JSON genérico — evita access violation del GBNF custom en vulkan.
        gbnf = JSON_GBNF

    return LlamaGrammar.from_string(gbnf, verbose=verbose)
