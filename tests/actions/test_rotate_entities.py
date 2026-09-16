from unittest.mock import Mock

import pytest

from fle.env import DirectionInternal
from fle.env.entities import Position
from fle.env.tools.agent.place_path.rotate_entities.client import RotateEntities

pytestmark = pytest.mark.no_factorio

RESULT = {
    "requested": 2,
    "rotated": 2,
    "failed": 0,
    "direction": 12,
    "entities": [],
}


def make_tool(response=RESULT):
    tool = RotateEntities.__new__(RotateEntities)
    tool.name = "rotate_entities"
    tool.player_index = 1
    tool.execute = Mock(return_value=(response, None))
    return tool


def test_positions_and_named_entries_are_forwarded():
    tool = make_tool()
    receipt = tool(
        [Position(x=1, y=2), {"x": 3, "y": 4, "name": "transport-belt"}],
        DirectionInternal.LEFT,
    )
    assert receipt["rotated"] == 2
    assert receipt["requested_direction"] == "LEFT"
    tool.execute.assert_called_once_with(
        1,
        [
            {"x": 1.0, "y": 2.0},
            {"x": 3.0, "y": 4.0, "name": "transport-belt"},
        ],
        12,
    )


def test_invalid_list_and_direction_are_rejected():
    tool = make_tool()
    with pytest.raises(ValueError, match="non-empty list"):
        tool([], DirectionInternal.UP)
    with pytest.raises(ValueError, match="direction must be a Direction"):
        tool([Position(x=0, y=0)], "north")
    with pytest.raises(ValueError, match="entities must contain"):
        tool([42], DirectionInternal.UP)
    tool.execute.assert_not_called()


def test_engine_error_is_raised():
    tool = make_tool(response={"error": "no character"})
    with pytest.raises(RuntimeError, match="no character"):
        tool([Position(x=0, y=0)], DirectionInternal.UP)
