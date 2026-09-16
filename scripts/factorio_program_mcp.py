"""MCP projection of envd's provider-independent realtime program contract."""

import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlencode


def enabled():
    return os.environ.get("FACTORIO_EXECUTION_MODE") == "realtime"


TOOLS = [
    {
        "name": "factorio_get_program_status",
        "description": "Read program progress. Supply program_id to retrieve its completed execution receipt. Acceptance is not success.",
        "inputSchema": {
            "type": "object",
            "properties": {"program_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "factorio_cancel_program",
        "description": "Cancel queued work or request active cancellation at a safe action boundary. Completed actions remain applied.",
        "inputSchema": {
            "type": "object",
            "properties": {"program_id": {"type": "string"}},
            "required": ["program_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "factorio_await_events",
        "description": "Sleep the agent until a public program/game event after event_cursor or timeout. The factory and executor keep running at 1x. Prefer this to repeated status polling.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_cursor": {"type": "integer", "minimum": 0},
                "timeout_seconds": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 30,
                    "default": 30,
                },
            },
            "required": ["event_cursor"],
            "additionalProperties": False,
        },
    },
]


def dispatch(name, arguments, request_id, envd, receipt, signal):
    base = f"/v1/leases/{os.environ.get('LEASE_ID', '')}"
    if name.endswith("factorio_execute_program"):
        code = arguments.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("execute requires non-empty code")
        key = f"program:{request_id}" if request_id else f"program:{uuid.uuid4()}"
        return envd("POST", base + "/programs", {"code": code, "request_id": key})
    if name.endswith("factorio_cancel_program"):
        program_id = str(uuid.UUID(arguments["program_id"]))
        return envd("DELETE", base + "/programs/" + program_id)
    if name.endswith("factorio_await_events"):
        return envd(
            "GET",
            base
            + "/program-events?"
            + urlencode(
                {
                    "after": arguments["event_cursor"],
                    "timeout": arguments.get("timeout_seconds", 30),
                }
            ),
        )
    if name.endswith("factorio_get_program_status"):
        query = (
            {"program_id": arguments["program_id"], "result": "true"}
            if arguments.get("program_id")
            else {}
        )
        status = envd("GET", base + "/programs?" + urlencode(query))
        result = status.pop("result", None)
        if result:
            status["execution"] = receipt(result)
            terminal = (
                result.get("terminal_reason")
                or (status.get("terminal_event") or {}).get("kind")
                or next(
                    (
                        e["kind"]
                        for e in result.get("events", [])
                        if e.get("kind") in {"contract_fulfilled", "contract_expired"}
                    ),
                    None,
                )
            )
            if terminal and status.get("terminal_program_id") == arguments.get(
                "program_id"
            ):
                signal(terminal, result)
        checkpoint = status.pop("checkpoint", None)
        pointer = os.environ.get("FACTORIO_RESUME_POINTER_FILE")
        if checkpoint and pointer:
            path = Path(pointer)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "schema_version": "factorio-resume-pointer-v1",
                        "checkpoint": checkpoint,
                    }
                ),
                encoding="utf-8",
            )
            os.replace(temporary, path)
        return status
    return None
