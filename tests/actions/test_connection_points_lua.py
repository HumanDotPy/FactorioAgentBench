"""Connector pipe tiles for fluid machines, pinned to live 2.0.77 evidence.

Each expected tuple is a delta from the entity position where a pipe actually
links to the machine (verified in a reference world by placing pipes and
reading the resulting fluid connections), not the inner fluidbox anchor.
"""

import pytest

from tests.actions.lua_stub_helpers import lua_stub

pytestmark = pytest.mark.no_factorio


def runtime():
    return lua_stub(
        "defines={direction={north=0,east=4,south=8,west=12}}; storage={utils={}}",
        "mods/connection_points.lua",
    )


def points(lua, function_name, direction, x=0, y=0):
    result = lua.eval(
        "storage.utils.%s({position={x=%s,y=%s},direction=%d})"
        % (function_name, x, y, direction)
    )
    return sorted(
        (round(result[index]["x"], 2), round(result[index]["y"], 2))
        for index in range(1, len(result) + 1)
    )


@pytest.mark.parametrize(
    "function_name,direction,expected",
    [
        (
            "get_chemical_plant_connection_points",
            0,
            [(-1, -2), (-1, 2), (1, -2), (1, 2)],
        ),
        (
            "get_chemical_plant_connection_points",
            4,
            [(-2, -1), (-2, 1), (2, -1), (2, 1)],
        ),
        (
            "get_chemical_plant_connection_points",
            12,
            [(-2, -1), (-2, 1), (2, -1), (2, 1)],
        ),
        (
            "get_refinery_connection_points",
            0,
            [(-2, -3), (-1, 3), (0, -3), (1, 3), (2, -3)],
        ),
        (
            "get_refinery_connection_points",
            4,
            [(-3, -1), (-3, 1), (3, -2), (3, 0), (3, 2)],
        ),
        (
            "get_refinery_connection_points",
            8,
            [(-2, 3), (-1, -3), (0, 3), (1, -3), (2, 3)],
        ),
        ("get_pumpjack_connection_points", 0, [(1, -2)]),
        ("get_pumpjack_connection_points", 4, [(2, -1)]),
        ("get_pumpjack_connection_points", 8, [(-1, 2)]),
        ("get_pumpjack_connection_points", 12, [(-2, 1)]),
        ("get_boiler_connection_points", 0, [(-2, 0.5), (0, -1.5), (2, 0.5)]),
        ("get_boiler_connection_points", 4, [(-0.5, -2), (-0.5, 2), (1.5, 0)]),
        ("get_boiler_connection_points", 8, [(-2, -0.5), (0, 1.5), (2, -0.5)]),
        ("get_boiler_connection_points", 12, [(-1.5, 0), (0.5, -2), (0.5, 2)]),
        ("get_heat_exchanger_connection_points", 0, [(-2, 0.5), (0, -1.5), (2, 0.5)]),
        ("get_storage_tank_connection_points", 0, [(-2, -1), (-1, -2), (1, 2), (2, 1)]),
        ("get_storage_tank_connection_points", 4, [(-2, 1), (-1, 2), (1, -2), (2, -1)]),
        ("get_generator_connection_positions", 0, [(0, -3), (0, 3)]),
        ("get_generator_connection_positions", 4, [(-3, 0), (3, 0)]),
        ("get_pipe_to_ground_connection_points", 4, [(1, 0)]),
        ("get_pump_connection_points", 8, [(0, -1.5), (0, 1.5)]),
        ("get_offshore_pump_connection_points", 0, [(0, 1)]),
    ],
)
def test_live_verified_pipe_tile_geometry(function_name, direction, expected):
    assert points(runtime(), function_name, direction) == expected


def test_offsets_are_relative_to_entity_position():
    lua = runtime()
    assert points(lua, "get_pumpjack_connection_points", 0, x=10.5, y=-4.5) == [
        (11.5, -6.5)
    ]
