"""Contabilidad de jobs y perfil de sampling del puente de inferencia."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
for path in (str(REPO_ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)

from services import job_runner  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_jobs():
    job_runner.jobs.clear()
    yield
    job_runner.jobs.clear()


def test_create_job_arranca_en_running():
    job_id = job_runner.create_job()
    job = job_runner.jobs[job_id]
    assert job["status"] == "running"
    assert job["cancelled"] is False
    assert job["updated"] > 0


def test_cancel_job_marca_y_devuelve_true():
    job_id = job_runner.create_job()
    assert job_runner.cancel_job(job_id) is True
    assert job_runner.jobs[job_id]["cancelled"] is True
    assert job_runner._is_cancelled(job_id) is True


def test_cancel_job_desconocido():
    assert job_runner.cancel_job("no-existe") is False


def test_jobs_terminados_caducan():
    stale = job_runner.create_job()
    job_runner.jobs[stale].update(
        {"status": "done", "updated": time.time() - job_runner.JOB_TTL_SECONDS - 1}
    )
    running = job_runner.create_job()
    job_runner.jobs[running]["updated"] = time.time() - job_runner.JOB_TTL_SECONDS - 1

    job_runner.create_job()  # dispara la purga

    assert stale not in job_runner.jobs, "un job terminado y viejo debe purgarse"
    assert running in job_runner.jobs, "un job en curso nunca se purga"


def test_jobs_respetan_el_tope():
    for _ in range(job_runner.JOB_MAX + 10):
        job_id = job_runner.create_job()
        job_runner.jobs[job_id]["status"] = "done"
    job_runner.create_job()
    assert len(job_runner.jobs) <= job_runner.JOB_MAX + 1


def test_sampling_json_sin_penalizaciones_agresivas():
    import inference
    from config import OLLAMA_BP_PRESENCE_PENALTY, OLLAMA_BP_REPEAT_PENALTY

    # El JSON BP-Lite repite estructura por nodo: penalizar repetición hacía que
    # el modelo cortara el grafo en el tercer o cuarto nodo.
    assert OLLAMA_BP_REPEAT_PENALTY <= 1.05
    assert OLLAMA_BP_PRESENCE_PENALTY == 0.0

    # En JSON solo se corta por fin de turno, no por frases de prosa
    stops_json = inference._stops_for(json_mode=True)
    stops_prose = inference._stops_for(json_mode=False)
    assert all("\n" not in s for s in stops_json)
    assert len(stops_prose) > len(stops_json)
