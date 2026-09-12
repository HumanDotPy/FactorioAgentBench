from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
import threading
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from fle.commons import profiling as profile
from fle.env.instance import FactorioInstance
from fle.env.tools.controller import Controller
from fle.envd.api import create_app
from fle.envd.service import EnvironmentService
from scripts import factorio_codex_mcp as mcp
from scripts import factorio_profile as cli
from tests.envd.conftest import FakeWorker


pytestmark = pytest.mark.no_factorio


def test_bounded_sampling_expiration_and_clear_inflight(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(profile.time, "monotonic", lambda: clock[0])
    store = profile.ProfileStore()
    assert store.begin("execute") is None
    store.configure(enabled=True, sample_every=2, duration_seconds=10)
    old_generation, old_trace = store.begin("execute")
    assert store.begin("execute") is None
    store.configure(enabled=True, clear=True)
    old_trace.finish()
    store.complete(old_generation, old_trace)
    assert not store.report()["traces"]
    for _ in range(profile.TRACE_LIMIT + 3):
        generation, trace = store.begin("execute")
        with profile.activate(trace):
            for i in range(profile.STAGE_LIMIT + 10):
                with profile.span(f"stage.{i}"):
                    pass
        store.complete(generation, trace)
    report = store.report()
    assert len(report["traces"]) == profile.TRACE_LIMIT
    assert report["evicted_samples"] == 3
    assert len(report["traces"][-1]["stages"]) == profile.STAGE_LIMIT
    assert report["operations"]["execute"]["count"] == profile.TRACE_LIMIT
    clock[0] += 301
    assert store.begin("execute") is None
    assert not store.report()["enabled"]


def test_nested_errors_and_context_restoration():
    trace = profile.Trace("operation")
    with pytest.raises(ValueError), profile.activate(trace):
        with profile.span("outer"), profile.span("inner"):
            raise ValueError("private contents must not be recorded")
    assert profile.current_trace() is None
    captured = trace.snapshot()
    assert captured["failed"]
    assert captured["stages"]["inner"]["errors"] == 1
    assert (
        captured["stages"]["outer"]["total_ms"]
        >= captured["stages"]["inner"]["total_ms"]
    )
    assert "private contents" not in json.dumps(captured)


def test_context_reaches_real_evaluation_executor():
    instance = FactorioInstance.__new__(FactorioInstance)

    def evaluate(expr):
        with profile.span("inside.evaluation.thread"):
            return expr

    instance.namespaces = [SimpleNamespace(eval_with_timeout=evaluate)]
    with ThreadPoolExecutor(max_workers=1) as executor:
        instance._executor = executor
        trace = profile.Trace("execute")
        with profile.activate(trace):
            assert instance.eval_with_error("value") == "value"
        assert "inside.evaluation.thread" in trace.snapshot()["stages"]
        assert executor.submit(profile.current_trace).result() is None


def test_controller_records_rcon_and_decode_without_payload():
    manager = SimpleNamespace(
        action_invocation=lambda *args: "secret invocation",
        action_command=lambda *args: "secret command",
        rcon_client=SimpleNamespace(
            send_command=lambda command: "{a=true,b={answer=42}}"
        ),
    )
    controller = Controller(manager, SimpleNamespace(agent_index=0))
    trace = profile.Trace("execute")
    with profile.activate(trace):
        result, _ = controller.execute("private argument")
    assert result == {"answer": 42}
    assert {"rcon.action.controller", "lua.decode"} <= trace.stages.keys()
    assert "secret" not in json.dumps(trace.snapshot())
    assert "private argument" not in json.dumps(trace.snapshot())


def test_active_http_toggle_isolation_and_unchanged_idempotency(task_spec):
    service = EnvironmentService([FakeWorker("one"), FakeWorker("two")])
    lease = service.lease(task_spec).lease_id
    second = service.lease(task_spec).lease_id
    client = TestClient(create_app(service))
    path = f"/v1/leases/{lease}"
    assert client.get("/v1/health").json()["capabilities"]["features"][
        "runtime_profiling"
    ]
    assert client.get(path + "/profiling").json()["enabled"] is False
    first = client.post(
        path + "/execute", json={"code": "print(1)", "request_id": "once"}
    )
    assert "x-factorio-trace-id" not in first.headers
    config = client.put(path + "/profiling", json={"enabled": True})
    assert config.status_code == 200
    replay = client.post(
        path + "/execute",
        json={"code": "print(1)", "request_id": "once"},
        headers={"X-Factorio-Call-Id": "a" * 32},
    )
    assert replay.json() == first.json()
    assert "x-factorio-trace-id" in replay.headers
    conflict = client.post(
        path + "/execute", json={"code": "print(2)", "request_id": "once"}
    )
    assert conflict.status_code == 409
    report = client.get(path + "/profiling").json()
    assert len(report["traces"]) == 2
    assert report["traces"][0]["correlation_id"] == "a" * 32
    assert report["traces"][1]["failed"]
    assert "lease.lock_wait" in report["stages"]
    assert "service.execute" in report["stages"]
    assert not client.get(f"/v1/leases/{second}/profiling").json()["traces"]
    assert "profiling" not in json.dumps(first.json())
    assert (
        client.put(
            path + "/profiling", json={"enabled": True, "sample_every": 0}
        ).status_code
        == 422
    )
    assert client.get("/v1/leases/missing/profiling").status_code == 404
    client.put(path + "/profiling", json={"enabled": False})
    client.get(path + "/observe")
    assert len(client.get(path + "/profiling").json()["traces"]) == 2


def test_toggle_during_inflight_execution_does_not_wait_for_world(task_spec):
    entered = threading.Event()
    finish = threading.Event()

    class BlockingWorker(FakeWorker):
        def execute(self, *args, **kwargs):
            entered.set()
            assert finish.wait(10)
            return super().execute(*args, **kwargs)

    service = EnvironmentService([BlockingWorker()])
    lease = service.lease(task_spec).lease_id
    app = create_app(service)
    path = f"/v1/leases/{lease}"
    with ThreadPoolExecutor(max_workers=2) as executor:
        action = executor.submit(
            lambda: TestClient(app).post(path + "/execute", json={"code": "print(1)"})
        )
        try:
            assert entered.wait(5)
            control = executor.submit(
                lambda: TestClient(app).put(path + "/profiling", json={"enabled": True})
            )
            assert control.result(timeout=3).status_code == 200
        finally:
            finish.set()
        assert action.result(timeout=5).status_code == 200
    assert not service.profiling(lease).report()["traces"]


@pytest.mark.parametrize("sampled", [False, True])
def test_mcp_profiles_only_sampled_responses_without_extra_requests(
    monkeypatch, tmp_path, sampled
):
    monkeypatch.setenv("FACTORIO_TOOL_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("ENVD_URL", "http://example.invalid")
    monkeypatch.setenv("LEASE_ID", "lease")
    requests = []

    @contextmanager
    def urlopen(request, **kwargs):
        requests.append(request)
        yield SimpleNamespace(
            headers={"X-Factorio-Trace-Id": "b" * 32} if sampled else {},
            read=lambda: b'{"contract_status":"open"}',
        )

    monkeypatch.setattr(mcp.urllib.request, "urlopen", urlopen)
    result, failed = mcp._call_tool("factorio_check_throughput", {}, request_id=1)
    assert not failed
    assert json.loads(result) == {"contract_status": "open"}
    assert len(requests) == 1
    files = list((tmp_path / "profiling").glob("*.jsonl"))
    assert len(files) == int(sampled)
    if sampled:
        captured = json.loads(files[0].read_text())
        assert captured["server_trace_ids"] == ["b" * 32]
        assert captured["trace_id"] == requests[0].get_header("X-factorio-call-id")
        assert "http.other" in captured["stages"]


def test_mcp_persistence_rotates_and_cannot_fail_action(tmp_path, monkeypatch):
    trace = profile.Trace("execute")
    trace.finish()
    for _ in range(3):
        profile.persist_trace(tmp_path, trace, max_bytes=1)
    assert len(list(tmp_path.glob("*.jsonl"))) == 2

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", fail)
    profile.persist_trace(tmp_path, trace)


def test_cli_controls_and_exports(monkeypatch, tmp_path):
    report = profile.ProfileStore().report()
    requests = []

    @contextmanager
    def urlopen(request, **kwargs):
        requests.append(request)
        yield SimpleNamespace(read=lambda: json.dumps(report).encode())

    monkeypatch.setattr(cli.urllib.request, "urlopen", urlopen)
    output = tmp_path / "report.json"
    assert (
        cli.main(
            [
                "enable",
                "--url",
                "http://example.invalid",
                "--lease",
                "lease",
                "--clear",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(requests[0].data)["clear"] is True
    assert json.loads(output.read_text()) == report


def test_mcp_execute_checkpoint_camera_correlate_end_to_end(
    task_spec, monkeypatch, tmp_path
):
    class CheckpointWorker(FakeWorker):
        def export_game_state(self):
            return '{"private_world_state":true}'

        def export_resume_state(self):
            return {"private_resume_state": True}

        def camera(self, *args, **kwargs):
            return {"enabled": False}

    service = EnvironmentService([CheckpointWorker()])
    lease = service.lease(task_spec).lease_id
    service.profiling(lease).configure(enabled=True)
    client = TestClient(create_app(service))
    monkeypatch.setenv("LEASE_ID", lease)
    monkeypatch.setenv("ENVD_URL", "http://testserver")
    monkeypatch.setenv("FACTORIO_TOOL_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("FACTORIO_RESUME_POINTER_FILE", str(tmp_path / "resume.json"))
    monkeypatch.setenv("FACTORIO_CHECKPOINT_EVERY", "1")
    monkeypatch.setenv("FLE_LIFECYCLE_DIR", str(tmp_path / "checkpoints"))
    requests = []

    @contextmanager
    def urlopen(request, **kwargs):
        requests.append(request.full_url)
        response = client.request(
            request.method,
            request.full_url,
            content=request.data,
            headers=dict(request.header_items()),
        )
        assert 200 <= response.status_code < 300, response.text
        yield SimpleNamespace(headers=response.headers, read=lambda: response.content)

    monkeypatch.setattr(mcp.urllib.request, "urlopen", urlopen)
    mcp._reset_repetition_state()
    result, failed = mcp._call_tool(
        "factorio_execute_program", {"code": "print('private code')"}, request_id="one"
    )
    assert not failed
    assert json.loads(result)["status"] == "success"
    assert [url.rsplit("/", 1)[-1] for url in requests] == [
        "execute",
        "checkpoints",
        "camera",
    ]
    assert (tmp_path / "resume.json").is_file()
    server = service.profiling(lease).report()
    local = json.loads(
        next((tmp_path / "artifacts" / "profiling").glob("*.jsonl")).read_text()
    )
    assert len(server["traces"]) == 3
    assert {trace["correlation_id"] for trace in server["traces"]} == {
        local["trace_id"]
    }
    assert {trace["trace_id"] for trace in server["traces"]} == set(
        local["server_trace_ids"]
    )
    assert {
        "http.execute",
        "http.checkpoints",
        "http.camera",
        "mcp.execution_artifact",
        "mcp.camera",
    } <= local["stages"].keys()
    assert "checkpoint.persist" in server["stages"]
    assert "private" not in json.dumps(server)
    assert "private" not in json.dumps(local)
    checkpoint = json.loads(
        next((tmp_path / "checkpoints").rglob("ep*.json")).read_text()
    )
    assert "profiling" not in json.dumps(checkpoint)
