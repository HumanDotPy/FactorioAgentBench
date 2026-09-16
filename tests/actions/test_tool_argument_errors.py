from unittest.mock import Mock

import pytest

from fle.env.entities import Direction, Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.can_place_entity.client import CanPlaceEntity
from fle.env.tools.agent.nearest.client import Nearest
from fle.env.tools.agent.place_entity_next_to.client import PlaceEntityNextTo
from fle.env.tools.agent.place_offshore_pump.client import PlaceOffshorePump

pytestmark = pytest.mark.no_factorio


def test_missing_entity_is_a_lookup_error():
    tool = object.__new__(Nearest)
    tool.player_index = 1
    tool.execute = Mock(return_value=("Could not find an entity called iron-chest", 0))
    with pytest.raises(LookupError, match="No iron-chest"):
        tool(Prototype.IronChest)


def test_invalid_direction_has_actionable_error_before_execution():
    tool = object.__new__(PlaceEntityNextTo)
    with pytest.raises(ValueError, match="Direction.RIGHT"):
        tool(Prototype.WoodenChest, direction=4)


def test_can_place_sends_the_engine_direction():
    tool = object.__new__(CanPlaceEntity)
    tool.player_index = 1
    tool.execute = Mock(return_value=(True, 0))
    assert tool(Prototype.Pipe, direction=Direction.LEFT, position=Position(x=1, y=2))
    args = tool.execute.call_args[0]
    assert args[1] == Prototype.Pipe.value[0]
    assert args[2] == Direction.LEFT.value


def test_place_offshore_pump_sends_engine_direction_and_rejects_error_receipts():
    tool = object.__new__(PlaceOffshorePump)
    tool.player_index = 1
    tool.game_state = Mock()
    tool.game_state.instance.fast = True
    tool.game_state.player_location = Position(x=0, y=0)
    tool.connection = Mock()
    tool.execute = Mock(return_value=({"error": True, "reason": "no_water"}, 0))
    with pytest.raises(RuntimeError):
        tool(Position(x=1, y=2), direction=Direction.LEFT)
    assert tool.execute.call_args[0][1:4] == (1.0, 2.0, Direction.LEFT.value)
