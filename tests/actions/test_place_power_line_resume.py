import json

import pytest

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.place_power_line.client import (
    PlacePowerLine,
    _existing_pole_entry,
)

pytestmark = pytest.mark.no_factorio

POLE = Prototype.SmallElectricPole


class FakePole:
    def __init__(self, entity_id):
        self.id = entity_id


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


def test_existing_pole_at_first_point_is_skipped_and_reported():
    tool = make_tool(
        [placement_error((0, 0), pole_at(0, 0)), FakePole(101), FakePole(102)],
        {"small-electric-pole": 5},
    )

    receipt = tool([(0, 0), (14, 0)], POLE, spacing=7.0)

    assert receipt["status"] == "completed"
    assert receipt["stop_reason"] == "completed"
    assert receipt["existing"] == [
        {
            "position": {"x": 0, "y": 0},
            "prototype": "small-electric-pole",
            "entity_id": 41,
        }
    ]
    assert receipt["placed"] == [
        {"position": {"x": 7.0, "y": 0.0}, "entity_id": 101},
        {"position": {"x": 14.0, "y": 0.0}, "entity_id": 102},
    ]
    assert receipt["requested"] == [
        {"x": 0.0, "y": 0.0},
        {"x": 7.0, "y": 0.0},
        {"x": 14.0, "y": 0.0},
    ]
    assert receipt["remaining"] == []
    assert receipt["blocker"] is None
    assert receipt["entity_ids"] == [101, 102]
    assert receipt["inventory_delta"] == {"small-electric-pole": -2}


def test_partial_receipt_stops_at_first_blocked_point_without_raising():
    tool = make_tool(
        [
            FakePole(101),
            placement_error(
                (7, 0),
                {
                    "prototype": "big-rock",
                    "position": {"x": 7, "y": 0},
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
    assert receipt["blocker"]["position"] == {"x": 7.0, "y": 0.0}
    assert receipt["blocker"]["name"] == "big-rock"
    assert receipt["blocker"]["reason"] == "collision"
    assert receipt["blocker"]["blocked_by"]["prototype"] == "big-rock"
    assert receipt["remaining"] == [
        {"x": 7.0, "y": 0.0},
        {"x": 14.0, "y": 0.0},
    ]
    assert receipt["entity_ids"] == [101]
    assert [call["position"].x for call in tool.game_state.place_calls] == [0.0, 7.0]


def test_completed_receipt_when_every_point_places():
    tool = make_tool(
        [FakePole(1), FakePole(2), FakePole(3)], {"small-electric-pole": 3}
    )

    receipt = tool([(0, 0), (14, 0)], POLE, spacing=7.0)

    assert receipt["status"] == "completed"
    assert receipt["blocker"] is None
    assert receipt["remaining"] == []
    assert receipt["existing"] == []
    assert len(receipt["placed"]) == 3
    assert receipt["entity_ids"] == [1, 2, 3]
    assert receipt["inventory_delta"] == {"small-electric-pole": -3}


def test_material_shortage_is_reported_without_raising():
    tool = make_tool(
        [
            FakePole(101),
            RuntimeError(
                "Could not place small-electric-pole at (7.0, 0.0): "
                "No small_electric_pole in inventory. Current inventory: iron-plate: 3"
            ),
        ],
        {"small-electric-pole": 1},
    )

    receipt = tool([(0, 0), (14, 0)], POLE, spacing=7.0)

    assert receipt["status"] == "partial"
    assert receipt["stop_reason"] == "materials_exhausted"
    assert receipt["blocker"]["reason"] == "materials_exhausted"
    assert receipt["blocker"]["inventory"] == {
        "item": "small-electric-pole",
        "available": 0,
    }
    assert receipt["remaining"] == [
        {"x": 7.0, "y": 0.0},
        {"x": 14.0, "y": 0.0},
    ]


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
