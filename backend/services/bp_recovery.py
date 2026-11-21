"""Recuperación de un Blueprint a medias.

Cierra el JSON con los nodos ya terminados y, si faltan piezas, pide al
modelo que lo reemita. No fabrica nodos.
"""

from __future__ import annotations

from collections.abc import Callable

from middleware.bp_complete import (
    clean_partial_for_continue,
    finalize_bp_json,
    is_syntactically_truncated,
    missing_vs_prompt,
    score_graph_candidate,
)
from services.prompt_builder import (
    _build_bp_continue_prompt,
    _json_body_for_continue,
    open_nodes_prefix,
    stitch_continuation,
)


def recover_incomplete_blueprint(
    *,
    text: str,
    prompt: str,
    full_prompt: str,
    stuck_whitespace: bool,
    stuck_degeneration: bool = False,
    generate: Callable[..., str],
    set_phase: Callable[[str], None],
    publish: Callable[[str], None],
    prefix: Callable[[str], str],
    abort: Callable[[], bool] | None = None,
) -> str:
    from config import OLLAMA_BP_CONTINUE_TOKENS, OLLAMA_BP_MAX_TOKENS

    acumulado = text

    # Sin ni un JSON, repetir el prompt solo alarga el bucle de «the, the».
    # Si ya hay nodos, el continue de abajo pide lo que falta. El reintento
    # del prompt original no: es el que se desvía.
    if stuck_degeneration and '"graph_name"' not in (acumulado or ""):
        return acumulado

    def aborted() -> bool:
        return bool(abort and abort())

    def still_needs(blob: str) -> list[str]:
        body = _json_body_for_continue(blob) or blob
        gaps = list(missing_vs_prompt(prompt, body))
        if is_syntactically_truncated(blob or ""):
            gaps.append("JSON cortado a medias")
        seen: set[str] = set()
        out: list[str] = []
        for gap in gaps:
            if gap not in seen:
                seen.add(gap)
                out.append(gap)
        return out

    def take_if_better(candidate: str) -> bool:
        nonlocal acumulado
        cand = (_json_body_for_continue(candidate) or candidate or "").strip()
        if not cand or '"graph_name"' not in cand:
            return False
        if score_graph_candidate(prompt, cand) > score_graph_candidate(prompt, acumulado):
            acumulado = cand
            publish(prefix(acumulado))
            return True
        return False

    if aborted():
        return acumulado

    needs = still_needs(acumulado) or (["atasco espacios"] if stuck_whitespace else [])
    if not needs:
        return acumulado

    set_phase("completando")
    closed = finalize_bp_json(
        _json_body_for_continue(acumulado) or acumulado,
        prompt,
    )
    print("[job] finalize BP inmediato")
    take_if_better(closed)
    if is_syntactically_truncated(acumulado or ""):
        acumulado = closed
        publish(prefix(acumulado))

    needs = still_needs(acumulado)
    for attempt in range(2):
        if aborted() or not needs:
            break
        draft = clean_partial_for_continue(
            _json_body_for_continue(acumulado) or acumulado
        )
        try:
            print(f"[job] continue BP try={attempt + 1} gaps={needs}")
            prefill = open_nodes_prefix(draft)
            cont = generate(
                _build_bp_continue_prompt(prompt, draft, missing=needs),
                modo_json=True,
                max_tokens=max(OLLAMA_BP_CONTINUE_TOKENS, OLLAMA_BP_MAX_TOKENS),
                use_bp_grammar=False,
                repeat_penalty=1.0,
                presence_penalty=0.0,
                open_prefix=prefill,
            )
            if take_if_better(stitch_continuation(prefill, cont or "")):
                needs = still_needs(acumulado)
            else:
                break
        except Exception as cont_exc:  # noqa: BLE001
            print(f"[job] continue JSON falló: {cont_exc}")
            break

    needs = still_needs(acumulado)
    # El mismo pedido, otra vez desde cero, vuelve a cerrar en el primer nodo.
    if (
        not aborted()
        and needs
        and not stuck_degeneration
        and '"graph_name"' not in (acumulado or "")
    ):
        try:
            print(f"[job] retry BP full gaps={needs}")
            set_phase("reintentando")
            fresh = generate(
                full_prompt,
                modo_json=True,
                max_tokens=OLLAMA_BP_MAX_TOKENS,
                use_bp_grammar=False,
                repeat_penalty=1.0,
                presence_penalty=0.0,
            )
            take_if_better(fresh or "")
        except Exception as retry_exc:  # noqa: BLE001
            print(f"[job] retry BP full falló: {retry_exc}")

    if aborted():
        return acumulado

    if is_syntactically_truncated(acumulado or "") or still_needs(acumulado):
        closed = finalize_bp_json(
            _json_body_for_continue(acumulado) or acumulado,
            prompt,
        )
        print("[job] finalize BP JSON cerrado")
        acumulado = closed
        publish(prefix(acumulado))
    return acumulado
