"""BeginPlay→Delay→Print: truncado→error; completo→preservar."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from middleware.bp_lite import prepare_apply_payload

prompt = 'Crea un Blueprint: BeginPlay → Delay 2s → PrintString "Listo".'
# Un solo BeginPlay completo (JSON válido) — se preserva, no se completa a Delay+Print
incomplete = (
    '```json\n{"graph_name":"BP_Listo","nodes":['
    '{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},"outputs":{}}'
    "]}\n```"
)

r_inc = prepare_apply_payload(incomplete, user_prompt=prompt)
assert r_inc.get("ok"), r_inc
assert [n["name"] for n in r_inc["graph"]["nodes"]] == ["EventBeginPlay"]

good = '''```json
{"graph_name":"BP_Listo","nodes":[{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},"outputs":{"exec_out":"node_02.exec_in"}},{"id":"node_02","type":"FunctionCall","name":"Delay","inputs":{"exec_in":"node_01.exec_out","Duration":2.0},"outputs":{"exec_out":"node_03.exec_in"}},{"id":"node_03","type":"FunctionCall","name":"PrintString","inputs":{"exec_in":"node_02.exec_out","InString":"Listo"},"outputs":{}}]}
```'''
r = prepare_apply_payload(good, user_prompt=prompt)
assert r.get("ok"), r
assert [n["name"] for n in r["graph"]["nodes"]] == [
    "EventBeginPlay",
    "Delay",
    "PrintString",
]
assert r["graph"]["nodes"][1]["inputs"]["Duration"] == 2.0
print("BeginPlay+Delay OK")
