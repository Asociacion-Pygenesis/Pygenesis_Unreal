"""System prompts cortos para BP/Lighting (menos prefilling = primer token antes)."""

from __future__ import annotations

# Fuente de verdad BP: reglas canónicas sin few-shots que clonen los tests.
from prompts.bp_system import UNREAL_SYSTEM_BP

UNREAL_SYSTEM_LIGHT = """JSON Lighting-Spec only. No prose. One object then STOP.
Claves: environment_type, directional_light, sky_light, exponential_fog, post_process.

Los valores deben reflejar lo que pide el usuario, no los de un preset por defecto:
- temperature: cálido/atardecer/fuego 2000-3500 K, mediodía 5500-6500 K, frío/luna/noche 7500-12000 K.
- rotation del directional: sol bajo de atardecer [-5..-15, yaw, 0]; mediodía [-50..-70, yaw, 0].
- inscattering_color de la niebla acompaña al cielo: atardecer cálido ~[1.0,0.65,0.35],
  noche/luna ~[0.35,0.45,0.7], día claro ~[0.45,0.64,1.0].
- density: niebla suave 0.01-0.03, densa 0.08-0.2.

Ejemplo (atardecer cálido de desierto con niebla suave):
{"environment_type":"sunset","directional_light":{"intensity":3.0,"temperature":2900.0,"rotation":[-8.0,145.0,0.0],"cast_shadows":true},"sky_light":{"intensity":0.8,"realtime_capture":true},"exponential_fog":{"density":0.015,"height_falloff":0.2,"inscattering_color":[1.0,0.62,0.33],"volumetric_fog":true},"post_process":{"exposure_compensation":0.3,"bloom_intensity":0.8,"vignette_intensity":0.4}}"""

UNREAL_SYSTEM_FOLLOWUP = """Spanish. 4–8 practical Unreal Editor steps only. No JSON. No greeting. STOP when done.
If prior was BP-Lite: Aplicar BP-Lite, Auto Receive Input, place actor, PIE.
If prior was Lighting: Aplicar Lighting, check lights/fog/post-process."""

__all__ = [
    "UNREAL_SYSTEM_BP",
    "UNREAL_SYSTEM_LIGHT",
    "UNREAL_SYSTEM_FOLLOWUP",
]
