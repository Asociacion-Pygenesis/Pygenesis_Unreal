import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from middleware.bp_lite import prepare_apply_payload

raw = r'''```json
{
 "graph_name": "BP-Lite Character",
 "nodes":
 [
 {
 "id":"node_01","type":"InputActionNode", 
 "name":"W Key Pressed", 
 "inputs":{"Pressed":"/Game/Blueprints/InputActions.W"},
 "outputs":{
 "/Exec":"exec_out"
 }
 },
 { 
 "id": "node_02",
 "type":
 "FunctionCallNode","name":"AddMovementInput","description":"",
 "inputs":{"Direction":[0,1]},
 "outputs":"/Exec":"exec_in"}
 ]
}
```'''

r = prepare_apply_payload(raw)
print(r.get("error"), r.get("summary"))
assert r.get("ok"), r
names = [(n["type"], n["name"]) for n in r["graph"]["nodes"]]
print(names)
assert any(t == "InputKey" and n == "W" for t, n in names), names
assert any(n == "AddMovementInput" for _, n in names), names
mv = next(n for n in r["graph"]["nodes"] if n["name"] == "AddMovementInput")
assert "WorldDirectionVector" in mv["inputs"] or "ScaleValue" in mv["inputs"]
print("CHAR W OK", json.dumps(r["graph"], ensure_ascii=False))
