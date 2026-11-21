"""Filtros post-proceso para respuestas del modelo (thinking, bucles, etc.)."""

from __future__ import annotations

import re

_THINKING_BLOCK_RE = re.compile(
    r"<think>.*?</think>",
    re.DOTALL | re.IGNORECASE,
)

_FUENTE_LINE_RE = re.compile(
    r"^\s*\[Fuente(?:\s+manual)?\s*:[^\]]+\]\s*",
    re.IGNORECASE | re.MULTILINE,
)

_INSTRUCTION_ECHO_RE = re.compile(
    r"(?:"
    r"[Ss]i no sabes(?:\s+algo|\s+qu[eé]\s+hacer)?,\s*dilo abiertamente[^.!]*[.!]?\s*"
    r"|sin inventar\s*[!.]?\s*"
    r"|\(y si (?:quieres|pides)[^)]*\)\s*"
    r"|PROHIBIDO JSON[^.]*[.!]?\s*"
    r"|genera(?:r)?\s+JSON\s+BP-Lite[^.]*[.!]?\s*"
    r")",
    re.IGNORECASE,
)

_FIRST_FENCE_RE = re.compile(r"```(?:json)?\s*[\s\S]*?```", re.IGNORECASE)
_FENCE_OPEN_RE = re.compile(r"```(?:json)?\s*", re.IGNORECASE)

# Cierres / firmas que el modelo añade y alargan la respuesta sin valor
_FAREWELL_START_RE = re.compile(
    r"(?:"
    r"Espero que esto te ayude"
    r"|Si tienes alguna pregunta adicional"
    r"|no dudes en preguntar"
    r"|Un saludo desde"
    r"|Saludos desde Pygenesis"
    r"|Si el JSON BP-Lite es demasiado grande"
    r"|🙂|😊"
    r")",
    re.IGNORECASE,
)


def filtrar_thinking(texto: str) -> str:
    """Elimina bloques de thinking sin vaciar la respuesta útil."""
    if not texto:
        return texto
    texto = _THINKING_BLOCK_RE.sub("", texto)
    if "</think>" in texto:
        before, _, after = texto.partition("</think>")
        after = after.strip()
        before = before.strip()
        if after and len(after) >= max(40, len(before) // 5):
            texto = after
        else:
            texto = before or after
    texto = re.sub(r"<think>\s*", "", texto, flags=re.IGNORECASE)
    return texto.strip()


def limpiar_citas_fuente(texto: str) -> str:
    texto = texto.strip()
    while True:
        nuevo = _FUENTE_LINE_RE.sub("", texto, count=1)
        if nuevo == texto:
            break
        texto = nuevo.strip()
    return texto.strip()


def limpiar_eco_instrucciones(texto: str) -> str:
    texto = _INSTRUCTION_ECHO_RE.sub(" ", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _first_closed_fence_end(texto: str) -> int | None:
    m = _FIRST_FENCE_RE.search(texto)
    return m.end() if m else None


def _find_prose_echo_start(texto: str, start_search: int) -> int | None:
    """
    (1) Localiza el inicio de la 2.ª copia del eco, no un match a medias.

    Busca el sufijo más largo que ya apareció antes y lo expande hacia la
    izquierda mientras coincida → corte en la ancla del bucle.
    """
    body_len = len(texto) - start_search
    if body_len < 80:
        return None
    min_l, max_l = 40, min(400, body_len // 2)
    best_echo2: int | None = None
    best_len = 0
    # Sufijos más largos primero (mejor ancla)
    for length in range(max_l, min_l - 1, -10):
        suffix = texto[-length:]
        if len(suffix.strip()) < length * 0.7:
            continue
        prev = texto[start_search:-length]
        pos = prev.find(suffix)
        if pos < 0:
            continue
        echo1 = start_search + pos
        echo2 = len(texto) - length
        # Expandir a la izquierda sin solapar las dos copias
        # (si solapan, echo2 cae al inicio de la 1.ª copia y nos comemos el bloque útil)
        while echo1 > start_search and echo2 > echo1:
            if texto[echo1 - 1] != texto[echo2 - 1]:
                break
            new1, new2 = echo1 - 1, echo2 - 1
            new_len = len(texto) - new2
            if new1 + new_len > new2:
                break
            echo1, echo2 = new1, new2
        matched = len(texto) - echo2
        if matched > best_len and echo1 + matched <= echo2:
            best_len = matched
            best_echo2 = echo2
        if matched >= 80 and best_echo2 is not None:
            break
    return best_echo2


def _snap_cut_to_boundary(texto: str, echo_start: int, floor: int) -> int:
    """
    (4) Si el eco cae a mitad de frase, retrocede al último .!? o fin de línea.

    Si ya empieza en límite de línea/párrafo, no tocar (conserva el bloque útil).
    """
    if echo_start <= floor:
        return max(echo_start, floor)
    # Eco en inicio de línea / tras whitespace de párrafo → corte limpio
    i = echo_start
    while i > floor and texto[i - 1] in " \t":
        i -= 1
    if i > floor and texto[i - 1] == "\n":
        return i

    # A mitad de frase: snap corto (<=120) al último cierre de frase o línea
    region_from = max(floor, echo_start - 120)
    region = texto[region_from:echo_start]
    best = -1
    for m in re.finditer(r"[.!?…][\"'»)\]]*\s+", region):
        best = m.end()
    if best >= 0:
        return region_from + best
    nl = region.rfind("\n")
    if nl >= 0:
        return region_from + nl
    return echo_start


def _farewell_cut_index(texto: str) -> int | None:
    """Corta despedidas / firmas tras el JSON+explicación útil."""
    fence_end = _first_closed_fence_end(texto) or 0
    after_len = len(texto) - fence_end
    # No cortar si la explicación aún es corta (evita truncar el paso 3 a medias)
    if after_len < 280:
        return None
    m = _FAREWELL_START_RE.search(texto)
    if not m:
        return None
    if m.start() >= max(fence_end, int(len(texto) * 0.45)):
        return m.start()
    return None


def _repetition_echo_start(texto: str) -> int | None:
    """Índice crudo donde empieza el bucle (sin snap). None si no hay bucle."""
    farewell = _farewell_cut_index(texto)
    if farewell is not None:
        return farewell

    fence_end = _first_closed_fence_end(texto)

    # Segundo JSON real SOLO después del primer bloque cerrado.
    if fence_end is not None:
        after = texto[fence_end:]
        m = re.search(r"```(?:json)?\s*\{", after, re.IGNORECASE)
        if m:
            return fence_end + m.start()
        m = re.search(r"\{\s*\"(?:graph_name|environment_type)\"", after)
        if m:
            return fence_end + m.start()

    # Sin fence cerrado: JSON duplicado a medias
    if texto.count('"graph_name"') >= 2 and texto.count('"nodes"') >= 2:
        first = texto.find('"graph_name"')
        second = texto.find('"graph_name"', first + 12)
        if second > 0:
            window = texto[max(0, second - 40) : second]
            if "{" in window or "```" in window:
                return second

    start_search = fence_end if fence_end is not None else 0
    echo = _find_prose_echo_start(texto, start_search)
    if echo is not None:
        return echo

    # Misma línea larga repetida 3+ veces al final
    lines = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    if len(lines) >= 4:
        last = lines[-1]
        if len(last) >= 40 and lines[-3:] == [last, last, last]:
            found = 0
            search_from = len(texto)
            second_pos = -1
            for _ in range(3):
                pos = texto.rfind(last, 0, search_from)
                if pos < 0:
                    break
                found += 1
                search_from = pos
                if found == 2:
                    second_pos = pos
            if found >= 3 and second_pos > 0:
                return second_pos

    return None


def _repetition_cut_index(texto: str) -> int | None:
    """Índice de corte limpio: ancla del eco + snap a párrafo/frase."""
    echo = _repetition_echo_start(texto)
    if echo is None:
        return None
    floor = _first_closed_fence_end(texto) or 0
    # No pisar el JSON
    if echo <= floor:
        return echo
    return _snap_cut_to_boundary(texto, echo, floor)


def _structured_json_object_span(texto: str) -> tuple[int, int] | None:
    """
    Span [start, end) del objeto JSON BP/Lighting (tras ```json o al inicio).
    No exige el ``` de cierre — así paramos antes del eco de instrucciones.
    """
    if not texto:
        return None
    m = _FENCE_OPEN_RE.search(texto)
    if m:
        rel = _balanced_json_prefix_end(texto[m.end() :])
        if rel is None:
            return None
        start = m.end()
        end = m.end() + rel
        chunk = texto[start:end]
        if '"graph_name"' in chunk or '"environment_type"' in chunk:
            return start, end
        return None
    end = _balanced_json_prefix_end(texto)
    if end is None:
        return None
    chunk = texto[:end]
    if '"graph_name"' in chunk or '"environment_type"' in chunk:
        return 0, end
    return None


def _structured_json_fence_closed(texto: str) -> bool:
    """True si ya hay JSON estructurado completo (fence cerrado o objeto balanceado)."""
    if _structured_json_object_span(texto) is not None:
        return True
    m = _FIRST_FENCE_RE.search(texto or "")
    if not m:
        return False
    body = m.group(0)
    return '"graph_name"' in body or '"environment_type"' in body


def _fence_desde_objeto(obj_text: str) -> str:
    body = (obj_text or "").strip().rstrip(".")
    return f"```json\n{body}\n```"


_FILLER_WORDS = frozenset(
    {
        "the",
        "and",
        "a",
        "an",
        "is",
        "of",
        "to",
        "but",
        "also",
        "not",
        "as",
        "be",
        "have",
        "been",
        "are",
        "or",
        "if",
        "it",
        "this",
        "that",
        "for",
        "with",
        "on",
        "in",
        "by",
        "was",
        "were",
        "from",
        "at",
    }
)
_COMMA_THE_RE = re.compile(r",\s*the\b", re.IGNORECASE)
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(")
_DASH_GAP_RE = re.compile(r" - ")


def _window_is_filler(window: str) -> bool:
    """Cola de colapso: «the, the, the» sin contenido. No es un JSON ni prosa útil."""
    words = re.findall(r"[A-Za-z']+", window or "")
    if len(words) < 16:
        return False
    low = [w.lower() for w in words]
    the_count = low.count("the")
    ratio = sum(w in _FILLER_WORDS for w in low) / len(low)
    comma_the = len(_COMMA_THE_RE.findall(window))
    if comma_the >= 4 and the_count >= 6:
        return True
    return the_count >= 8 and ratio >= 0.55


def _is_symbol_spam(texto: str) -> bool:
    """Imagen markdown o una cola de « -  -  - ». Un -400 dentro del JSON no cuenta."""
    if not texto:
        return False
    tail = texto[-180:]
    if _MD_IMAGE_RE.search(texto) and tail.count("-") >= 4:
        return True
    if len(_DASH_GAP_RE.findall(tail)) >= 8:
        return True
    dashes = tail.count("-")
    letters = len(re.findall(r"[A-Za-z]", tail))
    return dashes >= 24 and dashes > letters * 2


def _help_key_cut(texto: str) -> int | None:
    """Clave basura «help» / «helpmethodteamteam…». El JSON sigue abierto y el eco no corta."""
    if not texto:
        return None
    match = re.search(r'"help(?:method|type|team)*[a-z]*"\s*:', texto, re.IGNORECASE)
    if match is None:
        match = re.search(r"teamteam", texto, re.IGNORECASE)
    if match is None:
        return None
    quote = texto.rfind('"', 0, match.start() + 1)
    return quote if quote >= 0 else match.start()


def is_degenerate_filler(texto: str) -> bool:
    """True si la cola es relleno: «the, the», guiones o claves help que crecen."""
    if not texto:
        return False
    if _is_symbol_spam(texto) or _help_key_cut(texto) is not None:
        return True
    if len(texto) < 80:
        return False
    return _window_is_filler(texto[-240:])


def degenerate_cut_index(texto: str) -> int | None:
    """Dónde empieza el relleno. None si la cola aún es texto normal."""
    help_at = _help_key_cut(texto)
    if help_at is not None:
        return help_at
    if _is_symbol_spam(texto):
        image = _MD_IMAGE_RE.search(texto)
        if image:
            return image.start()
        dashes = _DASH_GAP_RE.search(texto)
        if dashes:
            return dashes.start()
        return max(0, len(texto) - 180)
    if not is_degenerate_filler(texto):
        return None
    limit = max(1, len(texto) - 80)
    for start in range(0, limit, 16):
        if _window_is_filler(texto[start : start + 240]):
            return start
    return max(0, len(texto) - 240)


def _prose_after_graph_cut(texto: str) -> int | None:
    """Índice donde empieza una explicación fuera del JSON.

    Las claves van entre comillas. Una palabra suelta (El, Para, Esta…) es prosa
    y no debe seguir generando: la explicación corta la pone el filtro.
    """
    if not texto or '"graph_name"' not in texto or '"nodes"' not in texto:
        return None
    depth = 0
    in_str = False
    escape = False
    started = False
    i = 0
    n = len(texto)
    while i < n:
        ch = texto[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == "[":
            if started:
                depth += 1
        elif ch == "]":
            depth = max(0, depth - 1)
        elif started and ch.isalpha():
            word = re.match(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]+", texto[i:])
            token = word.group(0).lower() if word else ""
            if token not in {"true", "false", "null"}:
                return i
        i += 1
    return None


def _bp_json_still_open(texto: str) -> bool:
    """Grafo BP empezado y sin cerrar. Sus nodos repiten claves; eso no es un eco."""
    if not texto or '"graph_name"' not in texto or '"nodes"' not in texto:
        return False
    start = texto.find("{")
    if start < 0:
        return False
    return _balanced_json_prefix_end(texto[start:]) is None


def should_stop_generation(texto: str) -> bool:
    """Para con JSON completo, eco, o un bucle de relleno. Un JSON a medias sigue.

    Un segundo AIMoveTo repite type/name/exec_in del primero. Mientras el
    objeto no haya cerrado, esa repetición es el grafo, no un bucle.
    """
    if not texto:
        return False
    if _structured_json_object_span(texto) is not None:
        return True
    if _structured_json_fence_closed(texto):
        return True
    if is_degenerate_filler(texto):
        return True
    if _prose_after_graph_cut(texto) is not None:
        return True
    if _bp_json_still_open(texto):
        return False
    return _repetition_echo_start(texto) is not None


def truncate_repetition(texto: str, user_prompt: str = "") -> str:
    """Corta eco y repetición. No reescribe el grafo: eso solo ocurre al aplicar."""
    _ = user_prompt
    if not texto:
        return texto
    structured = False
    prose_at = _prose_after_graph_cut(texto)
    if prose_at is not None and prose_at > 0:
        texto = texto[:prose_at].rstrip().rstrip(",")
    span = _structured_json_object_span(texto)
    if span is not None:
        texto = _fence_desde_objeto(texto[span[0] : span[1]])
        structured = True
    elif _structured_json_fence_closed(texto):
        m = _FIRST_FENCE_RE.search(texto)
        if m:
            # Recortar basura dentro del fence (tras el objeto balanceado)
            inner = m.group(0)
            open_m = _FENCE_OPEN_RE.match(inner)
            if open_m:
                rel = _balanced_json_prefix_end(inner[open_m.end() :])
                if rel is not None:
                    texto = _fence_desde_objeto(inner[open_m.end() : open_m.end() + rel])
                    structured = True
                else:
                    texto = texto[: m.end()].rstrip()
                    structured = True
    cut = degenerate_cut_index(texto)
    if cut is None:
        cut = _repetition_cut_index(texto)
    if cut is not None and cut > 0:
        texto = texto[:cut].rstrip()
    elif cut == 0:
        texto = ""
    if not structured and not _structured_json_fence_closed(texto):
        texto = re.sub(r"\n?```(?:json)?\s*$", "", texto, flags=re.IGNORECASE).rstrip()
    return texto.rstrip()


def _base_structured_fence(texto: str) -> str | None:
    """Devuelve solo el fence/objeto JSON estructurado, o None si incompleto."""
    if not texto or not texto.strip():
        return None
    has_bp = '"graph_name"' in texto
    has_light = '"environment_type"' in texto
    if not has_bp and not has_light:
        return None
    m = _FIRST_FENCE_RE.search(texto)
    if m:
        return texto[: m.end()].rstrip()
    end = _balanced_json_prefix_end(texto)
    if end is None:
        return None
    fence_body = texto[:end]
    if '"graph_name"' not in fence_body and '"environment_type"' not in fence_body:
        return None
    return fence_body.rstrip()


def asegurar_explicacion_aplicar(texto: str) -> str:
    """Tras BP/Lighting JSON cerrado: JSON limpio + explicación corta (sin pregunta)."""
    base = _base_structured_fence(texto)
    if base is None:
        return (texto or "").rstrip()
    # Quitar oferta antigua si el modelo o un turno previo la coló
    resto = texto[len(base) :] if texto.startswith(base) else ""
    if re.search(r"aplicar bp-lite|aplicar lighting|cadena esperada", resto, re.I):
        # Ya hay explicación útil tras el fence
        cleaned_rest = re.sub(
            r"\n*\s*¿?Quieres que te explique[^\n]*",
            "",
            resto,
            flags=re.IGNORECASE,
        ).strip()
        return (base + ("\n\n" + cleaned_rest if cleaned_rest else "")).rstrip()

    expl = explicacion_determinista(base)
    if not expl:
        return base
    return base + "\n\n" + expl


# Alias por si algún test/script antiguo importa el nombre previo
def asegurar_pregunta_aplicar(texto: str) -> str:
    return asegurar_explicacion_aplicar(texto)


def limpiar_despedidas(texto: str) -> str:
    cut = _farewell_cut_index(texto)
    if cut is not None and cut > 0:
        return texto[:cut].rstrip()
    return texto


def _balanced_json_prefix_end(texto: str) -> int | None:
    """Si el texto empieza con `{...}` balanceado, devuelve el índice tras el cierre."""
    i = 0
    n = len(texto)
    while i < n and texto[i].isspace():
        i += 1
    if i >= n or texto[i] != "{":
        return None
    depth = 0
    in_str = False
    escape = False
    for j in range(i, n):
        ch = texto[j]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                while end < n and texto[end] in " \t\r\n.":
                    end += 1
                return end
    return None


def _strip_structured_json_blocks(texto: str) -> str:
    """Quita fences/objetos BP-Lite o Lighting-Spec (para respuestas de explicación)."""
    if not texto:
        return texto
    # Fences ```json ... ```
    texto = re.sub(
        r"```(?:json)?\s*[\s\S]*?```",
        "",
        texto,
        flags=re.IGNORECASE,
    )
    # Objeto JSON suelto al inicio (anidado; el modelo a veces lo repite sin fence)
    end = _balanced_json_prefix_end(texto)
    if end is not None and (
        '"graph_name"' in texto[:end] or '"environment_type"' in texto[:end]
    ):
        texto = texto[end:]
    # Restos rotos tipo `]}.` tras un strip parcial
    texto = re.sub(r"^\s*[\]\},]+\s*\.?\s*", "", texto)
    # Pregunta de oferta si se coló
    texto = re.sub(
        r"\n*\s*¿?Quieres que te explique[^\n]*\n?",
        "\n",
        texto,
        flags=re.IGNORECASE,
    )
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def limpiar_respuesta_followup(texto: str) -> str:
    """Explicación bajo demanda: prosa útil, sin JSON ni re-pregunta."""
    original = texto or ""
    texto = filtrar_thinking(original)
    texto = limpiar_citas_fuente(texto)
    texto = limpiar_eco_instrucciones(texto)
    texto = limpiar_despedidas(texto)
    texto = _strip_structured_json_blocks(texto)
    # Si tras quitar JSON no queda nada, no recuperar el JSON (el Apply usa el turno anterior)
    if not texto.strip():
        return (
            "Aquí tienes los pasos: crea o abre el Blueprint, cablea los nodos "
            "según el grafo, compila, coloca el Actor en el nivel y prueba en PIE."
        )
    return texto.strip()


def _explicacion_desde_grafo(graph: dict) -> str:
    """Pasos genéricos + verificación según nodos reales del grafo."""
    nodes = graph.get("nodes") or []
    lines = [
        "1. Pulsa **Aplicar BP-Lite** en la ventana Pygenesis (crea el asset en `/Game/Pygenesis`).",
        "2. Abre ese Blueprint en el Content Browser y revisa el Event Graph.",
    ]
    chain: list[str] = []
    needs_input = False
    has_branch = False
    print_msgs: list[str] = []
    verify = "Play (PIE) y comprueba el resultado en pantalla/log."
    for n in nodes:
        ntype = str(n.get("type") or "")
        name = str(n.get("name") or "")
        inns = n.get("inputs") or {}
        if ntype == "InputKey":
            needs_input = True
            chain.append(f"InputKey **{name}**")
        elif "BeginPlay" in name:
            chain.append("**Event BeginPlay**")
        elif "Overlap" in name:
            chain.append("**ActorBeginOverlap**")
        elif ntype == "Branch" or name == "Branch":
            has_branch = True
            chain.append("**Branch** (then/else)")
        elif name == "Delay":
            dur = inns.get("Duration", inns.get("duration", "?"))
            chain.append(f"**Delay** ({dur}s)")
        elif name == "PrintString":
            msg = inns.get("InString", "")
            chain.append(f'**PrintString** "{msg}"' if msg else "**PrintString**")
            if msg:
                print_msgs.append(str(msg))
        elif name == "DestroyActor":
            chain.append("**DestroyActor**")
            verify = "Play (PIE): el Actor debe destruirse."
        elif name == "LaunchCharacter":
            needs_input = True
            chain.append("**LaunchCharacter**")
            verify = "Play (PIE) y pulsa la tecla del grafo: el Character debe saltar/impulsarse."
        elif name:
            chain.append(f"**{name}**")
    if has_branch and len(print_msgs) >= 2:
        verify = (
            f'Play (PIE): según Condition verás **"{print_msgs[0]}"** (then) '
            f'o **"{print_msgs[1]}"** (else).'
        )
    elif print_msgs:
        verify = f'Play (PIE): debe verse **"{print_msgs[-1]}"** (PrintString).'
    if chain:
        lines.append("3. Cadena esperada: " + " → ".join(chain) + ".")
    else:
        lines.append("3. Revisa que los nodos del JSON estén cableados en el Event Graph.")
    step = 4
    if needs_input:
        lines.append(
            f"{step}. En Class Defaults / Details: **Auto Receive Input = Player 0**."
        )
        step += 1
    lines.append(f"{step}. Compila y guarda el Blueprint.")
    step += 1
    lines.append(f"{step}. Arrástralo al nivel (si aún no está).")
    step += 1
    lines.append(f"{step}. {verify}")
    if needs_input:
        step += 1
        lines.append(
            f"{step}. Si el input no responde: revisa Auto Receive Input y que el Actor esté poseído/en el nivel."
        )
    return "\n".join(lines)


def explicacion_determinista(prev: str) -> str | None:
    """
    Explicación fija tras «sí» (sin LLM): evita alucinaciones y cortes por tokens.
    """
    prev = prev or ""
    if '"graph_name"' in prev:
        try:
            import sys
            from pathlib import Path

            root = Path(__file__).resolve().parents[1]
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from middleware.bp_lite import prepare_apply_payload

            result = prepare_apply_payload(prev)
            if result.get("ok") and result.get("graph"):
                return _explicacion_desde_grafo(result["graph"])
        except Exception:  # noqa: BLE001
            pass
        return (
            "1. Pulsa **Aplicar BP-Lite** en la ventana Pygenesis.\n"
            "2. Abre el Blueprint en `/Game/Pygenesis` y revisa el Event Graph.\n"
            "3. Compila, colócalo en el nivel y prueba en PIE."
        )
    if '"environment_type"' in prev:
        env = "el preset"
        em = re.search(r'"environment_type"\s*:\s*"([^"]+)"', prev)
        if em:
            env = em.group(1)
        return (
            "1. Pulsa **Aplicar Lighting** en la ventana Pygenesis.\n"
            f"2. Revisa Directional Light, Sky Light, Exponential Height Fog y PostProcess del preset **{env}**.\n"
            "3. Si el nivel ya tenía luces, confirma que los actores se actualizaron (o se crearon).\n"
            "4. Ajusta intensidad/color en Details si quieres afinar.\n"
            "5. Play (PIE) o el viewport lit para validar la atmósfera."
        )
    return None


def _prompt_es_concepto(user_prompt: str) -> bool:
    """Pregunta de concepto: no adjuntar pasos Aplicar ni reescribir a Lighting-Spec."""
    p = (user_prompt or "").strip()
    if not p:
        return False
    if re.search(
        r"(?:"
        r"expl[ií]ca(?:me)?\s+(?:la\s+)?(?:diferencia|ventaja|relaci[oó]n|distinci[oó]n)"
        r"|expl[ií]ca(?:me)?\s+(?:qu[eé]\s+es|c[oó]mo\s+funciona|por\s+qu[eé])"
        r"|diferencia\s+entre"
        r"|qu[eé]\s+(?:diferencia|es|significa)\s+"
        r")",
        p,
        re.I,
    ):
        return True
    if re.search(r"^expl[ií]ca(?:me)?\s+\S+", p, re.I):
        if not re.search(
            r"\b(?:esto|eso|lo\s+anterior|el\s+(?:blueprint|grafo|json)|"
            r"c[oó]mo\s+(?:usarlo|aplicarlo))\b",
            p,
            re.I,
        ):
            return len(re.findall(r"\w+", p, flags=re.UNICODE)) >= 6
    return False


def limpiar_respuesta_modelo(texto: str, user_prompt: str = "") -> str:
    """Pipeline completo; nunca devuelve vacío si había contenido."""
    original = texto or ""
    concepto = _prompt_es_concepto(user_prompt)
    texto = filtrar_thinking(original)
    texto = limpiar_citas_fuente(texto)
    texto = limpiar_eco_instrucciones(texto)
    texto = limpiar_despedidas(texto)
    if concepto:
        # No reescribir a JSON Lighting/BP ni añadir «Aplicar …»
        texto = limpiar_despedidas(texto).strip()
        return texto or original.strip()
    texto = truncate_repetition(texto, user_prompt=user_prompt)
    texto = asegurar_explicacion_aplicar(texto)
    texto = texto.strip()
    if not texto and original.strip():
        recovered = (
            truncate_repetition(original, user_prompt=user_prompt).strip()
            or original.strip()
        )
        return asegurar_explicacion_aplicar(recovered)
    # Si la limpieza perdió el JSON que sí estaba, recuperar truncando el original
    if '"graph_name"' in original and '"graph_name"' not in texto:
        recovered = truncate_repetition(original, user_prompt=user_prompt).strip()
        if '"graph_name"' in recovered:
            return asegurar_explicacion_aplicar(recovered)
        return asegurar_explicacion_aplicar(original.strip())
    return texto
