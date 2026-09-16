from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from lupa.lua54 import LuaRuntime

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.instance import NONE
from fle.env.tools.agent.connect_entities.client import ConnectEntities
from fle.env.tools.agent.move_to.client import MoveTo
from fle.env.tools.agent.place_path.client import PlacePath
from fle.env.tools.tool import Tool

pytestmark = pytest.mark.no_factorio

ROOT = Path(__file__).parents[2]


def move_client(fast: bool) -> MoveTo:
    tool = MoveTo.__new__(MoveTo)
    tool.player_index = 1
    tool.game_state = Mock()
    tool.game_state.player_location = Position(x=0.0, y=0.0)
    tool.game_state.instance.fast = fast
    tool.game_state._program_runtime = None
    tool._game_tick = Mock(return_value=100)
    return tool


def move_one(tool, goal):
    return tool._move_one(
        goal,
        laying=None,
        leading=None,
        stop_distance=0,
        interrupt_on=set(),
        timeout_ticks=100,
    )


def test_move_to_refreshes_the_stale_cache_before_requesting_a_path():
    tool = move_client(fast=True)
    tool.request_path = Mock(return_value="handle")
    tool.get_path = Mock(return_value=[Position(x=16.5, y=0.5)])
    tool.execute = Mock(
        side_effect=[
            ({"x": 17.0, "y": 2.3}, 0),
            ({"x": 16.5, "y": 0.5}, 0),
        ]
    )

    final, receipt = move_one(tool, Position(x=16.5, y=0.5))

    assert tool.execute.call_args_list[0] == call(1, "__position__", NONE, NONE, 0)
    assert tool.request_path.call_args.kwargs["start"] == Position(x=17.0, y=2.3)
    assert (final.x, final.y) == (16.5, 0.5)
    assert receipt["status"] == "completed"
    assert (
        tool.game_state.player_location.x,
        tool.game_state.player_location.y,
    ) == (16.5, 0.5)


def test_move_to_already_in_range_shortcut_uses_the_refreshed_position():
    tool = move_client(fast=False)
    tool.request_path = Mock()
    tool.get_path = Mock()
    tool.execute = Mock(return_value=({"x": 0.4, "y": 0.2}, 0))

    final, receipt = move_one(tool, Position(x=0.4, y=0.2))

    assert (final.x, final.y) == (0.4, 0.2)
    assert receipt["stop_reason"] == "already_in_range"
    assert receipt["ticks_elapsed"] == 0
    tool.request_path.assert_not_called()
    assert tool.execute.call_count == 1


def test_move_to_position_branch_returns_the_live_character():
    lua = LuaRuntime()
    lua.execute("""
        storage={actions={},agent_characters={},utils={},fast=true}
        script={on_event=function() end,on_nth_tick=function() end}
        defines={events={on_tick=1},direction={north=0,east=4,south=8,west=12}}
        game={tick=0}
        local character={valid=true,position={x=17,y=2.3}}
        storage.agent_characters[1]=character
        storage.utils.ensure_valid_character=function() return character end
    """)
    lua.execute(
        (ROOT / "fle/env/tools/agent/move_to/server.lua").read_text(encoding="utf-8")
    )
    result = lua.execute(
        "return storage.actions.move_to(1,'__position__','nil','nil',0)"
    )
    assert (result["x"], result["y"]) == (17, 2.3)


def test_ensure_reachable_refreshes_the_cache_before_the_distance_check(monkeypatch):
    walked = []

    class FakeMoveTo:
        def __init__(self, connection, game_state):
            walked.append(game_state)

        def __call__(self, position, stop_distance=0):
            raise AssertionError("walk should be skipped for the live position")

    monkeypatch.setattr("fle.env.tools.agent.move_to.client.MoveTo", FakeMoveTo)
    refresh = Mock(return_value=Position(x=17.0, y=2.3))
    tool = Tool.__new__(Tool)
    tool.name = "probe"
    tool.connection = Mock()
    tool.game_state = SimpleNamespace(
        player_location=Position(x=0.0, y=0.0),
        instance=SimpleNamespace(
            fast=False,
            controllers={"move_to": SimpleNamespace(refresh_player_location=refresh)},
        ),
    )

    result = tool.ensure_reachable(Position(x=18.0, y=2.5), stop_distance=5.5)

    refresh.assert_called_once()
    assert (result.x, result.y) == (17.0, 2.3)
    assert walked == []


def test_place_path_refreshes_the_cache_after_building():
    tool = PlacePath.__new__(PlacePath)
    tool.name = "place_path"
    tool.player_index = 1
    tool.connection = Mock()
    tool.connection.rcon_client.send_command = Mock(side_effect=["10", "20"])
    refresh = Mock(return_value=Position(x=2.0, y=0.5))
    state = Mock()
    state.player_location = Position(x=0.0, y=0.0)
    state.inspect_inventory.return_value = {Prototype.TransportBelt: 10}
    state.place_entity.return_value = SimpleNamespace(
        position=Position(x=0.0, y=0.0), id=1
    )
    state.instance.controllers = {
        "move_to": SimpleNamespace(refresh_player_location=refresh)
    }
    tool.game_state = state

    receipt = tool(Prototype.TransportBelt, [Position(0, 0), Position(1, 0)])

    assert receipt["status"] == "completed"
    refresh.assert_called_once()


def test_connect_entities_refreshes_the_cache_after_its_teleports():
    tool = ConnectEntities.__new__(ConnectEntities)
    tool.player_index = 1
    tool.connection = Mock()
    refresh = Mock(return_value=Position(x=30.0, y=40.0))
    state = Mock()
    state.player_location = Position(x=0.0, y=0.0)
    state.instance.get_elapsed_ticks = Mock(return_value=0)
    state.instance.controllers = {
        "move_to": SimpleNamespace(refresh_player_location=refresh)
    }
    tool.game_state = state
    tool._connect_pair_of_waypoints = Mock(return_value="connected")

    result = tool.__call_impl__(
        Position(0, 0),
        Position(1, 0),
        connection_type={Prototype.TransportBelt},
    )

    assert result == "connected"
    refresh.assert_called_once()
