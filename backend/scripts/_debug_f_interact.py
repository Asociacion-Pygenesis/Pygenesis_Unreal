"""Debug: Event_Interact se preserva (sin repair a InputKey)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from middleware.bp_complete import complete_if_incomplete, graph_looks_incomplete
from middleware.bp_lite import prepare_apply_payload
from middleware.bp_normalize import normalize_graph

prompt = (
    'Crea un Blueprint: al pulsar F imprime en pantalla "Interactuando" con PrintString.'
)
raw = (
    '{"graph_name":"FInteract","nodes":['
    '{"id":"node_01","type":"Event","name":"Event_Interact","inputs":{},'
    '"outputs":{"exec_out":"node_03.exec_in"}},'
    '{"id":"node_03","type":"FunctionCall","name":"PrintString",'
    '"inputs":{"exec_in":"node_01.exec_out","InString":"Interactuando"},"outputs":{}}'
    "]}"
)
g = normalize_graph(json.loads(raw)) if False else None  # noqa: F841
import json

g = normalize_graph(json.loads(raw))
print("incomplete", graph_looks_incomplete(g, raw))
out = complete_if_incomplete(g, user_prompt=prompt, raw_text=raw)
print("complete_if names", [n["name"] for n in out["nodes"]] if out else None)
r = prepare_apply_payload(raw, user_prompt=prompt)
print("ok", r.get("ok"), [(n["type"], n["name"]) for n in (r.get("graph") or {}).get("nodes") or []])
