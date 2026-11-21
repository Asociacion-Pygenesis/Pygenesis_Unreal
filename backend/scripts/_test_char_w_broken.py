"""JSON basura Character W: dedupe ids; no inventar InputKey desde el prompt."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from middleware.bp_lite import prepare_apply_payload

prompt = "Crea un Blueprint Character: tecla W llama a AddMovementInput hacia adelante."
raw = '''```json
{"graph_name":"Character_W","nodes":[{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},"outputs":{}},{"id":"node_05","type":"FunctionCall","name":"AddMovementInput","inputs":{"exec_in":"node_05.Pressed","WorldDirectionVector":[1.0,0.0,0.0],"ScaleValue":1.0},"outputs":{}},{"id":"node_05","type":"FunctionCall","name":"AddMovementInput","inputs":{"exec_in":"node_05.Pressed","WorldDirectionVector":[1.0,0.0,0.0],"ScaleValue":1.0},"outputs":{}}]}
```'''

r = prepare_apply_payload(raw, user_prompt=prompt)
assert r.get("ok"), r
names = [(n["type"], n["name"]) for n in r["graph"]["nodes"]]
ids = [n["id"] for n in r["graph"]["nodes"]]
assert len(ids) == len(set(ids)), ids
assert any(n == "AddMovementInput" for _, n in names), names
# No fabricar InputKey W: el modelo no lo emitió
assert not any(t == "InputKey" for t, _ in names), names
print("CHAR W dedupe-preserve OK", json.dumps(names))
