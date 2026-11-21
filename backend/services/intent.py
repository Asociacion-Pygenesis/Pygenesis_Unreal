"""Intent routing: greeting, follow-up, BP/Lighting vs concept."""

from __future__ import annotations

import re

_REVIEW_QUESTION_RE = re.compile(
    r"(?:"
    r"qu[eé]\s+(?:deber[ií]a|tengo\s+que|conviene|hay\s+que)\s+revisar"
    r"|qu[eé]\s+revisar"
    r"|revisar\s+(?:en|aqu[ií]|ac[aá])"
    r"|por\s+d[oó]nde\s+(?:empiezo|empezar|arrancar)"
    r"|checklist"
    r"|qu[eé]\s+mirar"
    r")",
    re.IGNORECASE,
)


def _es_pregunta_revision(prompt: str) -> bool:
    return bool(_REVIEW_QUESTION_RE.search(prompt))


_GREETING_RE = re.compile(
    r"^\s*(?:"
    r"hola+|hey+|hi+|hello+|buenas(?:\s+tardes|\s+noches|\s+d[ií]as)?|"
    r"qu[eé]\s+tal|c[oó]mo\s+est[aá]s|gracias|thanks|"
    r"qu[eé]\s+puedes\s+hacer|qui[eé]n\s+eres|help"
    r")\s*[!?.]*\s*$",
    re.IGNORECASE,
)


def _es_saludo_o_casual(prompt: str) -> bool:
    text = (prompt or "").strip()
    if len(text) <= 40 and _GREETING_RE.match(text):
        return True
    return False


def _es_afirmacion_corta(prompt: str) -> bool:
    """Sí / vale / ok tras la pregunta '¿Quieres que te explique…?'."""
    t = (prompt or "").strip().lower()
    if not t or len(t) > 48:
        return False
    return bool(
        re.fullmatch(
            r"(?:"
            r"s[ií]"
            r"|s[ií]\s+por\s+favor"
            r"|vale"
            r"|ok"
            r"|okay"
            r"|claro"
            r"|dale"
            r"|yes"
            r"|yep"
            r"|de\s+acuerdo"
            r"|por\s+favor"
            r"|expl[ií]ca(?:me)?"
            r"|quiero(?:\s+la)?\s+explicaci[oó]n"
            r")\.?",
            t,
        )
    )


def _prev_tiene_json_estructurado(prev: str) -> bool:
    p = prev or ""
    return '"graph_name"' in p or '"environment_type"' in p


def _es_pregunta_tema_nuevo(prompt: str) -> bool:
    """
    Pregunta de concepto nueva (no «explícame lo anterior»).
    Evita que «Explica la diferencia entre Sky Light…» dispare la explicación
    determinista del último BP-Lite.
    """
    p = (prompt or "").strip()
    if not p:
        return False
    if re.search(
        r"(?:"
        r"expl[ií]ca(?:me)?\s+(?:la\s+)?(?:diferencia|ventaja|relaci[oó]n|distinci[oó]n)"
        r"|expl[ií]ca(?:me)?\s+(?:qu[eé]\s+es|c[oó]mo\s+funciona|por\s+qu[eé])"
        r"|diferencia\s+entre"
        r"|qu[eé]\s+(?:diferencia|es|significa)\s+"
        r"|c[oó]mo\s+funciona\s+"
        r")",
        p,
        re.IGNORECASE,
    ):
        return True
    # «Explica <tema largo>» sin deícticos al turno anterior
    if re.search(r"^expl[ií]ca(?:me)?\s+\S+", p, re.IGNORECASE):
        if not re.search(
            r"\b(?:"
            r"esto|eso|lo\s+anterior|el\s+resultado|"
            r"el\s+(?:blueprint|grafo|json|bp)|"
            r"c[oó]mo\s+(?:usarlo|aplicarlo|probarlo)|"
            r"m[aá]s\s+(?:detalle|detalles)"
            r")\b",
            p,
            re.IGNORECASE,
        ):
            if len(re.findall(r"\w+", p, flags=re.UNICODE)) >= 6:
                return True
    return False


def _es_seguimiento_uso(prompt: str, prev: str = "") -> bool:
    """Follow-up: sí / explícame esto / cómo usarlo — solo tras JSON BP/luz previo."""
    if not prompt:
        return False
    if _es_pregunta_tema_nuevo(prompt):
        return False
    if _es_afirmacion_corta(prompt) and _prev_tiene_json_estructurado(prev):
        return True
    # Sin JSON previo no hay «explicación del grafo» que reutilizar
    if not _prev_tiene_json_estructurado(prev):
        return False
    return bool(
        re.search(
            r"(?:"
            r"expl[ií]ca(?:me)?(?:\s+(?:esto|eso|lo\s+anterior|el\s+blueprint|m[aá]s))?\s*$"
            r"|expl[ií]ca(?:me)?\s+(?:c[oó]mo\s+)?(?:usarlo|aplicarlo|probarlo)"
            r"|c[oó]mo\s+(?:lo\s+)?(?:uso|usar|aplico|aplicar|pruebo|probar)"
            r"|c[oó]mo\s+usarlo"
            r"|qu[eé]\s+(?:hago|hago\s+ahora|sigo)"
            r"|para\s+qu[eé]\s+sirve"
            r"|no\s+entiendo"
            r"|detalla(?:me)?(?:\s+esto)?\s*$"
            r"|quiero(?:\s+que)?\s+(?:me\s+)?expliqu"
            r")",
            prompt,
            re.IGNORECASE,
        )
    )


_LIGHTING_INTENT_RE = re.compile(
    r"\b(?:iluminaci[oó]n|lighting|atm[oó]sfera|niebla|fog|lumen|"
    r"post\s*process|directional\s*light|sky\s*light|atardecer|"
    r"cyberpunk|noche|bosque|luna|preset\s+de\s+luz|"
    r"cubemap|realtime\s*capture)\b",
    re.IGNORECASE,
)
_GRAPH_INTENT_RE = re.compile(
    r"\b(?:crea|crear|monta|genera|blueprint|bp-lite|launchcharacter|"
    r"event\s*graph|nodo|jump|grafo|printstring|pulsar|tecla)\b",
    re.IGNORECASE,
)
_GENERA_LIGHTING_RE = re.compile(
    r"\b(?:configura|configurar|crea|crear|monta|genera|aplicar|aplica|"
    r"preset|ajusta|ajustar|pon(?:me)?|haz(?:me)?)\b",
    re.IGNORECASE,
)


def _pide_json_lighting(prompt: str) -> bool:
    """True solo si pide generar/aplicar Lighting-Spec, no si pregunta concepto."""
    if not prompt or _es_pregunta_tema_nuevo(prompt):
        return False
    if not _LIGHTING_INTENT_RE.search(prompt):
        return False
    # «explica / diferencia / qué es» ya filtrado; exige verbo de acción o preset
    if _GENERA_LIGHTING_RE.search(prompt):
        return True
    # Frases tipo «iluminación de atardecer…» sin «explica»
    if re.search(
        r"\b(?:iluminaci[oó]n|lighting|atm[oó]sfera|preset)\b",
        prompt,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:expl[ií]ca|diferencia|qu[eé]\s+es|c[oó]mo\s+funciona)\b",
        prompt,
        re.IGNORECASE,
    ):
        return True
    return False


def _pide_json_bp(prompt: str) -> bool:
    if not prompt or _es_pregunta_tema_nuevo(prompt):
        return False
    return bool(_GRAPH_INTENT_RE.search(prompt))

