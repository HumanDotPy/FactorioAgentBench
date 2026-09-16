"""Opt-in checks against a disposable, explicitly selected Factorio server."""

import os
import time

import pytest

from fle.envd.backend import FLEWorker
from fle.envd.service import EnvironmentService
from scripts.adaptive_contract_benchmark import freeplay_task_spec


@pytest.fixture(autouse=True)
def _reset_between_tests():
    # Override the root fixture: this test owns an explicitly isolated server,
    # and must never acquire/reset the cluster's default instance.
    yield


@pytest.fixture
def isolated_service(tmp_path, monkeypatch):
    port = os.environ.get("FACTORIO_REALTIME_TEST_PORT")
    if not port:
        pytest.skip(
            "Set FACTORIO_REALTIME_TEST_PORT to a disposable Factorio 2.0.77 server"
        )
    monkeypatch.setenv("FLE_LIFECYCLE_DIR", str(tmp_path))
    worker = FLEWorker.connect("isolated-realtime-validation", tcp_port=int(port))
    service = EnvironmentService([worker])
    try:
        yield service
    finally:
        service.close()


def completed(runtime, program_id):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        status = runtime.status(program_id)
        assert not status["failure"], status
        if status["programs"][0]["status"] not in {"queued", "running"}:
            return status
        runtime.wait(status["event_cursor"], 1)
    pytest.fail("Program did not finish")


def test_live_admission_observation_cancellation_and_restore(isolated_service):
    service = isolated_service
    lease = service.lease(freeplay_task_spec(execution_mode="realtime"))
    key = lease.lease_id
    runtime = service.programs(key)
    job = service.submit_program(key, "wait(600)", "wait")
    before = service.observe(key)
    time.sleep(1)
    after = service.observe(key)
    assert after.ticks > before.ticks
    assert runtime.status(job["program_id"])["programs"][0]["status"] == "running"
    following = service.submit_program(key, "print(42)", "following")
    runtime.cancel(job["program_id"])
    assert completed(runtime, job["program_id"])["programs"][0]["status"] == "cancelled"
    assert (
        completed(runtime, following["program_id"])["programs"][0]["status"]
        == "cancelled"
    )
    checkpoint = service.checkpoint(key)
    service.release(key)
    restored = service.lease(
        freeplay_task_spec(checkpoint.checkpoint_id, execution_mode="realtime")
    )
    replay = service.submit_program(restored.lease_id, "wait(600)", "wait")
    assert replay["program_id"] == job["program_id"]
    assert replay["status"] == "cancelled"
    next_job = service.submit_program(restored.lease_id, "wait(30)\nprint(7)", "fresh")
    status = completed(service.programs(restored.lease_id), next_job["program_id"])
    assert status["programs"][0]["status"] == "completed", status
