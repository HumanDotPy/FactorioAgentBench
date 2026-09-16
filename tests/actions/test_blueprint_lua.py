"""Blueprint capture pre-flight and stable ghost paging (stub world)."""

import pytest

from tests.actions.lua_stub_helpers import lua_stub

pytestmark = pytest.mark.no_factorio

PREAMBLE = """
storage={actions={},utils={},agent_characters={}}
defines={direction={north=0,east=4,south=8,west=12},
    build_mode={normal=1,forced=2,superforced=3}}
prototypes={entity={},item={}}
game={}
capture_calls=0
capture_params=nil
tile_count_value=3
stack={
    set_stack=function() end,
    create_blueprint=function(params) capture_calls=capture_calls+1; capture_params=params end,
    is_blueprint_setup=function() return true end,
    export_stack=function() return "0stub" end,
    get_blueprint_entity_count=function() return 1 end,
    get_blueprint_tiles=function() return {1,2,3} end,
}
game.create_inventory=function() return {[1]=stack, destroy=function() end} end
surface={
    count_entities_filtered=function() return 1 end,
    count_tiles_filtered=function() return tile_count_value end,
    find_entities_filtered=function()
        return {
            {valid=true, type="entity-ghost", ghost_name="transport-belt",
                position={x=2.5,y=0.5}, direction=4},
            {valid=true, type="entity-ghost", ghost_name="stone-furnace",
                position={x=0.5,y=3.5}, direction=0},
            {valid=true, type="tile-ghost", ghost_name="stone-path",
                position={x=0.5,y=0.5}, direction=0},
        }
    end,
}
storage.agent_characters[1]={valid=true, surface=surface}
"""


def runtime():
    return lua_stub(PREAMBLE, "tools/agent/blueprint/server.lua", unpack=True)


def test_capture_rejects_oversized_area_before_creating_the_blueprint():
    lua = runtime()
    lua.execute("tile_count_value=200000")
    result = lua.eval("storage.actions.blueprint(1, 'capture', 0, 0, 128, {})")
    assert "estimated" in result["error"]
    assert result["estimated_bytes"] > 512 * 1024
    assert lua.eval("capture_calls") == 0


def test_capture_honors_include_tiles():
    lua = runtime()
    omitted = lua.eval(
        "storage.actions.blueprint(1, 'capture', 1, 2, 16, {include_tiles=false})"
    )
    assert omitted["tile_count"] == 3
    assert lua.eval("capture_params.always_include_tiles") is False
    lua.execute("capture_params=nil")
    included = lua.eval("storage.actions.blueprint(1, 'capture', 1, 2, 16, {})")
    assert included["included_tiles"] is True
    assert lua.eval("capture_params.always_include_tiles") is True


def test_ghosts_page_in_stable_position_order_with_usable_ids():
    lua = runtime()
    first = lua.eval("storage.actions.blueprint(1, 'ghosts', 0, 0, 32, {offset=0})")
    assert first["total"] == 3
    assert [ghost["name"] for ghost in first["ghosts"].values()] == [
        "stone-path",
        "stone-furnace",
        "transport-belt",
    ]
    assert all(
        isinstance(ghost["entity_id"], str) and ghost["entity_id"].startswith("ghost:")
        for ghost in first["ghosts"].values()
    )
    second = lua.eval("storage.actions.blueprint(1, 'ghosts', 0, 0, 32, {offset=2})")
    assert second["offset"] == 2
    assert len(second["ghosts"]) == 1
    assert list(second["ghosts"].values())[0]["name"] == "transport-belt"
    assert list(second["ghosts"].values())[0]["item_requests"] is None


def test_ghost_id_includes_name_type_and_position():
    lua = runtime()
    result = lua.eval("storage.actions.blueprint(1, 'ghosts', 0, 0, 32, {offset=0})")
    ids = [ghost["entity_id"] for ghost in result["ghosts"].values()]
    assert "ghost:stone-path:tile-ghost:0.500:0.500" in ids
