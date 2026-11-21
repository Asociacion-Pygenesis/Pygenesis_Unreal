"""JSON casi inválido Destroy: sanitize en except puede recuperar; sin plantillas."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from middleware.bp_lite import prepare_apply_payload

# JSON válido mínimo (preservar)
good = (
    '{"graph_name":"DestroyActorOnGameStart","nodes":['
    '{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},'
    '"outputs":{"exec_out":"node_02.exec_in"}},'
    '{"id":"node_02","type":"FunctionCall","name":"DestroyActor",'
    '"inputs":{"exec_in":"node_01.exec_out"},"outputs":{}}]}'
)
r = prepare_apply_payload(good)
assert r.get("ok"), r
assert any(n["name"] == "EventBeginPlay" for n in r["graph"]["nodes"])
assert any(n["name"] == "DestroyActor" for n in r["graph"]["nodes"])

# Basura con comentarios/keys rotas: no exigir reparación mágica
broken = r'''
{"graph_name": "DestroyActorOnGameStart",
"nodes":
[
 {
 "id":"node_01",
 "type":"Event Graph Node",
 "name":"",
 "inputs":{"Trigger:Event BeginPlay"},
 "outputs":{
 "Exec:None"
 }
 }
]}.
'''
r2 = prepare_apply_payload(broken)
# Si parsea, preservar; si no, error claro — nunca inventar cadena completa
if r2.get("ok"):
    assert any("BeginPlay" in str(n.get("name")) or n.get("type") == "Event" for n in r2["graph"]["nodes"])
else:
    assert r2.get("error")
print("Destroy preserve/error contract OK", r2.get("ok"), r2.get("error"))
