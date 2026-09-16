import pytest

from fle.env.entities import Direction, EntityStatus, Pipe, Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.connect_entities.groupable_entities import _construct_group

pytestmark = pytest.mark.no_factorio


def _pipe(x, contents, flow_rate=0.0):
    return Pipe(
        name="pipe",
        direction=Direction.NORTH,
        position=Position(x=x, y=0),
        energy=0.0,
        health=100.0,
        dimensions={"width": 1, "height": 1},
        tile_dimensions={"tile_width": 1, "tile_height": 1},
        fluidbox_id=7,
        contents=contents,
        flow_rate=flow_rate,
    )


def _group(pipes):
    return _construct_group(
        id=7, entities=pipes, prototype=Prototype.Pipe, position=pipes[0].position
    )


def test_full_static_pipe_is_working_not_full_output():
    group = _group([_pipe(0, 100.0)])
    assert group.status == EntityStatus.WORKING


def test_empty_pipes_are_empty():
    group = _group([_pipe(0, 0.0), _pipe(1, 0.0)])
    assert group.status == EntityStatus.EMPTY


def test_pipe_group_deduplicates_positions():
    group = _group([_pipe(0, 25.0), _pipe(0, 25.0), _pipe(1, 0.0)])
    assert len(group.pipes) == 2
    assert group.status == EntityStatus.WORKING
