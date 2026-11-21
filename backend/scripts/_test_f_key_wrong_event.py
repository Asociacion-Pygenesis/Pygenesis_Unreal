"""Modelo emite Event_Interact: preservar (no forzar InputKey F)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from middleware.bp_lite import prepare_apply_payload

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
r = prepare_apply_payload(raw, user_prompt=prompt)
assert r.get("ok"), r
names = [(n["type"], n["name"]) for n in r["graph"]["nodes"]]
# Preservar salida del modelo — no secuestrar a InputKey F
assert any(n == "Event_Interact" for _, n in names), names
assert any(n == "PrintString" for _, n in names), names
assert not any(t == "InputKey" for t, _ in names), names
print("F Event_Interact preserved OK", names)
