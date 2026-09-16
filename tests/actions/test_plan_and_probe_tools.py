from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from fle.env import Direction
from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.can_place_entity.client import CanPlaceEntity
from fle.env.tools.agent.can_place_entity.plan_placement.client import PlanPlacement
from fle.env.tools.agent.place_path.plan_path.client import PlanPath
from fle.envd.program_policy import ProgramPolicyViolation, validate_program
from fle.envd.program_runtime import ProgramRuntime

pytestmark = pytest.mark.no_factorio


def make_probe(client_class, response):
    tool = client_class.__new__(client_class)
    tool.name = client_class.__name__
    tool.player_index = 1
    tool.execute = Mock(return_value=(response, 0))
    return tool


def test_can_place_entity_returns_false_for_normal_negatives():
    tool = make_probe(CanPlaceEntity, False)
    assert tool(Prototype.Pipe, position=Position(x=1, y=2)) is False
    assert tool(Prototype.Pipe, position=Position(x=1, y=2)) is False


def test_can_place_entity_returns_engine_verdict():
    assert make_probe(CanPlaceEntity, True)(
        Prototype.Pipe, direction=Direction.LEFT, position=Position(x=1, y=2)
    )
    response = {"placeable": False, "reason": "occupied"}
    assert (
        make_probe(CanPlaceEntity, response)(
            Prototype.Pipe, direction=Direction.LEFT, position=Position(x=1, y=2)
        )
        is False
    )


def test_can_place_entity_invalid_input_raises_value_error():
    tool = make_probe(CanPlaceEntity, False)
    with pytest.raises(ValueError, match="Prototype"):
        tool("pipe", position=Position(x=1, y=2))
    with pytest.raises(ValueError, match="Direction"):
        tool(Prototype.Pipe, direction=4, position=Position(x=1, y=2))
    with pytest.raises(ValueError, match="Position"):
        tool(Prototype.Pipe, position="somewhere")
    with pytest.raises(ValueError, match="typo"):
        make_probe(
            CanPlaceEntity, "pipe isn't a valid entity prototype. Did you make a typo?"
        )(Prototype.Pipe, position=Position(x=1, y=2))


def test_plan_placement_normalizes_blocks_and_reports_evidence():
    response = {
        "prototype": "stone-furnace",
        "position": {"x": 4.0, "y": 0.0},
        "direction": 0,
        "engine_direction": 0,
        "building": "furnace",
        "placeable": False,
        "within_reach": True,
        "inventory_count": 2,
        "reason": "occupied",
        "blocked_by": {
            "prototype": "tree-01",
            "position": {"x": 4.5, "y": 0.5},
            "type": "tree",
        },
        "overlapping_entities": {
            "1": {
                "prototype": "tree-01",
                "position": {"x": 4.5, "y": 0.5},
                "type": "tree",
            }
        },
    }
    report = make_probe(PlanPlacement, response)(
        Prototype.StoneFurnace, Position(x=4, y=0)
    )
    assert report["placeable"] is False
    assert report["blocked_by"]["prototype"] == "tree-01"
    assert isinstance(report["overlapping_entities"], list)
    assert report["overlapping_entities"][0]["prototype"] == "tree-01"


def test_plan_placement_rejects_invalid_input_and_missing_prototype():
    tool = make_probe(PlanPlacement, {"placeable": True})
    with pytest.raises(ValueError, match="Prototype"):
        tool("stone-furnace", Position(x=0, y=0))
    with pytest.raises(ValueError, match="Position"):
        tool(Prototype.StoneFurnace, "origin")
    with pytest.raises(ValueError, match="Direction"):
        tool(Prototype.StoneFurnace, Position(x=0, y=0), direction=3)
    with pytest.raises(ValueError, match="typo"):
        make_probe(
            PlanPlacement, "bogus isn't a valid entity prototype. Did you make a typo?"
        )(Prototype.StoneFurnace, Position(x=0, y=0))


def test_plan_path_rasterizes_width_lanes_without_mutating():
    response = {
        "prototype": "transport-belt",
        "placeable": False,
        "requested": 6,
        "blocked": 1,
        "tiles": {
            "1": {
                "position": {"x": 0.0, "y": 0.0},
                "direction": 4,
                "engine_direction": 4,
                "placeable": True,
            },
            "2": {
                "position": {"x": 1.0, "y": 0.0},
                "direction": 4,
                "engine_direction": 4,
                "placeable": False,
                "reason": "occupied",
                "blocked_by": {"prototype": "big-rock", "type": "simple-entity"},
            },
        },
    }
    tool = make_probe(PlanPath, response)
    report = tool(Position(x=0, y=0), Position(x=2, y=0), width=2)

    tiles = tool.execute.call_args[0][2]
    assert tiles == [
        {"x": 0.0, "y": 0.0, "direction": Direction.RIGHT.value},
        {"x": 0.0, "y": 1.0, "direction": Direction.RIGHT.value},
        {"x": 1.0, "y": 0.0, "direction": Direction.RIGHT.value},
        {"x": 1.0, "y": 1.0, "direction": Direction.RIGHT.value},
        {"x": 2.0, "y": 0.0, "direction": Direction.RIGHT.value},
        {"x": 2.0, "y": 1.0, "direction": Direction.RIGHT.value},
    ]
    assert report["status"] == "blocked"
    assert report["width"] == 2
    assert isinstance(report["tiles"], list)
    assert report["blockers"] == [report["tiles"][1]]
    assert report["blockers"][0]["blocked_by"]["prototype"] == "big-rock"


def test_plan_path_rejects_diagonals_width_and_invalid_links():
    tool = make_probe(PlanPath, {})
    with pytest.raises(ValueError, match="axis-aligned"):
        tool(Position(x=0, y=0), Position(x=2, y=2))
    with pytest.raises(ValueError, match="width"):
        tool(Position(x=0, y=0), Position(x=2, y=0), width=0)
    with pytest.raises(ValueError, match="prototype"):
        tool(Position(x=0, y=0), Position(x=2, y=0), prototype="belt")


def test_nested_plan_tools_load_their_parent_actions():
    plan_path = PlanPath.__new__(PlanPath)
    plan_path.lua_script_manager = Mock()
    PlanPath.load(plan_path)
    plan_path.lua_script_manager.load_tool_into_game.assert_called_once_with(
        "place_path"
    )

    plan_placement = PlanPlacement.__new__(PlanPlacement)
    plan_placement.lua_script_manager = Mock()
    PlanPlacement.load(plan_placement)
    plan_placement.lua_script_manager.load_tool_into_game.assert_called_once_with(
        "can_place_entity"
    )


def test_policy_allows_read_only_plan_tools_but_rejects_nonexact_builds():
    validate_program(
        "plan_placement(Prototype.StoneFurnace, Position(x=0, y=0))\n"
        "plan_path(Position(x=0, y=0), Position(x=5, y=0), width=2)\n"
        "can_place_entity(Prototype.Pipe, position=Position(x=0, y=0))"
    )
    with pytest.raises(ProgramPolicyViolation, match="non-exact"):
        validate_program(
            "place_entity(Prototype.StoneFurnace, position=Position(x=0, y=0), "
            "exact=False)"
        )


def test_place_path_partial_does_not_block_the_program(tmp_path):
    runtime = ProgramRuntime(tmp_path, None, None, nullcontext)
    job = runtime.submit("print(1)", "one", "hash1")
    runtime.active = job["program_id"]
    runtime.action_result(
        "place_path",
        {"status": "partial", "placed": 2, "resume_from": {"x": 2.0, "y": 0.0}},
    )
    runtime.boundary()
    assert runtime.blocked() is None
