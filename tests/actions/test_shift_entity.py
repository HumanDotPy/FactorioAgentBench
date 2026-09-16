from unittest.mock import Mock

import pytest

from fle.env import DirectionInternal
from fle.env.entities import Dimensions, Direction, Entity, Position, TileDimensions
from fle.env.tools.agent.shift_entity.client import ShiftEntity

pytestmark = pytest.mark.no_factorio


def make_entity(x=4.0, y=4.0, direction=Direction.NORTH):
    return Entity(
        name="wooden-chest",
        position=Position(x=x, y=y),
        direction=direction,
        energy=0.0,
        dimensions=Dimensions(width=1, height=1),
        tile_dimensions=TileDimensions(tile_width=1, tile_height=1),
        health=100.0,
    )


def make_tool(can_place=True, pickup_result=True, place_side_effect=None):
    tool = ShiftEntity.__new__(ShiftEntity)
    tool.player_index = 1
    tool.pickup_entity = Mock(return_value=pickup_result)
    tool.can_place_entity = Mock(return_value=can_place)
    if place_side_effect is None:
        place_side_effect = [make_entity(5.0, 4.0)]
    tool.place_entity = Mock(side_effect=place_side_effect)
    return tool


def placed_at(tool, index=-1):
    position = tool.place_entity.call_args_list[index].args[2]
    return (position.x, position.y)


def test_shift_moves_in_direction_internal_cardinal_values():
    moved_entity = make_entity(4.0, 5.0)
    tool = make_tool(place_side_effect=[moved_entity])
    entity = make_entity()
    moved = tool(entity, DirectionInternal.SOUTH)

    assert moved is moved_entity
    tool.pickup_entity.assert_called_once_with(entity)
    assert placed_at(tool) == (4.0, 5.0)


def test_shift_accepts_direction_aliases():
    tool = make_tool()
    tool(make_entity(), Direction.NORTH, distance=2)
    assert placed_at(tool) == (4.0, 2.0)


def test_shift_rejects_diagonals_before_pickup():
    tool = make_tool()
    with pytest.raises(ValueError, match="cardinal"):
        tool(make_entity(), Direction.UPRIGHT)
    tool.pickup_entity.assert_not_called()
    tool.place_entity.assert_not_called()


def test_shift_rejects_invalid_distance():
    tool = make_tool()
    with pytest.raises(ValueError, match="distance"):
        tool(make_entity(), Direction.RIGHT, distance=0)
    tool.pickup_entity.assert_not_called()


def test_shift_reports_pickup_failure_without_placing():
    tool = make_tool(pickup_result=False)
    with pytest.raises(Exception, match="pickup failed"):
        tool(make_entity(), Direction.RIGHT)
    tool.place_entity.assert_not_called()


def test_shift_restores_entity_when_destination_is_blocked():
    tool = make_tool(can_place=False, place_side_effect=[make_entity()])
    with pytest.raises(Exception, match="restored at"):
        tool(make_entity(), Direction.RIGHT)
    tool.pickup_entity.assert_called_once()
    assert tool.place_entity.call_count == 1
    assert placed_at(tool) == (4.0, 4.0)


def test_shift_restores_entity_when_placement_raises():
    tool = make_tool(place_side_effect=[RuntimeError("engine rejected"), make_entity()])
    with pytest.raises(Exception, match="restored at"):
        tool(make_entity(), Direction.RIGHT)
    assert tool.place_entity.call_count == 2
    assert placed_at(tool, 0) == (5.0, 4.0)
    assert placed_at(tool, 1) == (4.0, 4.0)


def test_shift_reports_loudly_when_restore_fails():
    tool = make_tool(can_place=False, place_side_effect=[RuntimeError("no space")])
    with pytest.raises(Exception, match="remains in the inventory"):
        tool(make_entity(), Direction.RIGHT)
    tool.pickup_entity.assert_called_once()
    assert tool.place_entity.call_count == 1


def test_shift_passes_agent_direction_to_probe_and_place_for_inserters():
    tool = make_tool(place_side_effect=[make_entity(5.0, 4.0, Direction.EAST)])
    entity = make_entity(direction=Direction.EAST)
    entity.name = "burner-inserter"

    tool(entity, Direction.RIGHT)

    assert tool.can_place_entity.call_args.args[1] == Direction.EAST
    assert tool.place_entity.call_args.args[1] == Direction.EAST


def test_shift_does_not_mutate_the_source_entity_position():
    tool = make_tool()
    entity = make_entity()
    tool(entity, Direction.RIGHT, distance=3)
    assert (entity.position.x, entity.position.y) == (4.0, 4.0)
    assert placed_at(tool) == (7.0, 4.0)
