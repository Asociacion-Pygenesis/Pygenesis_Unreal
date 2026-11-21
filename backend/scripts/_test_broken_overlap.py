import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from middleware.bp_lite import extract_bplite_from_text, prepare_apply_payload

sample = r'''
```json
{
 "graph_name": "OverlapEvent",
 "nodes":
 [
 {
 "id":"node_01","type":"Get All Overlapping Actors", 
 "name":"","inputs":{"ActorClass":""},outputs:{}
 },
 { "id":"node_02","type":"Print String", 
 "name":"",
 inputs:{"String": ""},
 outputs:{} }
 ]
}

```

Para crear este Blueprint, sigue estos pasos...
Recuerda que el nodo Get All Overlapping Actors... en lugar del evento ActorBeginOverlap.
'''

g = extract_bplite_from_text(sample)
print(json.dumps(g, indent=2, ensure_ascii=False))
r = prepare_apply_payload(sample)
print("ok", r.get("ok"), r.get("error"))
print(r.get("summary"))
assert r.get("ok"), r
names = {n["name"] for n in r["graph"]["nodes"]}
assert "EventActorBeginOverlap" in names, names
assert "PrintString" in names, names
pr = next(n for n in r["graph"]["nodes"] if n["name"] == "PrintString")
# El nodo venía con String:"" y sin name: el middleware ya no inventa el texto,
# solo garantiza que el pin exista para que el usuario lo rellene en el Editor.
assert "InString" in pr["inputs"], pr["inputs"]
ev = next(n for n in r["graph"]["nodes"] if n["name"] == "EventActorBeginOverlap")
assert "node_02" in str(ev.get("outputs", {}))
print("OVERLAP OK")
