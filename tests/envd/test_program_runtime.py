import threading
import time
from contextlib import nullcontext
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from fle.envd.api import create_app
from fle.envd.errors import IdempotencyConflict
from fle.envd.program_runtime import ProgramRuntime
from fle.envd.service import EnvironmentService
from tests.envd.conftest import FakeWorker

pytestmark = pytest.mark.no_factorio


def test_tool_wrapper_accepts_uninitialized_tool_with_mock_state():
    from fle.env.tools.tool import Tool

    class TestAction(Tool):
        def __call__(self):
            return {"status": "completed"}

    action = TestAction.__new__(TestAction)
    action.game_state = Mock()
    result = action()
    assert result == {"status": "completed"}
    action.game_state._program_runtime.boundary.assert_called_once_with()
    action.game_state._program_runtime.action_result.assert_called_once_with(
        "TestAction", result
    )


class LiveWorker(FakeWorker):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.finish = threading.Event()
        self.read_threads = []
        self.executed = []

    def execute(self, lease_id, code, sequence, template=None):
        self.executed.append(code)
        self.started.set()
        while not self.finish.wait(0.005):
            self.program_runtime.pump()
            if self.program_runtime.cancelled():
                break
        return super().execute(lease_id, code, sequence, template)

    def observe(self, lease_id):
        self.read_threads.append(threading.get_ident())
        return super().observe(lease_id)

    def export_game_state(self):
        return "{}"

    def export_resume_state(self):
        return {}


@pytest.fixture
def live(tmp_path, monkeypatch, task_spec):
    monkeypatch.setenv("FLE_LIFECYCLE_DIR", str(tmp_path))
    worker = LiveWorker()
    service = EnvironmentService([worker])
    lease = service.lease(
        task_spec.model_copy(
            update={"execution_mode": "realtime", "max_interventions": None}
        )
    )
    try:
        yield service, worker, lease.lease_id
    finally:
        worker.finish.set()
        service.close()


def settle(runtime):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = runtime.status()
        if status["failure"]:
            pytest.fail(status["failure"])
        if not status["active_program_id"] and not status["queue_length"]:
            return status
        runtime.wait(status["event_cursor"], 0.05)
    pytest.fail("executor did not settle")


def test_acceptance_reads_and_idempotency_while_running(live):
    service, worker, lease = live
    first = service.submit_program(lease, "print(1)", "one")
    assert first["status"] == "queued"
    assert worker.started.wait(2)
    assert (
        service.submit_program(lease, "print(1)", "one")["program_id"]
        == first["program_id"]
    )
    with pytest.raises(IdempotencyConflict):
        service.submit_program(lease, "print(2)", "one")
    observation = service.observe(lease)
    assert observation.ticks == 0
    assert worker.read_threads[-1] == service.programs(lease).thread.ident
    second = service.submit_program(lease, "print(2)", "two")
    assert second["status"] == "queued"
    assert worker.executed == ["print(1)"]
    worker.finish.set()
    settle(service.programs(lease))
    assert worker.executed == ["print(1)", "print(2)"]


def test_cancellation_preserves_prefix_and_cancels_suffix(live):
    service, worker, lease = live
    first = service.submit_program(lease, "print(1)", "one")
    assert worker.started.wait(2)
    second = service.submit_program(lease, "print(2)", "two")
    runtime = service.programs(lease)
    runtime.cancel(first["program_id"])
    settle(runtime)
    assert runtime.status(first["program_id"])["programs"][0]["status"] == "cancelled"
    assert runtime.status(second["program_id"])["programs"][0]["status"] == "cancelled"
    assert worker.executed == ["print(1)"]


def test_queue_bound_and_event_wait(live):
    service, worker, lease = live
    runtime = service.programs(lease)
    for index in range(8):
        service.submit_program(lease, f"print({index})", str(index))
    with pytest.raises(ValueError, match="full"):
        service.submit_program(lease, "print(9)", "nine")
    assert worker.started.wait(2)
    cursor = runtime.status()["event_cursor"]
    assert runtime.wait(cursor, 0.01)["events"] == []
    worker.finish.set()
    assert runtime.wait(cursor, 2)["events"]


def test_cancelling_queued_program_keeps_active_prefix(live):
    service, worker, lease = live
    first = service.submit_program(lease, "print(1)", "one")
    assert worker.started.wait(2)
    second = service.submit_program(lease, "print(2)", "two")
    third = service.submit_program(lease, "print(3)", "three")
    runtime = service.programs(lease)
    runtime.cancel(second["program_id"])
    assert runtime.status(third["program_id"])["programs"][0]["status"] == "cancelled"
    assert not runtime.cancelled()
    worker.finish.set()
    settle(runtime)
    assert runtime.status(first["program_id"])["programs"][0]["status"] == "completed"
    assert worker.executed == ["print(1)"]


def test_restore_reconciles_later_durable_admissions(tmp_path):
    first = ProgramRuntime(tmp_path, None, None, nullcontext)
    one = first.submit("print(1)", "one", "hash1")
    state = first.export()
    two = first.submit("print(2)", "two", "hash2")
    restored = ProgramRuntime(tmp_path, None, None, nullcontext, state=state)
    assert set(restored.jobs) == {one["program_id"], two["program_id"]}
    assert (
        restored.submit("print(2)", "two", "hash2")["program_id"] == two["program_id"]
    )
    restored.cancel(two["program_id"])
    again = ProgramRuntime(tmp_path, None, None, nullcontext, state=state)
    assert again.jobs[two["program_id"]]["status"] == "cancelled"


def test_torn_admission_tail_is_repaired_before_append(tmp_path):
    runtime = ProgramRuntime(tmp_path, None, None, nullcontext)
    state = runtime.export()
    runtime.submit("print(1)", "one", "hash1")
    with (runtime.directory / "admissions.jsonl").open("ab") as file:
        file.write(b'{"operation":')
    restored = ProgramRuntime(tmp_path, None, None, nullcontext, state=state)
    restored.submit("print(2)", "two", "hash2")
    again = ProgramRuntime(tmp_path, None, None, nullcontext, state=state)
    assert len(again.jobs) == 2


def test_restore_cancellation_stops_previously_admitted_suffix(tmp_path):
    runtime = ProgramRuntime(tmp_path, None, None, nullcontext)
    state = runtime.export()
    first = runtime.submit("print(1)", "one", "hash1")
    second = runtime.submit("print(2)", "two", "hash2")
    runtime.pending.popleft()
    runtime.active = first["program_id"]
    runtime.jobs[runtime.active]["status"] = "running"
    runtime.cancel(runtime.active)
    restored = ProgramRuntime(tmp_path, None, None, nullcontext, state=state)
    assert restored.jobs[second["program_id"]]["status"] == "cancelled"
    assert not restored.pending


def test_memory_and_template_admission_do_not_wait_for_execution(live):
    service, worker, lease = live
    service.submit_program(lease, "wait(60)", "first")
    assert worker.started.wait(2)
    service.memory_write(lease, "plan", "Build the next furnace")
    assert service.memory_read(lease, "plan").content == "Build the next furnace"
    service.save_template(lease, "greet", code='print("hello")')
    submitted = service.run_template(lease, "greet", request_id="template-one")
    repeated = service.run_template(lease, "greet", request_id="template-one")
    assert submitted["program_id"] == repeated["program_id"]
    assert worker.template_store.get("greet").times_run == 1


def test_public_terminal_event_cancels_active_program(live):
    service, worker, lease = live
    runtime = service.programs(lease)
    job = service.submit_program(lease, "wait(600)", "one")
    assert worker.started.wait(2)
    runtime.poll_events = lambda: [
        {"kind": "objective_completed", "tick": 90, "terminal": True}
    ]
    runtime.last_poll = 0
    settle(runtime)
    status = runtime.status()
    assert status["terminal_event"]["kind"] == "objective_completed"
    assert status["terminal_program_id"] == job["program_id"]
    with pytest.raises(RuntimeError):
        service.submit_program(lease, "print(2)", "two")


def test_partial_batch_result_blocks_following_action(tmp_path):
    runtime = ProgramRuntime(tmp_path, None, None, nullcontext)
    job = runtime.submit("print(1)", "one", "hash1")
    runtime.active = job["program_id"]
    runtime.action_result("place_grid", {"status": "partial", "placed": 2})
    with pytest.raises(RuntimeError, match="partial"):
        runtime.boundary()


def test_fixed_pacing_and_http_program_contract(live):
    service, worker, lease = live
    with pytest.raises(ValueError, match="continuous"):
        service.set_realtime(lease, enabled=False)
    with pytest.raises(ValueError, match="/programs"):
        service.execute(lease, "print(1)")
    client = TestClient(create_app(service))
    accepted = client.post(
        f"/v1/leases/{lease}/programs", json={"code": "print(1)", "request_id": "one"}
    )
    assert accepted.status_code == 202
    assert worker.started.wait(2)
    status = client.get(f"/v1/leases/{lease}/programs").json()
    assert status["active_program_id"] == accepted.json()["program_id"]
    assert (
        client.get(f"/v1/leases/{lease}/programs?program_id=missing").status_code == 404
    )


def test_external_checkpoint_never_captures_running_stack(live):
    service, worker, lease = live
    service.submit_program(lease, "print(1)", "one")
    assert worker.started.wait(2)
    finished = threading.Event()
    checkpoint = []

    def save():
        checkpoint.append(service.checkpoint(lease))
        finished.set()

    thread = threading.Thread(target=save)
    thread.start()
    assert not finished.wait(0.03)
    worker.finish.set()
    assert finished.wait(5)
    thread.join()
    from fle.envd.lifecycle import CheckpointPool

    state = CheckpointPool().get_payload(checkpoint[0].checkpoint_id)["quality"][
        "service_state"
    ]
    assert all(job["status"] != "running" for job in state["programs"]["jobs"].values())
