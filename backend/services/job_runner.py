"""Async inference jobs + SSE streaming helpers."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import uuid

from fastapi import HTTPException

import inference
from middleware.bp_complete import (
    finalize_bp_json,
    is_syntactically_truncated,
)
from services.bp_recovery import recover_incomplete_blueprint
from response_filters import (
    explicacion_determinista,
    limpiar_respuesta_followup,
    limpiar_respuesta_modelo,
    is_degenerate_filler,
    should_stop_generation,
    truncate_repetition,
)
from schemas import Consulta
from services.intent import (
    _es_pregunta_tema_nuevo,
    _es_saludo_o_casual,
    _es_seguimiento_uso,
    _pide_json_bp,
    _pide_json_lighting,
)
from services.prompt_builder import (
    _json_body_for_continue,
    construir_prompt,
)
from services.rag import buscar_contexto

# Jobs asíncronos: el plugin Unreal hace POST corto + GET de polling
# (el HTTP de UE corta conexiones largas a /consultar).
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()

# Sin esto el diccionario crece con cada consulta de la sesión del Editor.
JOB_TTL_SECONDS = 900
JOB_MAX = 64


def _evict_jobs_locked() -> None:
    now = time.time()
    stale = [
        job_id
        for job_id, job in jobs.items()
        if job.get("status") != "running"
        and now - float(job.get("updated") or 0) > JOB_TTL_SECONDS
    ]
    for job_id in stale:
        jobs.pop(job_id, None)
    if len(jobs) > JOB_MAX:
        finished = sorted(
            (j for j in jobs.items() if j[1].get("status") != "running"),
            key=lambda kv: float(kv[1].get("updated") or 0),
        )
        for job_id, _ in finished[: len(jobs) - JOB_MAX]:
            jobs.pop(job_id, None)


def create_job() -> str:
    job_id = uuid.uuid4().hex
    with jobs_lock:
        _evict_jobs_locked()
        jobs[job_id] = {
            "status": "running",
            "phase": "encolado",
            "respuesta": "",
            "fragmentos_usados": 0,
            "error": None,
            "cancelled": False,
            "updated": time.time(),
        }
    return job_id


def cancel_job(job_id: str) -> bool:
    """Marca el job: el bucle de tokens corta en el siguiente y deja lo generado."""
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return False
        if job.get("status") == "running":
            job["cancelled"] = True
            job["phase"] = "cancelando"
            job["updated"] = time.time()
    return True


def _is_cancelled(job_id: str) -> bool:
    with jobs_lock:
        job = jobs.get(job_id)
        return bool(job and job.get("cancelled"))


def _ensure_model_ready() -> None:
    status = inference.get_status()
    if not status["loaded"]:
        raise HTTPException(
            status_code=503,
            detail=status.get("error") or "Modelo no cargado",
        )


async def _stream_inference_sse(consulta: Consulta):
    _ensure_model_ready()
    contexto_rag = buscar_contexto(consulta.prompt, top_k=3)
    prompt_completo = construir_prompt(consulta, contexto_rag)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()
    acumulado = ""

    def worker() -> None:
        try:
            for token in inference.generate_stream(
                prompt_completo, modo_json=consulta.modo_json
            ):
                loop.call_soon_threadsafe(queue.put_nowait, ("token", token))
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))

    threading.Thread(target=worker, daemon=True).start()

    def _final_payload() -> str:
        # Mismo recorte que los jobs: antes el SSE devolvía el eco sin limpiar
        texto = truncate_repetition(acumulado, user_prompt=consulta.prompt) or acumulado
        payload = {
            "done": True,
            "respuesta": limpiar_respuesta_modelo(texto, user_prompt=consulta.prompt),
            "fragmentos_usados": len(contexto_rag),
        }
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    while True:
        kind, data = await queue.get()
        if kind == "token" and data:
            acumulado += data
            yield f"data: {json.dumps({'token': data}, ensure_ascii=False)}\n\n"
            if should_stop_generation(acumulado):
                yield _final_payload()
                break
        elif kind == "done":
            yield _final_payload()
            break
        elif kind == "error":
            raise RuntimeError(data or "Error de inferencia")


def _run_job(job_id: str, consulta: Consulta) -> None:
    try:
        casual = _es_saludo_o_casual(consulta.prompt)
        conceptual = _es_pregunta_tema_nuevo(consulta.prompt)
        wants_graph = _pide_json_bp(consulta.prompt)
        wants_lighting = _pide_json_lighting(consulta.prompt)
        # RAG alarga el prompt y sesga follow-ups ("cómo usarlo" → ejemplos de lighting).
        follow = _es_seguimiento_uso(
            consulta.prompt, consulta.ultima_respuesta or ""
        )
        if casual or wants_graph or wants_lighting or consulta.modo_json or follow:
            contexto_rag = []
        else:
            # Las preguntas de concepto son justo donde el RAG evita inventar pines
            contexto_rag = buscar_contexto(consulta.prompt, top_k=2)

        with jobs_lock:
            job0 = jobs.get(job_id)
            if job0 is not None:
                job0["phase"] = "preparando"
                job0["respuesta"] = ""

        # «sí» tras BP/Lighting: explicación fija (sin LLM → sin alucinaciones ni cortes)
        if follow:
            canned = explicacion_determinista(consulta.ultima_respuesta or "")
            if canned:
                with jobs_lock:
                    jobs[job_id] = {
                        "status": "done",
                        "phase": "done",
                        "respuesta": canned,
                        "fragmentos_usados": 0,
                        "error": None,
                        "cancelled": False,
                        "updated": time.time(),
                    }
                return

        prompt_completo = construir_prompt(consulta, contexto_rag)
        if casual:
            token_budget = 48
        elif follow:
            # Explicación bajo demanda (pasos), sin JSON
            token_budget = 420
        elif conceptual:
            token_budget = 420
        elif wants_graph or wants_lighting or consulta.modo_json:
            # Alineado a Ollama num_predict (512) + margen A/D → 768
            from config import OLLAMA_BP_MAX_TOKENS

            token_budget = OLLAMA_BP_MAX_TOKENS
        else:
            token_budget = None

        with jobs_lock:
            job0 = jobs.get(job_id)
            if job0 is not None:
                job0["phase"] = "generando"

        # Streaming: el poll del plugin lee "respuesta" parcial mientras status=running.
        # IMPORTANTE: marcar done ANTES de stream.close() — close() puede bloquear
        # mientras llama-cpp termina el resto de tokens y el plugin hacía timeout.
        acumulado = ""
        last_publish_len = 0
        last_published = ""
        marked_done = False
        # GBNF solo en jobs BP (no lighting / follow / casual): JSON de grafo garantizado.
        use_bp_grammar = bool(
            wants_graph and not wants_lighting and not follow and not casual
        )

        def _with_bp_prefix(text: str, *, fence: bool = False) -> str:
            """El fence solo va en el mensaje final.

            Si el JSON en curso ya lleva ``` el plugin lo da por cerrado a los
            12 s y no espera al segundo pase (patrulla que se queda en BeginPlay).
            """
            t = text or ""
            if t.lstrip().startswith("```"):
                return t
            body = t.lstrip()
            if not body.startswith("{"):
                return t
            if fence and wants_graph and not follow and not casual:
                closed = body.count("{") <= body.count("}") and body.rstrip().endswith(
                    "}"
                )
                return "```json\n" + body + ("\n```" if closed else "")
            return t

        # Follow-up NUNCA en modo JSON (si no, repite el grafo en vez de explicar).
        use_modo_json = (not follow) and (
            consulta.modo_json or wants_graph or wants_lighting
        )
        stream = inference.generate_stream(
            prompt_completo,
            modo_json=use_modo_json and not use_bp_grammar,
            max_tokens=token_budget,
            use_bp_grammar=use_bp_grammar,
        )

        def _publish_running(text: str) -> None:
            nonlocal last_publish_len, last_published
            with jobs_lock:
                job = jobs.get(job_id)
                if job is not None and job.get("status") == "running":
                    job["respuesta"] = text
                    # No pisar el segundo pase: si vuelve a «generando», el
                    # plugin cree que el BeginPlay cerrado ya es el final.
                    if job.get("phase") not in ("completando", "reintentando"):
                        job["phase"] = "generando"
                    job["updated"] = time.time()
            last_publish_len = len(text)
            last_published = text

        def _mark_done(text: str) -> None:
            nonlocal marked_done
            if marked_done:
                return
            text = _with_bp_prefix(text, fence=True)
            if follow:
                texto_limpio = limpiar_respuesta_followup(text)
                # El prompt primea con "1." (no sale en los tokens); reponerlo si falta.
                if texto_limpio and not re.match(r"^\s*\d+[\.\)]", texto_limpio):
                    texto_limpio = "1. " + texto_limpio.lstrip()
            else:
                texto_limpio = limpiar_respuesta_modelo(
                    text, user_prompt=consulta.prompt
                )
            if stuck_degeneration and '"graph_name"' not in (texto_limpio or ""):
                texto_limpio = (
                    "El modelo ha entrado en un bucle y no ha cerrado el grafo. "
                    "Vuelve a lanzar el pedido."
                )
            elif not (texto_limpio or "").strip():
                texto_limpio = (last_published or text or "").strip()
            # Si el limpio pierde el JSON que el usuario ya vio, recuperar
            # (solo en el turno del grafo; en follow-up el JSON no debe volver)
            if (
                not follow
                and last_published
                and '"graph_name"' in last_published
                and '"graph_name"' not in (texto_limpio or "")
            ):
                texto_limpio = (
                    truncate_repetition(
                        last_published, user_prompt=consulta.prompt
                    )
                    or last_published
                )
                texto_limpio = limpiar_respuesta_modelo(
                    texto_limpio, user_prompt=consulta.prompt
                )
            if not (texto_limpio or "").strip() and (text or "").strip():
                texto_limpio = (
                    limpiar_respuesta_followup(text) if follow else text.strip()
                )
            with jobs_lock:
                cancelled = bool((jobs.get(job_id) or {}).get("cancelled"))
                jobs[job_id] = {
                    "status": "done",
                    "phase": "cancelado" if cancelled else "done",
                    "respuesta": texto_limpio,
                    "fragmentos_usados": len(contexto_rag),
                    "error": None,
                    "cancelled": cancelled,
                    "updated": time.time(),
                }
            marked_done = True

        cancelled_mid_stream = False
        stuck_whitespace = False
        stuck_degeneration = False
        try:
            for token in stream:
                if _is_cancelled(job_id):
                    cancelled_mid_stream = True
                    _mark_done(_with_bp_prefix(acumulado or last_published))
                    break
                acumulado += token
                view = _with_bp_prefix(acumulado)
                # En follow-up no parar por fence JSON (el modelo no debe emitir JSON;
                # si lo hace, lo limpiamos al final; parar aquí cortaría la explicación).
                if wants_graph and not follow and not casual and is_degenerate_filler(
                    acumulado
                ):
                    stuck_degeneration = True
                    print("[job] BP stream colapso «the, the» → corte")
                if (not follow) and should_stop_generation(view):
                    # Publicar versión ya recortada para que el poll no reciba
                    # un monstruo de repetición (rompe el JSON del plugin) ni vacío.
                    if stuck_degeneration:
                        view = truncate_repetition(
                            view, user_prompt=consulta.prompt
                        )
                    else:
                        view = (
                            truncate_repetition(view, user_prompt=consulta.prompt)
                            or last_published
                            or view
                        )
                    _publish_running(view)
                    # En BP no marcamos done aún: un JSON cerrado pero corto
                    # (faltan nodos vs prompt) debe poder pasar por continue.
                    if wants_graph and not casual:
                        break
                    _mark_done(view)
                    break
                # Degeneración a espacios a mitad de JSON ("node_05     …").
                # Umbral bajo: si no cortamos pronto, max_tokens se gasta en basura
                # y el continue/retry llegan tarde o no mejoran.
                if wants_graph and not follow and not casual and is_syntactically_truncated(
                    acumulado
                ):
                    tail = acumulado[-24:] if len(acumulado) >= 24 else acumulado
                    space_run = 0
                    for ch in reversed(acumulado):
                        if ch == " ":
                            space_run += 1
                        else:
                            break
                    if space_run >= 12 or tail.count(" ") >= 16:
                        stuck_whitespace = True
                        print(
                            f"[job] BP stream espacios×{space_run} → recovery"
                        )
                        _publish_running(view)
                        break
                # Publicar casi cada token: el plugin necesita parciales frecuentes
                # o la UI parece “todo de golpe” tras minutos de silencio.
                if (
                    len(view) - last_publish_len >= 1
                    or token.endswith(("\n", " ", ".", ",", "}", "]"))
                ):
                    _publish_running(view)
        finally:
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass

        # Recuperación BP: cierre de lo ya escrito, continue y reintento.
        # No fabrica nodos. El grafo que se aplica lo normaliza prepare_apply.
        if (
            not cancelled_mid_stream
            and wants_graph
            and not follow
            and not casual
        ):
            def _set_phase(phase: str) -> None:
                with jobs_lock:
                    job = jobs.get(job_id)
                    if job is not None and job.get("status") == "running":
                        job["phase"] = phase

            if stuck_degeneration:
                acumulado = truncate_repetition(acumulado, user_prompt=consulta.prompt)
            def _generate_visible(prompt: str, **kwargs) -> str:
                """El segundo pase también se publica. Si no, el chat se queda
                en el primer JSON y el plugin deja de preguntar."""
                if _is_cancelled(job_id):
                    return ""
                head = str(kwargs.get("open_prefix") or "")
                parts: list[str] = []
                text = ""
                for token in inference.generate_stream(
                    prompt,
                    modo_json=bool(kwargs.get("modo_json")),
                    max_tokens=kwargs.get("max_tokens"),
                ):
                    if _is_cancelled(job_id):
                        break
                    parts.append(token)
                    text = "".join(parts)
                    shown = head + text
                    if is_degenerate_filler(text):
                        print("[job] BP reintento colapso → corte")
                        break
                    _publish_running(_with_bp_prefix(shown))
                    if should_stop_generation(shown):
                        break
                return text

            acumulado = recover_incomplete_blueprint(
                text=acumulado,
                prompt=consulta.prompt,
                full_prompt=prompt_completo,
                stuck_whitespace=stuck_whitespace,
                stuck_degeneration=stuck_degeneration,
                generate=_generate_visible,
                set_phase=_set_phase,
                publish=_publish_running,
                prefix=_with_bp_prefix,
                abort=lambda: _is_cancelled(job_id),
            )

        if not marked_done:
            _mark_done(_with_bp_prefix(acumulado or last_published))
    except Exception as exc:  # noqa: BLE001
        # Si el corte/recovery petó, aún intentar dejar un JSON cerrado.
        try:
            seed = ""
            with jobs_lock:
                seed = str((jobs.get(job_id) or {}).get("respuesta") or "")
            if '"graph_name"' in seed and is_syntactically_truncated(seed):
                closed = finalize_bp_json(
                    _json_body_for_continue(seed) or seed, consulta.prompt
                )
                with jobs_lock:
                    jobs[job_id] = {
                        "status": "done",
                        "phase": "done",
                        "respuesta": f"```json\n{closed}\n```",
                        "fragmentos_usados": 0,
                        "error": None,
                        "cancelled": False,
                        "updated": time.time(),
                    }
                return
        except Exception:  # noqa: BLE001
            pass
        # Nunca borrar lo ya streameado: el chat del Editor lo mostraba y luego "desaparecía"
        with jobs_lock:
            prev = jobs.get(job_id) or {}
            prev_resp = (prev.get("respuesta") or "").strip()
            if prev_resp:
                jobs[job_id] = {
                    "status": "done",
                    "phase": "done",
                    "respuesta": prev_resp,
                    "fragmentos_usados": int(prev.get("fragmentos_usados") or 0),
                    "error": None,
                    "cancelled": bool(prev.get("cancelled")),
                    "updated": time.time(),
                }
            else:
                jobs[job_id] = {
                    "status": "error",
                    "phase": "error",
                    "respuesta": None,
                    "fragmentos_usados": 0,
                    "error": str(exc),
                    "cancelled": bool(prev.get("cancelled")),
                    "updated": time.time(),
                }

