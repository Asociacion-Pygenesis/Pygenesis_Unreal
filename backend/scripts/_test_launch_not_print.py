"""JSON Print + prompt Launch: preservar Print (sin repair a Launch)."""
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
bad = '''```json
{"graph_name":"PrintOnF","nodes":[{"id":"node_01","type":"InputKey","name":"F","inputs":{},"outputs":{"Pressed":"node_02.exec_in"}},{"id":"node_02","type":"FunctionCall","name":"PrintString","inputs":{"exec_in":"node_01.Pressed","InString":"Interactuando"},"outputs":{}}]}
```'''

r = prepare_apply_payload(bad, user_prompt=prompt)
assert r.get("ok"), r
names = [n["name"] for n in r["graph"]["nodes"]]
assert "PrintString" in names
assert "LaunchCharacter" not in names
print("Print preserved (no Launch repair) OK", names)
