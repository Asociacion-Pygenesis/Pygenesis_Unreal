"""JSON raro F→Print: clasificar InputKey/Print; no inventar InString desde basura."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from middleware.bp_lite import prepare_apply_payload

sample = r'''
```json
{
 "graph_name": "BP_Lite_PrintString",
 "nodes":
 [
 {
 "id":"node_01", 
 "type":"InputKeyNode", 
 "name":"",
 "inputs":{"Pressed":""}, 
 "outputs":{
 "ExecIn":"exec_in"
 }
 },
 
 { 
 "id": "node_02",
 "type": "FunctionCallNode",
 "name": "",
 "inputs":
 {
 "F": "{ \"InputKey\": [\"Interactuando\"] }", 
 "StringToPrint":"InString"
 }, 
 "outputs":{"ExecOut":""}
 }
 ]
}
```
'''

r = prepare_apply_payload(sample)
print("ok", r.get("ok"), r.get("summary"))
assert r["ok"], r
assert any(n["type"] == "InputKey" and n["name"] == "F" for n in r["graph"]["nodes"]), r["graph"]
pr = next(n for n in r["graph"]["nodes"] if n["name"] == "PrintString")
# No rellenar InString desde pines basura / prosa
assert pr["inputs"].get("InString") in (None, "", "InString") or "InString" in pr["inputs"]
print("OK preserve-without-invent", json.dumps(pr["inputs"], ensure_ascii=False))
