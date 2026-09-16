import json

import pytest

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.place_power_line.client import (
    PlacePowerLine,
    _existing_pole_entry,
    _plan,
)

pytestmark = pytest.mark.no_factorio

POLE = Prototype.SmallElectricPole


class FakePole:
    def __init__(self, entity_id, x=0.0, y=0.0):
        self.id = entity_id
        self.position = Position(x=x, y=y)


class FakeGameState:
    def __init__(self, script, inventory):
        self.script = list(script)
        self.inventory = dict(inventory)
        self.place_calls = []

    def inspect_inventory(self):
        from fle.env.entities import Inventory

        return Inventory(**self.inventory)

    def place_entity(self, entity, position=None, exact=True, direction=None):
        self.place_calls.append({"position": position, "exact": exact})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        self.inventory[entity.value[0]] -= 1
        return step


def make_tool(script, inventory):
    tool = PlacePowerLine.__new__(PlacePowerLine)
    tool.game_state = FakeGameState(script, inventory)
    return tool


def attach_engine(tool, response):
    tool.player_index = 1
    tool.execute = lambda *args: (response, 0.0)
    return tool


def placement_error(position, blocked_by=None, reason="occupied"):
    diagnostics = {"reason": reason}
    if blocked_by is not None:
        diagnostics["blocked_by"] = blocked_by
    return RuntimeError(
        json.dumps(
            {
                "error": True,
                "reason": "placement_rejected",
                "position": {"x": position[0], "y": position[1]},
                "diagnostics": diagnostics,
            },
            sort_keys=True,
        )
    )


def pole_at(x, y, entity_id=41):
    return {
        "prototype": "small-electric-pole",
        "position": {"x": x, "y": y},
        "entity_id": entity_id,
        "type": "electric-pole",
    }


def gaps(positions):
    return [
        ((b["x"] - a["x"]) ** 2 + (b["y"] - a["y"]) ** 2) ** 0.5
        for a, b in zip(positions, positions[1:])
    ]


def test_planned_points_snap_and_never_exceed_the_wire_step():
    tool = make_tool(
        [
            FakePole(1, 0.5, 0.5),
            FakePole(2, 7.5, 0.5),
            FakePole(3, 14.5, 0.5),
            FakePole(4, 15.5, 0.5),
        ],
        {"small-electric-pole": 4},
    )

    receipt = tool([(0, 0), (15, 0)], POLE, spacing=7.5)

    assert receipt["status"] == "completed"
    assert receipt["stop_reason"] == "completed"
    assert receipt["requested"] == [
        {"x": 0.5, "y": 0.5},
        {"x": 7.5, "y": 0.5},
        {"x": 14.5, "y": 0.5},
        {"x": 15.5, "y": 0.5},
    ]
    assert receipt["placed"] == [
        {"position": {"x": 0.5, "y": 0.5}, "entity_id": 1},
        {"position": {"x": 7.5, "y": 0.5}, "entity_id": 2},
        {"position": {"x": 14.5, "y": 0.5}, "entity_id": 3},
        {"position": {"x": 15.5, "y": 0.5}, "entity_id": 4},
    ]
    assert max(gaps(receipt["requested"])) <= 7.0 + 1e-9
    assert receipt["unreachable_spans"] == []
    assert receipt["inventory_delta"] == {"small-electric-pole": -4}


def test_existing_pole_at_first_point_is_skipped_and_reported():
    tool = make_tool(
        [
            placement_error((0.5, 0.5), pole_at(0.5, 0.5)),
            FakePole(101, 7.5, 0.5),
            FakePole(102, 14.5, 0.5),
        ],
        {"small-electric-pole": 5},
    )

    receipt = tool([(0, 0), (14, 0)], POLE, spacing=7.0)

    assert receipt["status"] == "completed"
    assert receipt["existing"] == [
        {
            "position": {"x": 0.5, "y": 0.5},
            "prototype": "small-electric-pole",
            "entity_id": 41,
        }
    ]
    assert receipt["entity_ids"] == [101, 102]
    assert receipt["inventory_delta"] == {"small-electric-pole": -2}


def test_partial_receipt_stops_at_first_blocked_point_without_raising():
    tool = make_tool(
        [
            FakePole(101, 0.5, 0.5),
            placement_error(
                (7.5, 0.5),
                {
                    "prototype": "big-rock",
                    "position": {"x": 7.5, "y": 0.5},
                    "entity_id": 7,
                    "type": "simple-entity",
                },
            ),
        ],
        {"small-electric-pole": 4},
    )

    receipt = tool([(0, 0), (14, 0)], POLE, spacing=7.0)

    assert receipt["status"] == "partial"
    assert receipt["stop_reason"] == "collision"
    assert receipt["blocker"]["position"] == {"x": 7.5, "y": 0.5}
    assert receipt["blocker"]["name"] == "big-rock"
    assert receipt["remaining"] == [
        {"x": 7.5, "y": 0.5},
        {"x": 14.5, "y": 0.5},
    ]
    assert receipt["entity_ids"] == [101]
    assert [call["position"].x for call in tool.game_state.place_calls] == [0.5, 7.5]


def test_material_shortage_is_reported_without_raising():
    tool = make_tool(
        [
            FakePole(101, 0.5, 0.5),
            RuntimeError(
                "Could not place small-electric-pole at (7.5, 0.5): "
                "No small_electric_pole in inventory. Current inventory: iron-plate: 3"
            ),
        ],
        {"small-electric-pole": 1},
    )

    receipt = tool([(0, 0), (14, 0)], POLE, spacing=7.0)

    assert receipt["status"] == "partial"
    assert receipt["stop_reason"] == "materials_exhausted"
    assert receipt["blocker"]["inventory"] == {
        "item": "small-electric-pole",
        "available": 0,
    }
    assert receipt["remaining"] == [
        {"x": 7.5, "y": 0.5},
        {"x": 14.5, "y": 0.5},
    ]


def test_engine_verification_reports_unreachable_spans():
    tool = make_tool(
        [FakePole(1, 0.5, 0.5), FakePole(2, 7.5, 0.5), FakePole(3, 14.5, 0.5)],
        {"small-electric-pole": 3},
    )
    attach_engine(
        tool,
        {
            "connected": False,
            "spans_checked": 2,
            "unreachable": [{"from_index": 1, "to_index": 2, "gap": 8.0}],
        },
    )

    receipt = tool([(0, 0), (14, 0)], POLE, spacing=7.0)

    assert receipt["status"] == "partial"
    assert receipt["stop_reason"] == "unreachable_spans"
    assert receipt["entity_ids"] == [1, 2, 3]
    assert receipt["unreachable_spans"] == [
        {
            "from_index": 1,
            "to_index": 2,
            "poles": ["small-electric-pole", "small-electric-pole"],
            "positions": [
                {"x": 7.5, "y": 0.5},
                {"x": 14.5, "y": 0.5},
            ],
            "gap": 8.0,
        }
    ]


def test_engine_verified_line_is_completed():
    tool = make_tool(
        [FakePole(1, 0.5, 0.5), FakePole(2, 7.5, 0.5)],
        {"small-electric-pole": 2},
    )
    attach_engine(tool, {"connected": True, "spans_checked": 1, "unreachable": {}})

    receipt = tool([(0, 0), (7, 0)], POLE, spacing=7.0)

    assert receipt["status"] == "completed"
    assert receipt["stop_reason"] == "completed"
    assert receipt["unreachable_spans"] == []


def test_geometric_fallback_flags_an_engine_snapped_gap():
    tool = make_tool(
        [FakePole(1, 0.5, 0.5), FakePole(2, 8.5, 0.5)],
        {"small-electric-pole": 2},
    )

    receipt = tool([(0, 0), (7, 0)], POLE, spacing=7.0)

    assert receipt["status"] == "partial"
    assert receipt["stop_reason"] == "unreachable_spans"
    assert receipt["unreachable_spans"] == [
        {
            "from_index": 0,
            "to_index": 1,
            "poles": ["small-electric-pole", "small-electric-pole"],
            "positions": [
                {"x": 0.5, "y": 0.5},
                {"x": 8.5, "y": 0.5},
            ],
            "gap": 8.0,
        }
    ]


def test_diagonal_plan_keeps_every_gap_within_the_wire_step():
    planned = _plan([Position(x=0, y=0), Position(x=7, y=7)], 7.0, False)

    points = [{"x": position.x, "y": position.y} for position in planned]
    assert points[0] == {"x": 0.5, "y": 0.5}
    assert points[-1] == {"x": 7.5, "y": 7.5}
    assert max(gaps(points)) <= 7.0 + 1e-9


def test_multi_segment_plan_keeps_one_corner_and_short_steps():
    planned = _plan(
        [Position(x=0, y=0), Position(x=10, y=0), Position(x=10, y=10)], 7.0, False
    )

    points = [{"x": position.x, "y": position.y} for position in planned]
    assert all(first != second for first, second in zip(points, points[1:]))
    assert points.count({"x": 10.5, "y": 0.5}) == 1
    assert max(gaps(points)) <= 7.0 + 1e-9


def test_existing_pole_entry_requires_pole_at_the_requested_point():
    position = Position(x=3, y=4)

    assert _existing_pole_entry(None, position) is None
    assert (
        _existing_pole_entry(
            {
                "prototype": "big-rock",
                "type": "simple-entity",
                "position": {"x": 3, "y": 4},
            },
            position,
        )
        is None
    )
    assert _existing_pole_entry(pole_at(4, 4), position) is None

    entry = _existing_pole_entry(
        {
            "prototype": "medium-electric-pole",
            "type": "electric-pole",
            "position": {"x": 3, "y": 4},
            "entity_id": 6,
        },
        position,
    )
    assert entry == {
        "position": {"x": 3.0, "y": 4.0},
        "prototype": "medium-electric-pole",
        "entity_id": 6,
    }
