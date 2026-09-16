"""Blueprint generator and VQA direction helpers must use Factorio 2.0 values."""

import pytest
from data.vqa.blueprint_transforms import (
    DirectionSystem,
    FlipType,
    detect_direction_system,
    flip_blueprint,
)
from data.vqa.direction_utils import (
    Direction,
    convert_numeric_direction,
    format_direction_in_text,
)

from fle.agents.data.blueprints_to_policies.blueprint_analyzer import (
    BlueprintAnalyzer,
)
from fle.agents.data.blueprints_to_policies.blueprint_analyzer_with_connect import (
    BlueprintAnalyzerWithConnect,
)
from fle.agents.data.blueprints_to_policies.blueprint_analyzer_with_place_next_to import (
    BlueprintAnalyzerWithPlaceNextTo,
)
from fle.agents.data.blueprints_to_policies.loop_generator import (
    BlueprintAnalyzer as LoopBlueprintAnalyzer,
)
from fle.agents.data.blueprints_to_policies.direction_semantics import (
    agent_direction,
    is_inserter_prototype,
)
from fle.agents.data.blueprints_to_policies.trajectory_generator import (
    direction_to_enum,
)

pytestmark = pytest.mark.no_factorio


def test_analyzers_emit_2_0_direction_enums():
    assert BlueprintAnalyzer._direction_to_enum(None, 0) == "Direction.UP"
    assert BlueprintAnalyzer._direction_to_enum(None, 4) == "Direction.RIGHT"
    assert BlueprintAnalyzer._direction_to_enum(None, 8) == "Direction.DOWN"
    assert BlueprintAnalyzer._direction_to_enum(None, 12) == "Direction.LEFT"
    assert BlueprintAnalyzerWithConnect._direction_to_enum(None, 4) == "Direction.RIGHT"
    assert (
        BlueprintAnalyzerWithPlaceNextTo._direction_to_enum(None, 8) == "Direction.DOWN"
    )
    assert LoopBlueprintAnalyzer._direction_to_enum(None, 12) == "Direction.LEFT"
    assert direction_to_enum(4) == "RIGHT"
    assert direction_to_enum(8) == "DOWN"
    assert direction_to_enum(12) == "LEFT"


def test_connect_analyzer_pairs_same_or_opposite_belts():
    opposite = {
        "entities": [
            {
                "entity_number": 1,
                "name": "transport-belt",
                "position": {"x": 0, "y": 0},
                "direction": 4,
            },
            {
                "entity_number": 2,
                "name": "transport-belt",
                "position": {"x": 1, "y": 0},
                "direction": 12,
            },
        ]
    }
    assert len(BlueprintAnalyzerWithConnect(opposite).find_belt_sequences()) == 1

    perpendicular = {
        "entities": [
            {
                "entity_number": 1,
                "name": "transport-belt",
                "position": {"x": 0, "y": 0},
                "direction": 4,
            },
            {
                "entity_number": 2,
                "name": "transport-belt",
                "position": {"x": 1, "y": 0},
                "direction": 0,
            },
        ]
    }
    assert len(BlueprintAnalyzerWithConnect(perpendicular).find_belt_sequences()) == 0


def test_detect_direction_system_treats_0_and_4_only_blueprints_as_2_0():
    blueprint = {"entities": [{"direction": 0}, {"direction": 4}]}
    assert detect_direction_system(blueprint) == DirectionSystem.NEW_SYSTEM


def test_detect_direction_system_uses_embedded_version():
    old = {"version": 1 << 48, "entities": [{"direction": 2}]}
    new = {"version": 2 << 48, "entities": [{"direction": 2}]}
    assert detect_direction_system(old) == DirectionSystem.OLD_SYSTEM
    assert detect_direction_system(new) == DirectionSystem.NEW_SYSTEM


def test_flip_blueprint_keeps_2_0_direction_values():
    blueprint = {
        "entities": [
            {
                "name": "transport-belt",
                "position": {"x": 0, "y": 0},
                "direction": 4,
            },
            {
                "name": "transport-belt",
                "position": {"x": 2, "y": 0},
                "direction": 12,
            },
        ]
    }
    flipped = flip_blueprint(blueprint, FlipType.HORIZONTAL, DirectionSystem.NEW_SYSTEM)
    ordered = sorted(flipped["entities"], key=lambda item: item["position"]["x"])
    assert [item["direction"] for item in ordered] == [4, 12]


def test_direction_enum_uses_2_0_values():
    assert Direction.NORTH.value == 0
    assert Direction.EAST.value == 4
    assert Direction.SOUTH.value == 8
    assert Direction.WEST.value == 12
    assert Direction.opposite(Direction.EAST) == Direction.WEST
    assert Direction.next_clockwise(Direction.NORTH) == Direction.EAST
    assert Direction.next_counterclockwise(Direction.NORTH) == Direction.WEST
    assert Direction.to_factorio_direction(Direction.SOUTH) == 2
    assert Direction.from_factorio_direction(3) == Direction.WEST


def test_from_value_snaps_16_way_values_and_reads_legacy_blueprints():
    assert Direction.from_value(0) == Direction.NORTH
    assert Direction.from_value(4) == Direction.EAST
    assert Direction.from_value(8) == Direction.SOUTH
    assert Direction.from_value(12) == Direction.WEST
    assert Direction.from_value(2) == Direction.EAST
    assert Direction.from_value(14) == Direction.NORTH
    assert Direction.from_value(4, DirectionSystem.OLD_SYSTEM) == Direction.SOUTH
    assert Direction.from_value("north") == Direction.NORTH


def test_inserters_convert_blueprint_direction_to_drop_side():
    assert is_inserter_prototype("burner-inserter")
    assert is_inserter_prototype("long-handed-inserter")
    assert not is_inserter_prototype("transport-belt")
    assert agent_direction("burner-inserter", 4) == 12
    assert agent_direction("burner-inserter", 12) == 4
    assert agent_direction("burner-inserter", 8) == 0
    assert agent_direction("transport-belt", 4) == 4
    assert agent_direction("electric-mining-drill", 8) == 8
    assert agent_direction("unknown-inserter", 0) == 8
    assert agent_direction("transport-belt", None) is None


def test_generators_emit_drop_side_direction_for_inserters():
    assert (
        BlueprintAnalyzer._direction_to_enum(None, 4, "burner-inserter")
        == "Direction.LEFT"
    )
    assert (
        BlueprintAnalyzerWithConnect._direction_to_enum(None, 0, "fast-inserter")
        == "Direction.DOWN"
    )
    assert (
        BlueprintAnalyzerWithPlaceNextTo._direction_to_enum(None, 8, "bulk-inserter")
        == "Direction.UP"
    )
    assert (
        LoopBlueprintAnalyzer._direction_to_enum(None, 12, "inserter")
        == "Direction.RIGHT"
    )
    assert direction_to_enum(4, "burner-inserter") == "LEFT"
    assert direction_to_enum(4, "transport-belt") == "RIGHT"


def test_generated_program_uses_drop_side_for_blueprint_inserter():
    blueprint = {
        "entities": [
            {
                "entity_number": 1,
                "name": "burner-inserter",
                "position": {"x": 0, "y": 0},
                "direction": 4,
            }
        ]
    }
    program = BlueprintAnalyzer(blueprint).generate_program()
    assert "Direction.LEFT" in program
    assert "Direction.RIGHT" not in program


def test_convert_numeric_direction_uses_system():
    assert convert_numeric_direction(4, DirectionSystem.NEW_SYSTEM) == "east"
    assert convert_numeric_direction(4, DirectionSystem.OLD_SYSTEM) == "south"
    assert convert_numeric_direction(2, DirectionSystem.NEW_SYSTEM) == "east"


def test_format_direction_in_text_handles_2_0_values():
    assert format_direction_in_text("direction=12") == "facing west"
    assert format_direction_in_text("facing 0") == "facing north"
