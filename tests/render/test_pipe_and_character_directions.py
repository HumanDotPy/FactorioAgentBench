"""Pipe, heat-pipe and character renderers must speak Factorio 2.0 directions."""

import pytest

from fle.env.tools.admin.render.renderers import character, heat_pipe, pipe

pytestmark = pytest.mark.no_factorio


class Grid:
    def __init__(self, entities=None):
        self.entities = entities or {}
        self.center_x = 0.0
        self.center_y = 0.0

    def get_relative(self, dx, dy):
        return self.entities.get((dx, dy))


def entity(name, x=0.0, y=0.0, direction=0):
    return {"name": name, "position": {"x": x, "y": y}, "direction": direction}


def test_pipe_to_ground_connects_toward_its_direction():
    assert pipe.is_pipe(entity("pipe-to-ground", direction=4), 4) == 1
    assert pipe.is_pipe(entity("pipe-to-ground", direction=4), 12) == 0
    assert pipe.is_pipe(entity("pipe-to-ground", direction=12), 12) == 1


def test_pipe_around_uses_2_0_directions():
    connected = Grid({(1, 0): entity("pipe-to-ground", x=1, y=0, direction=12)})
    assert pipe.get_around(entity("pipe"), connected) == [0, 1, 0, 0]

    away = Grid({(1, 0): entity("pipe-to-ground", x=1, y=0, direction=4)})
    assert pipe.get_around(entity("pipe"), away) == [0, 0, 0, 0]


def test_offshore_pump_direction_points_toward_water():
    toward_pipe = Grid({(0, -1): entity("offshore-pump", x=0, y=-1, direction=0)})
    assert pipe.get_around(entity("pipe"), toward_pipe)[0] == 1

    away_from_pipe = Grid({(0, -1): entity("offshore-pump", x=0, y=-1, direction=8)})
    assert pipe.get_around(entity("pipe"), away_from_pipe)[0] == 0


def test_boiler_and_engine_connection_points_use_2_0_directions():
    assert pipe.get_boiler_connection_points(0, 0, 0) == [
        (1.5, 0.5),
        (-1.5, 0.5),
        (0, -0.5),
    ]
    assert pipe.get_boiler_connection_points(0, 0, 4) == [
        (-0.5, 1.5),
        (-0.5, -1.5),
        (0.5, 0),
    ]
    assert pipe.get_steam_engine_connection_points(0, 0, 8) == [(0, -2), (0, 2)]
    assert pipe.get_steam_engine_connection_points(0, 0, 4) == [(-2, 0), (2, 0)]


def test_heat_pipe_exchanger_connections_use_2_0_directions():
    north = Grid({(0, -1.5): entity("heat-exchanger", x=0, y=-1.5, direction=0)})
    assert heat_pipe.get_around(entity("heat-pipe"), north)[0] == 1

    east = Grid({(1.5, 0): entity("heat-exchanger", x=1.5, y=0, direction=4)})
    assert heat_pipe.get_around(entity("heat-pipe"), east)[1] == 1

    wrong_way = Grid({(1.5, 0): entity("heat-exchanger", x=1.5, y=0, direction=12)})
    assert heat_pipe.get_around(entity("heat-pipe"), wrong_way)[1] == 0


def test_character_sprite_index_maps_use_2_0_directions():
    mapping = character.DIRECTION_MAPPINGS["standard"]
    assert mapping[0] == 0
    assert mapping[4] == 2
    assert mapping[8] == 4
    assert mapping[12] == 6


def test_character_render_requests_east_sprite_variant():
    requested = []

    def resolver(name, *args):
        requested.append(name)
        return None

    entity_dict = {
        "name": "character",
        "position": {"x": 0, "y": 0},
        "direction": 4,
        "state": "idle",
        "level": 1,
        "has_gun": False,
        "animation_frame": 0,
    }
    character.render(entity_dict, None, resolver)
    assert requested[0] == "character/level1_idle_2_0"
