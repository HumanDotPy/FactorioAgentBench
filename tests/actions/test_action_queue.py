import json

import pytest

from fle.commons.models.game_state import filter_serializable_vars
from fle.env.action_queue import (
    cancel_queue,
    inspect_queue,
    run_queue,
    submit_queue,
)

pytestmark = pytest.mark.no_factorio


class _Rcon:
    def __init__(self):
        self.tick = 10
        self.responses = []
        self.commands = []
        self.interrupt_after = None

    def send_command(self, command):
        self.commands.append(command)
        if "semantic_events" in command:
            if self.responses:
                response = self.responses.pop(0)
                if isinstance(response, Exception):
                    raise response
                return json.dumps(response)
            if self.interrupt_after == len(self.commands):
                return json.dumps({"type": "new_order", "tick": self.tick})
            return json.dumps({})
        return str(self.tick)


class _Instance:
    def __init__(self):
        self.rcon_client = _Rcon()
        self.virtual_tick = 0

    def get_elapsed_ticks(self):
        return self.virtual_tick

    def ensure_connected(self):
        pass


class _Namespace:
    def __init__(self):
        self.instance = _Instance()
        self.persistent_vars = {}
        self.fail = False

    def move_to(self, target):
        self.instance.rcon_client.tick += 60
        self.instance.virtual_tick += 30
        if self.fail:
            raise RuntimeError("blocked")
        return {"position": target}

    def insert_item(self, item, target):
        self.instance.rcon_client.tick += 15
        self.instance.virtual_tick += 5
        return {"item": item, "target": target}

    def wait(self, ticks):
        self.instance.rcon_client.tick += int(ticks)
        self.instance.virtual_tick += int(ticks)
        return {"ticks": ticks}

    def rotate_entities(self, entries, direction):
        self.instance.rcon_client.tick += 5
        return {
            "requested": len(entries),
            "rotated": len(entries),
            "failed": 0,
            "direction": direction,
            "entities": [],
        }


class _SubmitTool:
    player_index = 1

    def execute(self, *_args):
        return {"errors": {}}, 0

    def clean_response(self, value):
        return value


def test_queue_runs_in_order_and_resolves_prior_result():
    namespace = _Namespace()
    receipt = submit_queue(
        namespace,
        _SubmitTool(),
        [
            {"id": "destination", "action": "move_to", "args": [[4, 8]]},
            {
                "action": "insert_item",
                "args": ["coal", {"$result": "destination"}],
            },
        ],
    )

    assert receipt["status"] == "completed"
    assert receipt["next_index"] == 2
    assert receipt["ticks_elapsed"] == 75
    assert receipt["virtual_ticks_elapsed"] == 35
    assert receipt["receipts"][0]["virtual_ticks_elapsed"] == 30
    assert inspect_queue(namespace)["action_count"] == 2
    assert "_action_queue_state" in filter_serializable_vars(namespace.persistent_vars)


def test_queue_halts_and_preserves_pending_suffix():
    namespace = _Namespace()
    namespace.fail = True
    receipt = submit_queue(
        namespace,
        _SubmitTool(),
        [{"action": "move_to", "args": [[4, 8]]}, {"action": "wait", "args": [60]}],
    )

    assert receipt["status"] == "halted"
    assert receipt["next_index"] == 0
    assert receipt["event"]["action_index"] == 0
    cancelled = cancel_queue(namespace)
    assert cancelled["status"] == "cancelled"
    assert cancelled["stop_reason"] == "cancelled"


def test_queue_cancel_keeps_a_pending_queue_resumable():
    namespace = _Namespace()
    namespace.persistent_vars["_action_queue_state"] = {
        "queue_id": "queue",
        "status": "running",
        "actions": [
            {
                "id": "first",
                "action": "move_to",
                "args": [[1, 1]],
                "kwargs": {},
                "result": None,
            },
            {
                "id": "second",
                "action": "move_to",
                "args": [[2, 2]],
                "kwargs": {},
                "result": None,
            },
            {
                "id": "third",
                "action": "move_to",
                "args": [[3, 3]],
                "kwargs": {},
                "result": None,
            },
        ],
        "next_index": 1,
        "interrupt_on": set(),
        "ticks_elapsed": 60,
        "receipts": [],
        "results": {},
        "stop_reason": None,
        "event": None,
    }

    receipt = cancel_queue(namespace, from_index=2)

    assert receipt["status"] == "pending"
    assert receipt["stop_reason"] is None
    assert receipt["action_count"] == 2
    assert receipt["actions"][0]["id"] == "first"


def test_queue_records_receipt_before_a_failed_event_snapshot():
    namespace = _Namespace()
    namespace.instance.rcon_client.responses = [
        RuntimeError("snapshot receive failed"),
    ]
    receipt = submit_queue(
        namespace,
        _SubmitTool(),
        [{"action": "move_to", "args": [[4, 8]]}],
    )

    assert receipt["status"] == "halted"
    assert receipt["stop_reason"] == "event_snapshot_failure"
    assert receipt["next_index"] == 1
    assert receipt["receipt_count"] == 1
    assert receipt["receipts"][0]["result"] == {"position": [4, 8]}


def test_queue_serializes_and_validates_interrupt_names():
    namespace = _Namespace()
    submit_queue(
        namespace,
        _SubmitTool(),
        [{"action": "wait", "args": [1]}],
        interrupt_on=["under_attack", "Sensor_Events"],
    )

    wanted = [
        command
        for command in namespace.instance.rcon_client.commands
        if "wanted" in command
    ]
    assert wanted
    assert '"sensor_events"' in wanted[0]

    with pytest.raises(ValueError, match="not a valid event name"):
        submit_queue(
            namespace,
            _SubmitTool(),
            [{"action": "wait", "args": [1]}],
            interrupt_on=["bad\\name"],
        )


def test_queue_accepts_bulk_rotation_and_rejects_audit_reads():
    namespace = _Namespace()
    receipt = submit_queue(
        namespace,
        _SubmitTool(),
        [
            {
                "action": "rotate_entities",
                "args": [[{"x": 0, "y": 0}, {"x": 1, "y": 0}], 12],
            }
        ],
    )
    assert receipt["status"] == "completed"
    assert receipt["receipts"][0]["result"]["rotated"] == 2

    with pytest.raises(ValueError, match="unavailable command"):
        submit_queue(
            namespace,
            _SubmitTool(),
            [{"action": "belt_line_report", "args": [[0, 0]]}],
        )


def test_queue_rejects_planner_action_and_duplicate_ids():
    namespace = _Namespace()
    with pytest.raises(ValueError, match="unavailable command"):
        submit_queue(namespace, _SubmitTool(), [{"action": "connect_entities"}])
    with pytest.raises(ValueError, match="unique"):
        submit_queue(
            namespace,
            _SubmitTool(),
            [
                {"id": "same", "action": "move_to", "args": [[1, 1]]},
                {"id": "same", "action": "move_to", "args": [[2, 2]]},
            ],
        )


def _state_with_in_flight():
    return {
        "queue_id": "queue",
        "status": "running",
        "actions": [
            {"id": "first", "action": "move_to", "args": [[1, 1]], "kwargs": {}},
            {"id": "second", "action": "move_to", "args": [[2, 2]], "kwargs": {}},
        ],
        "next_index": 1,
        "interrupt_on": set(),
        "ticks_elapsed": 60,
        "virtual_ticks_elapsed": 30,
        "in_flight": {"index": 1, "id": "second", "action": "move_to"},
        "receipts": [],
        "results": {},
        "stop_reason": None,
        "event": None,
    }


def test_queue_never_reexecutes_an_unverified_in_flight_action():
    namespace = _Namespace()
    calls = []
    namespace.move_to = lambda target: calls.append(target)
    namespace.persistent_vars["_action_queue_state"] = _state_with_in_flight()

    receipt = run_queue(namespace)

    assert calls == []
    assert receipt["status"] == "halted"
    assert receipt["stop_reason"] == "action_in_flight"
    assert receipt["in_flight"]["id"] == "second"
    assert receipt["event"]["action_index"] == 1

    cancelled = cancel_queue(namespace, from_index=1)
    assert cancelled["status"] == "cancelled"
    assert cancelled["in_flight"] is None


def test_cancelling_before_the_in_flight_action_keeps_the_marker():
    namespace = _Namespace()
    namespace.persistent_vars["_action_queue_state"] = _state_with_in_flight()

    receipt = cancel_queue(namespace, from_index=2)

    assert receipt["in_flight"]["id"] == "second"
