"""Smoke: preserve paths + health + token_budget."""
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from middleware.bp_grammar import BP_LITE_GBNF
from middleware.bp_lite import prepare_apply_payload

assert "ws ::= [" in BP_LITE_GBNF and "]*" in BP_LITE_GBNF

cases = {
    "F": (
        '{"graph_name":"FPrint","nodes":['
        '{"id":"node_01","type":"InputKey","name":"F","inputs":{},'
        '"outputs":{"Pressed":"node_02.exec_in"}},'
        '{"id":"node_02","type":"FunctionCall","name":"PrintString",'
        '"inputs":{"exec_in":"node_01.Pressed","InString":"Interactuando"},"outputs":{}}]}'
    ),
    "Delay": (
        '{"graph_name":"D","nodes":['
        '{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},'
        '"outputs":{"exec_out":"node_02.exec_in"}},'
        '{"id":"node_02","type":"FunctionCall","name":"Delay",'
        '"inputs":{"exec_in":"node_01.exec_out","Duration":2.0},'
        '"outputs":{"exec_out":"node_03.exec_in"}},'
        '{"id":"node_03","type":"FunctionCall","name":"PrintString",'
        '"inputs":{"exec_in":"node_02.exec_out","InString":"Listo"},"outputs":{}}]}'
    ),
    "W": (
        '{"graph_name":"W","nodes":['
        '{"id":"node_01","type":"InputKey","name":"W","inputs":{},'
        '"outputs":{"Pressed":"node_02.exec_in"}},'
        '{"id":"node_02","type":"FunctionCall","name":"AddMovementInput",'
        '"inputs":{"exec_in":"node_01.Pressed","WorldDirectionVector":[1,0,0],'
        '"ScaleValue":1.0},"outputs":{}}]}'
    ),
    "Launch": (
        '{"graph_name":"J","nodes":['
        '{"id":"node_01","type":"InputKey","name":"SpaceBar","inputs":{},'
        '"outputs":{"Pressed":"node_02.exec_in"}},'
        '{"id":"node_02","type":"FunctionCall","name":"LaunchCharacter",'
        '"inputs":{"exec_in":"node_01.Pressed","LaunchVelocity":[0,0,700],'
        '"XYOverride":true,"ZOverride":true},"outputs":{}}]}'
    ),
}

for name, raw in cases.items():
    r = prepare_apply_payload(raw, user_prompt=name)
    assert r.get("ok"), (name, r)
    print(name, "OK", [n["name"] for n in r["graph"]["nodes"]])

try:
    health = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=10).read().decode()
    print("health", health[:180])
except OSError as exc:
    print(f"health omitido (backend no levantado): {exc}")

# El presupuesto de tokens vive en el runner de jobs desde el split de main.py
src = (ROOT / "backend" / "services" / "job_runner.py").read_text(encoding="utf-8")
assert "OLLAMA_BP_MAX_TOKENS" in src
from config import OLLAMA_BP_MAX_TOKENS, OLLAMA_BP_TEMPERATURE

assert OLLAMA_BP_MAX_TOKENS >= 1280
assert abs(OLLAMA_BP_TEMPERATURE - 0.25) < 1e-6
print("SMOKE OK")
