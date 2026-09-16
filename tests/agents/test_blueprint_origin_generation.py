from types import SimpleNamespace

import pytest

from fle.agents.data.blueprints_to_policies.blueprint_analyzer_with_connect import (
    BlueprintAnalyzerWithConnect,
)
from fle.agents.data.blueprints_to_policies.trajectory_generator import (
    BlueprintEntity,
    create_origin_finding_code_trace,
    find_valid_origin,
)
from fle.env import BoundingBox, Position
from fle.env.game_types import Resource, prototype_by_name

pytestmark = pytest.mark.no_factorio


def _drill(x=0.5, y=0.5):
    return {
        "entity_number": 1,
        "name": "burner-mining-drill",
        "position": {"x": x, "y": y},
        "direction": 0,
    }


def test_find_valid_origin_uses_namespace_tool_with_required_arguments():
    drill = BlueprintEntity(
        entity_number=1,
        name="burner-mining-drill",
        position={"x": 10.0, "y": 20.0},
    )
    calls = {}

    def nearest_buildable(entity, building_box, center_position):
        calls["entity"] = entity
        calls["size"] = (building_box.width(), building_box.height())
        calls["center"] = center_position
        return BoundingBox(
            left_top=Position(0, 0),
            right_bottom=Position(1, 1),
            left_bottom=Position(0, 1),
            right_top=Position(1, 0),
        )

    game = SimpleNamespace(
        namespace=SimpleNamespace(nearest_buildable=nearest_buildable)
    )
    origin = find_valid_origin([drill], Resource.IronOre, game)
    assert origin is not None
    assert calls["entity"] is prototype_by_name["burner-mining-drill"]
    assert calls["size"] == (0.0, 0.0)
    assert calls["center"] == Position(10.0, 20.0)


def test_connect_analyzer_origin_uses_valid_bounding_box_and_center():
    program = BlueprintAnalyzerWithConnect({"entities": [_drill()]}).generate_program()
    compile(program, "<connect-analyzer>", "exec")
    assert "building_box=miner_box" in program
    assert "center_position=Position(" in program
    assert "left_bottom = Position(" in program
    assert "right_top = Position(" in program
    assert "origin = origin.center + left_top + Position(x=0.5, y=0.5)" in program
    assert "origin + left_top" not in program
    assert "bounding_box=" not in program


def test_origin_finding_trace_matches_the_tool_contract():
    drills = [
        BlueprintEntity(
            entity_number=1, name="burner-mining-drill", position={"x": 0, "y": 0}
        ),
        BlueprintEntity(
            entity_number=2, name="burner-mining-drill", position={"x": 3, "y": 0}
        ),
    ]
    trace = "\n".join(create_origin_finding_code_trace(drills, Resource.IronOre))
    compile(trace, "<origin-trace>", "exec")
    assert "center_position=center" in trace
    assert "building_box=miner_box" in trace
    assert "origin = origin.center" in trace
    assert "origin + left_top" not in trace
    assert "bounding_box=" not in trace
