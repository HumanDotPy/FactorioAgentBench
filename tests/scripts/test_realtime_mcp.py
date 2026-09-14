import asyncio
import json
from types import SimpleNamespace

import pytest

from scripts import factorio_codex_mcp as mcp
from scripts import adaptive_contract_benchmark as harness
from fle.envd.realtime_prompt import REALTIME_PROMPT

pytestmark = pytest.mark.no_factorio


def test_realtime_tools_and_admission_do_not_capture_world(monkeypatch):
    monkeypatch.setenv("FACTORIO_EXECUTION_MODE", "realtime")
    monkeypatch.setenv("LEASE_ID", "lease")
    monkeypatch.delenv("MCP_TERMINAL_FINALIZATION_FILE", raising=False)
    calls = []

    def envd(method, path, payload=None):
        calls.append((method, path, payload))
        return {"program_id": "job", "status": "queued", "event_cursor": 1}

    monkeypatch.setattr(mcp, "_envd", envd)
    names = {t["name"] for t in mcp.tools_for_profile()}
    assert {
        "factorio_get_program_status",
        "factorio_cancel_program",
        "factorio_await_events",
    } <= names
    text, error = mcp._call_tool_impl(
        "factorio_execute_program", {"code": "wait(600)"}, request_id=1
    )
    assert not error
    assert json.loads(text)["status"] == "queued"
    assert len(calls) == 1
    assert calls[0][1] == "/v1/leases/lease/programs"
    assert calls[0][2]["request_id"]
    monkeypatch.setenv("FACTORIO_EXECUTION_MODE", "turn_based")
    assert "factorio_await_events" not in {t["name"] for t in mcp.tools_for_profile()}


def test_wait_forwards_cursor_without_observation_poll(monkeypatch):
    monkeypatch.setenv("FACTORIO_EXECUTION_MODE", "realtime")
    monkeypatch.setenv("LEASE_ID", "lease")
    calls = []

    def envd(method, path, payload=None):
        calls.append(path)
        return {"event_cursor": 9, "events": [{"kind": "program_completed"}]}

    monkeypatch.setattr(mcp, "_envd", envd)
    _, error = mcp._call_tool_impl(
        "factorio_await_events", {"event_cursor": 8, "timeout_seconds": 20}
    )
    assert not error
    assert calls == ["/v1/leases/lease/program-events?after=8&timeout=20"]


def test_opencode_pacing_prompt_and_config(tmp_path, monkeypatch):
    config = {"agent": {"factorio-eval": {"prompt": ""}}}
    (tmp_path / "opencode.json").write_text(json.dumps(config))
    agent = harness.OpenCodePersistentAgentSession.__new__(
        harness.OpenCodePersistentAgentSession
    )
    agent.scratch = tmp_path
    agent.execution_mode = "realtime"
    asyncio.run(agent.start("Build a factory."))
    prompt = json.loads((tmp_path / "opencode.json").read_text())["agent"][
        "factorio-eval"
    ]["prompt"]
    assert REALTIME_PROMPT in prompt
    assert "Build a factory." in prompt
    assert (
        harness.evaluation_execution_mode(SimpleNamespace(harness="opencode"))
        == "realtime"
    )
    assert (
        harness.evaluation_execution_mode(SimpleNamespace(harness="native"))
        == "turn_based"
    )


def test_runner_detects_terminal_even_without_mcp_result_call(tmp_path):
    class Client:
        async def program_status(self, lease, program_id=None, result=False):
            if result:
                return {
                    "result": {
                        "event": {"sequence": 1},
                        "terminal_reason": "objective_completed",
                    }
                }
            return {
                "checkpoint": {"checkpoint_id": "latest"},
                "terminal_program_id": "job",
            }

    agent = SimpleNamespace(
        execution_mode="realtime",
        program_client=Client(),
        program_lease_id="lease",
        artifacts_dir=tmp_path,
        terminal_file=tmp_path / "terminal.json",
    )
    asyncio.run(harness._sync_realtime_programs(agent))
    assert (
        json.loads(agent.terminal_file.read_text())["reason"] == "objective_completed"
    )
    assert (
        json.loads((tmp_path / "resume/world-checkpoint.json").read_text())[
            "checkpoint"
        ]["checkpoint_id"]
        == "latest"
    )
