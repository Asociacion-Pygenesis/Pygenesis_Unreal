"""Branch: normaliza JSON bueno; no fuerza Branch si el modelo puso Print."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from middleware.bp_lite import prepare_apply_payload

prompt = (
    'Crea un Blueprint: Branch tras BeginPlay; '
    'si true imprime "OK", si false "FAIL".'
)
bad = '''```json
{"graph_name":"BranchBeginPlay","nodes":[{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},"outputs":{"exec_out":"node_02.exec_in"}},{"id":"node_02","type":"FunctionCall","name":"PrintString","inputs":{"InString":"Interactuando","exec_in":"node_01.exec_out"},"outputs":{}}]}
```'''

r_bad = prepare_apply_payload(bad, user_prompt=prompt)
assert r_bad.get("ok"), r_bad
assert not any(n["type"] == "Branch" for n in r_bad["graph"]["nodes"])

good = '''```json
{"graph_name":"BranchBeginPlay","nodes":[{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},"outputs":{"exec_out":"node_02.exec_in"}},{"id":"node_02","type":"Branch","name":"Branch","inputs":{"exec_in":"node_01.exec_out","Condition":true},"outputs":{"then":"node_03.exec_in","else":"node_04.exec_in"}},{"id":"node_03","type":"FunctionCall","name":"PrintString","inputs":{"exec_in":"node_02.then","InString":"OK"},"outputs":{}},{"id":"node_04","type":"FunctionCall","name":"PrintString","inputs":{"exec_in":"node_02.else","InString":"FAIL"},"outputs":{}}]}
```'''
r = prepare_apply_payload(good, user_prompt=prompt)
assert r.get("ok"), r
assert any(n["type"] == "Branch" for n in r["graph"]["nodes"])
prints = [n for n in r["graph"]["nodes"] if n["name"] == "PrintString"]
assert {p["inputs"]["InString"] for p in prints} == {"OK", "FAIL"}
print("Branch normalize-only OK")
