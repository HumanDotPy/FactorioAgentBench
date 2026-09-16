import pytest

from tests.actions.lua_stub_helpers import lua_stub

pytestmark = pytest.mark.no_factorio


def server_runtime():
    return lua_stub(
        """
        storage={actions={},utils={},agent_characters={}}
        prototypes={entity={["stone-furnace"]={tile_width=2, tile_height=2}}}
        queries={}
        candidates={}
        surface={find_entities_filtered=function(query)
            queries[#queries+1]=query
            return candidates
        end}
        player={surface=surface}
        storage.utils.ensure_valid_character=function() return player end
        storage.utils.serialize_entity=function(entity)
            return {name=entity.name, position=entity.position}
        end
        """,
        "tools/agent/get_entity/server.lua",
    )


def test_get_entity_searches_the_prototype_footprint():
    lua = server_runtime()
    result = lua.execute("""
        candidates={
            {name='stone-furnace', position={x=0.5,y=0.5},
                bounding_box={left_top={x=-0.5,y=-0.5},
                    right_bottom={x=1.5,y=1.5}}},
        }
        local found=storage.actions.get_entity(1,'stone-furnace',0.5,0.5)
        assert(found.name=='stone-furnace')
        local area=queries[1].area
        assert(math.abs((area[2][1]-area[1][1])-2) < 0.05)
        assert(math.abs((area[2][2]-area[1][2])-2) < 0.05)
        return 'ok'
    """)
    assert result == "ok"


def test_get_entity_prefers_the_footprint_containing_the_position():
    lua = server_runtime()
    result = lua.execute("""
        candidates={
            {name='stone-furnace', position={x=0.0,y=0.0},
                bounding_box={left_top={x=-0.3,y=-0.3},
                    right_bottom={x=0.3,y=0.3}}},
            {name='stone-furnace', position={x=1.0,y=1.0},
                bounding_box={left_top={x=-1.0,y=-1.0},
                    right_bottom={x=2.0,y=2.0}}},
        }
        local found=storage.actions.get_entity(1,'stone-furnace',0.4,0.4)
        assert(found.position.x==1.0 and found.position.y==1.0)
        return 'ok'
    """)
    assert result == "ok"


def test_get_entity_falls_back_to_the_closest_when_none_contains():
    lua = server_runtime()
    result = lua.execute("""
        candidates={
            {name='stone-furnace', position={x=0.0,y=0.0},
                bounding_box={left_top={x=-0.5,y=-0.5},
                    right_bottom={x=0.5,y=0.5}}},
            {name='stone-furnace', position={x=6.0,y=6.0},
                bounding_box={left_top={x=5.5,y=5.5},
                    right_bottom={x=6.5,y=6.5}}},
        }
        local found=storage.actions.get_entity(1,'stone-furnace',3.0,3.0)
        assert(found.position.x==0.0 and found.position.y==0.0)
        return 'ok'
    """)
    assert result == "ok"
