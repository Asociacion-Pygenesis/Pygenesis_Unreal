"""No secuestrar: JSON Print se preserva aunque el prompt pida Launch; Launch bueno igual."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from middleware.bp_lite import prepare_apply_payload

prompt = (
    "Crea un Blueprint: al pulsar Espacio haz LaunchCharacter "
    "con velocidad (0,0,700)."
)
model_wrong = '''```json
{"graph_name":"PrintOnF","nodes":[{"id":"node_01","type":"InputKey","name":"F","inputs":{},"outputs":{"Pressed":"node_02.exec_in"}},{"id":"node_02","type":"FunctionCall","name":"PrintString","inputs":{"exec_in":"node_01.Pressed","InString":"Interactuando"},"outputs":{}}]}
```'''

r = prepare_apply_payload(model_wrong, user_prompt=prompt)
assert r.get("ok"), r
names = [n["name"] for n in r["graph"]["nodes"]]
assert "PrintString" in names
assert "LaunchCharacter" not in names
assert "SpaceBar" not in names
print("wrong Print preserved (no Launch hijack) OK")

model_ok = '''```json
{"graph_name":"Jump","nodes":[{"id":"node_01","type":"InputKey","name":"SpaceBar","inputs":{},"outputs":{"Pressed":"node_02.exec_in"}},{"id":"node_02","type":"FunctionCall","name":"LaunchCharacter","inputs":{"exec_in":"node_01.Pressed","LaunchVelocity":[0,0,700],"XYOverride":true,"ZOverride":true},"outputs":{}}]}
```'''
r2 = prepare_apply_payload(model_ok, user_prompt=prompt)
assert r2.get("ok"), r2
assert any(n["name"] == "SpaceBar" for n in r2["graph"]["nodes"])
assert any(n["name"] == "LaunchCharacter" for n in r2["graph"]["nodes"])
print("model Launch preserved OK")
