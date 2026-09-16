import json
from unittest.mock import Mock

import pytest

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.place_path.client import PlacePath, _blocked_by_from_message

pytestmark = pytest.mark.no_factorio

BLOCKED_MESSAGE = json.dumps(
    {
        "error": True,
        "reason": "placement_rejected",
        "diagnostics": {
            "position": {"x": 2, "y": 0},
            "reason": "occupied",
            "blocked_by": {
                "prototype": "tree-01",
                "position": {"x": 2, "y": 0},
                "entity_id": 9,
                "type": "tree",
            },
        },
    }
)


class FakeEntity:
    def __init__(self, position, entity_id):
        self.position = position
        self.id = entity_id


def make_tool(inventory=10, place_side_effect=None):
    tool = PlacePath.__new__(PlacePath)
    tool.name = "place_path"
    tool.player_index = 1
    tool.connection = Mock()
    tool.connection.rcon_client.send_command = Mock(side_effect=["10", "20"])
    state = Mock()
    state.inspect_inventory.return_value = {Prototype.TransportBelt: inventory}
    state.place_entity.side_effect = place_side_effect
    tool.game_state = state
    return tool


def test_extracts_promoted_blocked_by_from_diagnostics():
    message = (
        'RuntimeError: {"diagnostics": {"position": {"x": 29, "y": -82}, '
        '"reason": "occupied", "blocked_by": {"prototype": "small-electric-pole", '
        '"position": {"x": 30, "y": -82}, "entity_id": 1019, "type": "electric-pole"}}, '
        '"error": true}'
    )
    assert _blocked_by_from_message(message) == {
        "prototype": "small-electric-pole",
        "position": {"x": 30, "y": -82},
        "entity_id": 1019,
        "type": "electric-pole",
    }


def test_falls_back_to_nearest_overlapping_entity():
    message = (
        "Could not place stone-furnace at (0.0, 4.0): __fle-runtime__/control.lua: "
        '"{"diagnostics": {"overlapping_entities": [{"prototype": "character", '
        '"position": {"x": 0, "y": 0}, "entity_id": 14, "distance": 0.2}], '
        '"reason": "occupied"}, "error": true}"'
    )
    blocked_by = _blocked_by_from_message(message)
    assert blocked_by is not None
    assert blocked_by["prototype"] == "character"
    assert blocked_by["position"] == {"x": 0, "y": 0}


def test_returns_none_without_structured_diagnostics():
    assert _blocked_by_from_message("Could not insert: no coal") is None
    assert _blocked_by_from_message('RuntimeError: {"error": true}') is None
    assert _blocked_by_from_message("prefix {not json") is None


def test_partial_receipt_returns_resume_guidance_and_directions():
    tool = make_tool(
        place_side_effect=[
            FakeEntity(Position(0, 0), 1),
            FakeEntity(Position(1, 0), 2),
            RuntimeError(BLOCKED_MESSAGE),
        ]
    )
    receipt = tool(Prototype.TransportBelt, [Position(0, 0), Position(3, 0)])

    assert receipt["status"] == "partial"
    assert receipt["placed"] == 2
    assert receipt["requested"] == 4
    assert receipt["last_position"] == {"x": 1.0, "y": 0.0}
    assert receipt["resume_from"] == {"x": 2.0, "y": 0.0}
    assert receipt["remaining"] == [{"x": 2.0, "y": 0.0}, {"x": 3.0, "y": 0.0}]
    assert receipt["stop_reason"] == "collision"
    assert receipt["blocker"]["blocked_by"]["prototype"] == "tree-01"
    assert receipt["directions"] == [
        {"x": 0.0, "y": 0.0, "direction": "RIGHT"},
        {"x": 1.0, "y": 0.0, "direction": "RIGHT"},
        {"x": 2.0, "y": 0.0, "direction": "RIGHT"},
        {"x": 3.0, "y": 0.0, "direction": "RIGHT"},
    ]
    assert "trace_belt" in receipt["next_step"]
    assert "resume_from" in receipt["next_step"]


def test_completed_receipt_has_no_resume_guidance():
    tool = make_tool(
        place_side_effect=[
            FakeEntity(Position(0, 0), 1),
            FakeEntity(Position(1, 0), 2),
        ]
    )
    receipt = tool(Prototype.TransportBelt, [Position(0, 0), Position(1, 0)])

    assert receipt["status"] == "completed"
    assert receipt["resume_from"] is None
    assert receipt["remaining"] == []
    assert "next_step" not in receipt


def test_on_obstacle_clear_mines_blocker_and_retries():
    tool = make_tool(
        place_side_effect=[
            FakeEntity(Position(0, 0), 1),
            RuntimeError(BLOCKED_MESSAGE),
            FakeEntity(Position(1, 0), 2),
        ]
    )
    tool.game_state.mine_entity = Mock(
        return_value={
            "name": "tree-01",
            "position": {"x": 1.0, "y": 0.0},
            "items": {"wood": 1},
            "removed": True,
        }
    )
    receipt = tool(
        Prototype.TransportBelt,
        [Position(0, 0), Position(1, 0)],
        on_obstacle="clear",
    )

    assert receipt["status"] == "completed"
    assert receipt["placed"] == 2
    assert receipt["cleared"][0]["tool"] == "mine_entity"
    assert receipt["cleared"][0]["result"]["removed"] is True
    tool.game_state.mine_entity.assert_called_once()


def test_on_obstacle_clear_failure_stops_without_raising():
    tool = make_tool(place_side_effect=RuntimeError(BLOCKED_MESSAGE))
    tool.game_state.mine_entity = Mock(side_effect=RuntimeError("nothing neutral"))
    tool.game_state.pickup_entity = Mock(side_effect=RuntimeError("no entity"))
    tool.game_state.deconstruct_area = Mock(return_value={"removed": 0})

    receipt = tool(
        Prototype.TransportBelt,
        [Position(0, 0), Position(2, 0)],
        on_obstacle="clear",
    )

    assert receipt["status"] == "partial"
    assert receipt["stop_reason"] == "clear_failed"
    assert receipt["cleared"] == []
    assert receipt["blocker"]["blocked_by"]["prototype"] == "tree-01"


def test_on_obstacle_validation_rejects_unknown_policy():
    tool = make_tool(place_side_effect=[])
    with pytest.raises(ValueError, match="on_obstacle"):
        tool(
            Prototype.TransportBelt,
            [Position(0, 0), Position(1, 0)],
            on_obstacle="warp",
        )
