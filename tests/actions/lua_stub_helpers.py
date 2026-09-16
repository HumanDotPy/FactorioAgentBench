from pathlib import Path
from unittest.mock import Mock

from lupa.lua54 import LuaRuntime

ROOT = Path(__file__).parents[2]
ENV = ROOT / "fle/env"


def env_source(*parts):
    return (ENV / Path(*parts)).read_text(encoding="utf-8")


def load_env(lua, *parts):
    lua.execute(env_source(*parts))
    return lua


def lua_stub(preamble, *modules, unpack=False):
    lua = LuaRuntime(unpack_returned_tuples=unpack)
    lua.execute(preamble)
    for module in modules:
        load_env(lua, module)
    return lua


def stub_client(tool_class, *, player_index=1, response=None, side_effect=None):
    tool = tool_class.__new__(tool_class)
    tool.player_index = player_index
    if response is not None:
        tool.execute = Mock(return_value=(response, 0))
    elif side_effect is not None:
        tool.execute = Mock(side_effect=side_effect)
    return tool
