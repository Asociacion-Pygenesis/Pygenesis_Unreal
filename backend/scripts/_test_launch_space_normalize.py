"""Launch mal formado del modelo: normalizar pines/tipos; no inventar si ya hay nodos."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from middleware.bp_lite import prepare_apply_payload
from response_filters import explicacion_determinista

# JSON canónico bueno (preservar SpaceBar→Launch)
raw = r'''```json
{"graph_name":"LaunchCharacterOnSpace","nodes":[{"id":"node_01","type":"InputKey","name":"SpaceBar","inputs":{},"outputs":{"Pressed":"node_02.exec_in"}},{"id":"node_02","type":"FunctionCall","name":"LaunchCharacter","inputs":{"exec_in":"node_01.Pressed","LaunchVelocity":[0.0,0.0,700.0],"XYOverride":true,"ZOverride":true},"outputs":{}}]}
```'''

r = prepare_apply_payload(raw)
assert r.get("ok"), r
names = [(n["type"], n["name"]) for n in r["graph"]["nodes"]]
print("nodes:", names)
assert any(t == "InputKey" and n == "SpaceBar" for t, n in names), names
assert any(n == "LaunchCharacter" for _, n in names), names
assert not any(n == "PrintString" for _, n in names), names
launch = next(n for n in r["graph"]["nodes"] if n["name"] == "LaunchCharacter")
assert launch["inputs"]["LaunchVelocity"] == [0.0, 0.0, 700.0], launch["inputs"]
ik = next(n for n in r["graph"]["nodes"] if n["type"] == "InputKey")
assert ik["outputs"].get("Pressed") == f"{launch['id']}.exec_in", ik
assert launch["inputs"].get("exec_in") == f"{ik['id']}.Pressed", launch["inputs"]

exp = explicacion_determinista(raw)
assert exp is not None
assert "LaunchCharacter" in exp
assert "PrintString" not in exp
print("explain OK:\n", exp)
print(json.dumps(r["graph"], ensure_ascii=False))
