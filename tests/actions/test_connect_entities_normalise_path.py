from pathlib import Path

from lupa.lua54 import LuaRuntime
import pytest

ROOT = Path(__file__).parents[2]

pytestmark = pytest.mark.no_factorio


def runtime():
    lua = LuaRuntime()
    lua.execute(
        """
        storage={actions={},utils={},agent_characters={}}
        defines={direction={north=0,east=4,south=8,west=12},events={on_tick=1}}
        script={on_nth_tick=function() end,on_event=function() end}
        game={surfaces={[1]={find_entities_filtered=function() return {} end,
            get_tile=function() return {name='grass-1'} end}}}
        """
    )
    for module in (
        "mods/initialise.lua",
        "mods/utils.lua",
        "tools/agent/connect_entities/server.lua",
    ):
        lua.execute((ROOT / "fle/env" / module).read_text(encoding="utf-8"))
    return lua


def test_normalise_path_snaps_each_axis_and_keeps_input_untouched():
    lua = runtime()
    values = lua.execute(
        """
        local original = {
            {position={x=10.5,y=5.0}},
            {position={x=13.5,y=5.0}},
        }
        local first = {x=10.5,y=5.0}
        local last = {x=20.0,y=15.0}
        local path, start_position, end_position =
            storage.utils.normalise_path(original, first, last)
        local repeated = storage.utils.normalise_path(original, first, last)
        return {
            raw_x=original[1].position.x,
            raw_y=original[1].position.y,
            first_x=path[1].position.x,
            first_y=path[1].position.y,
            last_x=path[#path].position.x,
            last_y=path[#path].position.y,
            input_x=first.x,
            input_y=first.y,
            start_x=start_position.x,
            start_y=start_position.y,
            end_x=end_position.x,
            end_y=end_position.y,
            repeat_first_x=repeated[1].position.x,
            repeat_first_y=repeated[1].position.y,
        }
        """
    )
    assert (values["raw_x"], values["raw_y"]) == (10.5, 5.0)
    assert (values["input_x"], values["input_y"]) == (10.5, 5.0)
    assert (values["start_x"], values["start_y"]) == (10.5, 5.5)
    assert (values["end_x"], values["end_y"]) == (20.5, 15.5)
    assert (values["first_x"], values["first_y"]) == (10.5, 5.5)
    assert (values["last_x"], values["last_y"]) == (20.5, 15.5)
    assert (values["repeat_first_x"], values["repeat_first_y"]) == (10.5, 5.5)
