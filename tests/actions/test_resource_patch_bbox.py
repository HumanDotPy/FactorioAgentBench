import pytest

from tests.actions.lua_stub_helpers import lua_stub

pytestmark = pytest.mark.no_factorio


def server_runtime():
    return lua_stub(
        """
        storage={actions={},agent_characters={}}
        rendering={is_valid=function() return false end,
            destroy=function() end, draw_circle=function() end}
        water_tiles={
            {position={x=0,y=0}}, {position={x=1,y=0}},
        }
        ore_entities={
            {name='iron-ore', amount=100, position={x=0.5,y=0.5},
                bounding_box={left_top={x=0,y=0},right_bottom={x=1,y=1}}},
            {name='iron-ore', amount=50, position={x=1.5,y=0.5},
                bounding_box={left_top={x=1,y=0},right_bottom={x=2,y=1}}},
        }
        trees={
            {position={x=2.5,y=2.5},
                bounding_box={left_top={x=2.2,y=2.2},
                    right_bottom={x=2.8,y=2.8}},
                prototype={mineable_properties={products={{name='wood',amount=4}}}}},
        }
        surface={
            find_tiles_filtered=function() return water_tiles end,
            find_entities_filtered=function(query)
                if query.type=='tree' then return trees end
                return ore_entities
            end,
        }
        storage.agent_characters[1]={surface=surface}
        """,
        "tools/agent/get_resource_patch/server.lua",
    )


def test_water_bbox_uses_tile_extents_symmetrically():
    lua = server_runtime()
    result = lua.execute("""
        local patch=storage.actions.get_resource_patch(1,'water',0.5,0.0,5)
        local box=patch.bounding_box
        assert(box.left_top.x==-0.5 and box.left_top.y==-0.5)
        assert(box.right_bottom.x==1.5 and box.right_bottom.y==0.5)
        return 'ok'
    """)
    assert result == "ok"


def test_ore_bbox_uses_entity_bounds():
    lua = server_runtime()
    result = lua.execute("""
        local patch=storage.actions.get_resource_patch(1,'iron-ore',0.5,0.5,5)
        local box=patch.bounding_box
        assert(box.left_top.x==0 and box.left_top.y==0)
        assert(box.right_bottom.x==2 and box.right_bottom.y==1)
        assert(patch.size==150)
        return 'ok'
    """)
    assert result == "ok"


def test_wood_bbox_uses_tree_bounds():
    lua = server_runtime()
    result = lua.execute("""
        local patch=storage.actions.get_resource_patch(1,'wood',2.5,2.5,5)
        local box=patch.bounding_box
        assert(math.abs(box.left_top.x-2.2) < 1e-9)
        assert(math.abs(box.right_bottom.x-2.8) < 1e-9)
        assert(patch.size==4)
        return 'ok'
    """)
    assert result == "ok"
