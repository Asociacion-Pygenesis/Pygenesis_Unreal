import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from middleware.lighting import prepare_lighting_payload

sample = """
Explicacion del bosque nocturno.

{"Lighting-Spec": {"environment_type": "Sky", "directional_light": [0.5, -1.2, 3], "sky_light": true,
"post_process_fog": {"density": 0.15, "fog_color": [0.4, 0.6, 0.8]},
"exponential_fog": false}}
"""

r = prepare_lighting_payload(sample)
print(json.dumps(r, indent=2, ensure_ascii=False))
assert r["ok"], r
assert r["spec"]["exponential_fog"]["density"] == 0.15
assert r["spec"]["directional_light"]["rotation"] == [0.5, -1.2, 3.0]
assert r["spec"]["sky_light"]["intensity"] == 1.0
print("OK")
