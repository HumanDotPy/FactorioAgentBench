from unittest.mock import Mock

import pytest

from fle.env.entities import (
    BeltGroup,
    Direction,
    EntityStatus,
    Position,
    TransportBelt,
)
from fle.env.game_types import Prototype
from fle.env.tools.agent.get_entity.client import GROUP_RADIUS, GetEntity

pytestmark = pytest.mark.no_factorio


def _belt(x, y):
    return TransportBelt(
        name="transport-belt",
        direction=Direction.NORTH,
        position=Position(x=x, y=y),
        energy=0.0,
        health=100.0,
        dimensions={"width": 1, "height": 1},
        tile_dimensions={"tile_width": 1, "tile_height": 1},
        input_position=Position(x=x, y=y + 1),
        output_position=Position(x=x, y=y - 1),
    )


def _tool(groups):
    tool = GetEntity.__new__(GetEntity)
    tool.get_entities = Mock(return_value=groups)
    return tool


def _group():
    return BeltGroup(
        id=0,
        position=Position(x=5, y=5),
        status=EntityStatus.WORKING,
        inputs=[],
        outputs=[],
        belts=[_belt(5, 5), _belt(6, 5)],
    )


def test_group_query_is_bounded_and_reports_the_group(capsys):
    group = _group()
    tool = _tool([group])
    result = tool(Prototype.BeltGroup, Position(x=5, y=5))
    assert result is group
    _, kwargs = tool.get_entities.call_args
    assert kwargs["radius"] == GROUP_RADIUS
    assert kwargs["position"] == Position(x=5, y=5)
    output = capsys.readouterr().out
    assert "BeltGroup" in output
    assert "connected network" in output
    assert "2 members" in output


def test_group_query_without_match_returns_none(capsys):
    assert _tool([])(Prototype.PipeGroup, Position(x=9, y=9)) is None
    assert "connected network" not in capsys.readouterr().out
