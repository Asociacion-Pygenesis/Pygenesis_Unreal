"""GBNF/registry: grammar string válida; normalización siempre disponible."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["PYGENESIS_BP_GRAMMAR"] = "json"
from middleware.bp_grammar import BP_LITE_GBNF, grammar_mode
from middleware.bp_lite import prepare_apply_payload
from middleware.bp_normalize.registry import list_normalizers

assert grammar_mode() == "json"
assert "graph_name" in BP_LITE_GBNF
assert "ws ::= [ \\t\\n\\r]*" in BP_LITE_GBNF or "ws ::= [ \t\n\r]*" in BP_LITE_GBNF
assert "LaunchCharacter" in list_normalizers()

try:
    from middleware.bp_grammar import get_bp_lite_grammar

    g = get_bp_lite_grammar(verbose=False)
    # llama_cpp puede no estar en el PATH de scripts unitarios
    _ = g
except ModuleNotFoundError:
    print("llama_cpp not installed — skip LlamaGrammar bind")

sample = {
    "graph_name": "HolaMundo",
    "nodes": [
        {
            "id": "node_01",
            "type": "Event",
            "name": "EventBeginPlay",
            "inputs": {},
            "outputs": {"exec_out": "node_02.exec_in"},
        },
        {
            "id": "node_02",
            "type": "FunctionCall",
            "name": "PrintString",
            "inputs": {"exec_in": "node_01.exec_out", "InString": "Hola"},
            "outputs": {"exec_out": "node_03.exec_in"},
        },
        {
            "id": "node_03",
            "type": "FunctionCall",
            "name": "Delay",
            "inputs": {"exec_in": "node_02.exec_out", "Duration": 1.0},
            "outputs": {"exec_out": "node_04.exec_in"},
        },
        {
            "id": "node_04",
            "type": "FunctionCall",
            "name": "PrintString",
            "inputs": {"exec_in": "node_03.exec_out", "InString": "Mundo"},
            "outputs": {},
        },
    ],
}
r = prepare_apply_payload(sample)
assert r.get("ok"), r
names = [n["name"] for n in r["graph"]["nodes"]]
assert names == ["EventBeginPlay", "PrintString", "Delay", "PrintString"], names
print("GBNF+registry OK", json.dumps(names))
