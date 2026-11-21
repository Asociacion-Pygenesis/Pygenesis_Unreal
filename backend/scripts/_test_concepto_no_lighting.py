"""Explica Sky Light… no debe ir por Lighting-Spec."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import Consulta, construir_prompt, _pide_json_lighting, _es_pregunta_tema_nuevo
from response_filters import limpiar_respuesta_modelo

q = "Explica la diferencia entre Sky Light con Realtime Capture y cubemap estático en UE5."
assert _es_pregunta_tema_nuevo(q) is True
assert _pide_json_lighting(q) is False

p = construir_prompt(Consulta(prompt=q), [])
assert "Lighting-Spec" in p or "EXPLICACIÓN" in p or "concepto" in p.lower()
assert "UNREAL_SYSTEM_LIGHT" not in p
assert "```json" not in p.split("assistant")[-1] or "PROHIBIDO JSON" in p
assert "PROHIBIDO JSON" in p or "EXPLICACIÓN" in p

# Si el modelo se equivoca y suelta Lighting-Spec, no añadir Aplicar Lighting
fake = (
    '```json\n{"environment_type":"Sky","sky_light":{"realtime_capture":true}}\n```\n'
)
clean = limpiar_respuesta_modelo(fake, user_prompt=q)
assert "Aplicar Lighting" not in clean

assert _pide_json_lighting("Configura iluminación de atardecer cálido en un desierto") is True
print("concepto no lighting OK")
