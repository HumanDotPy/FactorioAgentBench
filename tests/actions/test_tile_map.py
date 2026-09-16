from pathlib import Path
from unittest.mock import Mock

import pytest
from lupa.lua54 import LuaError, LuaRuntime

from fle.env.entities import Position
from fle.env.tools.agent.get_tile_map.client import GetTileMap

pytestmark = pytest.mark.no_factorio


def runtime():
    # Engine-fidelity mocks: real LuaObjects raise when a member does not exist
    # ("LuaSurface doesn't contain key get_tiles." on 2.0.77), while plain Lua
    # tables silently return nil. get_tiles was removed in 2.0, so the mock must
    # reject it instead of letting production Lua read it past this suite.
    lua = LuaRuntime()
    lua.execute("""
        storage={actions={},agent_characters={[1]={surface=nil}},utils={}}
        entity_list={}
        tiles={}
        defines={entity_status={working=1,no_fuel=2,waiting_for_source_items=3,normal=4},
            inventory={chest=1,crafter_input=2,furnace_source=3,fuel=4}}
        storage.utils.get_contents_compat=function(inventory)
            local counts={}
            if inventory and inventory.get_contents then
                for _,item in ipairs(inventory.get_contents()) do
                    counts[item.name]=(counts[item.name] or 0)+item.count
                end
            end
            return counts
        end
        storage.utils.inserter_engine_direction=function(entity_name,direction)
            if type(direction)~='number' then return direction end
            local name=tostring(entity_name)
            if name:find('inserter') then return (direction+8)%16 end
            return direction
        end
        function strict_engine_object(class_name, members)
            return setmetatable(members, {__index=function(_, key)
                error(class_name.." doesn't contain key "..tostring(key), 2)
            end})
        end
        function add_entity(x,y,entity)
            entity.bounding_box={
                left_top={x=x+0.1,y=y+0.1},
                right_bottom={x=x+0.9,y=y+0.9}}
            entity_list[#entity_list+1]={x=x,y=y,entity=entity}
        end
        function tile_at(x,y)
            local name=tiles[string.format('%d,%d',x,y)] or 'grass-1'
            return strict_engine_object('LuaTile', {
                name=name,
                position={x=x,y=y},
                collides_with=function(layer)
                    return name=='water' or name=='cliff'
                end,
            })
        end
        surface=strict_engine_object('LuaSurface', {
            find_entities_filtered=function(query)
                local out={}
                for _,entry in ipairs(entity_list) do
                    local match=false
                    if query.area then
                        local lt=query.area[1]; local rb=query.area[2]
                        match=entry.x>=lt[1] and entry.x<rb[1]
                            and entry.y>=lt[2] and entry.y<rb[2]
                    elseif query.position then
                        local r=query.radius or 0.5
                        local px,py=query.position.x,query.position.y
                        match=math.abs(entry.entity.position.x-px)<=r
                            and math.abs(entry.entity.position.y-py)<=r
                    end
                    if match then out[#out+1]=entry.entity end
                    if query.limit and #out>=query.limit then break end
                end
                return out
            end,
            find_tiles_filtered=function(query)
                local lt=query.area[1]; local rb=query.area[2]
                local out={}
                for x=lt[1],rb[1]-1 do
                    for y=lt[2],rb[2]-1 do
                        out[#out+1]=tile_at(x,y)
                    end
                end
                return out
            end,
            get_tile=tile_at,
        })
        storage.agent_characters[1].surface=surface
    """)
    lua.execute(
        (
            Path(__file__).parents[2] / "fle/env/tools/agent/get_tile_map/server.lua"
        ).read_text()
    )
    return lua


def test_tile_map_marks_machines_resources_and_terrain():
    lua = runtime()
    lua.execute("""
        add_entity(0,0,{name='transport-belt', type='transport-belt',
            position={x=0,y=0}, direction=4, unit_number=1, status=1})
        add_entity(1,0,{name='small-electric-pole', type='electric-pole',
            position={x=1,y=0}, direction=0, unit_number=2, status=1})
        add_entity(-1,0,{name='iron-ore', type='resource',
            position={x=-1,y=0}, direction=0, unit_number=3, status=1})
        add_entity(0,-1,{name='stone-furnace', type='furnace',
            position={x=0,y=-1}, direction=0, unit_number=4, status=1})
        add_entity(0,1,{name='inserter', type='inserter',
            position={x=0,y=1}, direction=0, unit_number=5, status=1})
        tiles['1,1']='water'
        tiles['-1,-1']='cliff'
        result=storage.actions.get_tile_map(1,0,0,2)
        assert(#result.rows==5)
        assert(result.rows[1]=='.....')
        assert(result.rows[2]=='.#F..')
        assert(result.rows[3]=='.*>P.')
        assert(result.rows[4]=='..I~.')
        assert(result.rows[5]=='.....')
        assert(#result.entities==4 and result.entities_truncated==false)
        assert(result.legend:find('belts') ~= nil)
    """)


def test_tile_map_marks_neutral_obstacles_and_character():
    lua = runtime()
    lua.execute("""
        add_entity(0,0,{name='tree-04', type='tree',
            position={x=0,y=0}, direction=0, unit_number=7, status=1})
        add_entity(1,0,{name='big-rock', type='simple-entity',
            position={x=1,y=0}, direction=0, unit_number=8, status=1})
        add_entity(-1,0,{name='tree-07-stump', type='corpse',
            position={x=-1,y=0}, direction=0, unit_number=9, status=1})
        add_entity(0,1,{name='character', type='character',
            position={x=0,y=1}, direction=0, unit_number=10, status=1})
        result=storage.actions.get_tile_map(1,0,0,1)
        assert(result.rows[1]=='...')
        assert(result.rows[2]=='stR')
        assert(result.rows[3]=='.@.')
        assert(#result.entities==4)
        assert(result.legend:find('tree') ~= nil)
        assert(result.legend:find('rock') ~= nil)
    """)


def test_tile_map_covers_all_belt_types_and_item_on_ground():
    lua = runtime()
    lua.execute("""
        add_entity(0,0,{name='fast-transport-belt', type='transport-belt',
            position={x=0,y=0}, direction=4, unit_number=1, status=1})
        add_entity(1,0,{name='express-transport-belt', type='transport-belt',
            position={x=1,y=0}, direction=0, unit_number=2, status=1})
        add_entity(-1,0,{name='underground-belt', type='underground-belt',
            position={x=-1,y=0}, direction=8, unit_number=3, status=1})
        add_entity(0,1,{name='item-on-ground', type='item-on-ground',
            position={x=0,y=1}, direction=0, unit_number=nil, status=nil,
            stack={valid_for_read=true,name='iron-ore',count=7}})
        result=storage.actions.get_tile_map(1,0,0,2)
        assert(result.rows[3]:sub(2,4)=='v>^')
        assert(result.rows[4]:sub(3,3)=='o')
        local ground=nil
        for _,e in ipairs(result.entities) do
            if e.type=='item-on-ground' then ground=e end
        end
        assert(ground.item=='iron-ore' and ground.count==7)
        assert(ground.status=='unknown')
        assert(#result.entities==4)
    """)


def test_tile_map_counts_multitile_entities_once_and_explains_stalls():
    lua = runtime()
    lua.execute("""
        add_entity(2,0,{name='assembling-machine-1', type='assembling-machine',
            position={x=2.5,y=0.5}, direction=0, unit_number=1, status=4})
        entity_list[#entity_list].entity.bounding_box={
            left_top={x=2,y=0}, right_bottom={x=4,y=2}}
        add_entity(5,0,{name='burner-inserter', type='inserter',
            position={x=5,y=0}, direction=4, unit_number=2, status=3,
            pickup_position={x=4,y=0}, drop_position={x=7,y=0}})
        add_entity(4,0,{name='iron-chest', type='container',
            position={x=4,y=0}, direction=0, unit_number=3, status=4,
            get_inventory=function(kind)
                return {get_contents=function()
                    return {{name='coal',count=3}}
                end}
            end})
        result=storage.actions.get_tile_map(1,3,0,3)
        local assemblers=0
        local assembler=nil
        local inserter=nil
        for _,e in ipairs(result.entities) do
            if e.name=='assembling-machine-1' then
                assemblers=assemblers+1
                assembler=e
            elseif e.type=='inserter' then
                inserter=e
            end
        end
        assert(assemblers==1)
        assert(assembler.status=='normal')
        local glyph_count=0
        for _,row in ipairs(result.rows) do
            for i=1,#row do
                if row:sub(i,i)=='A' then glyph_count=glyph_count+1 end
            end
        end
        assert(glyph_count==4)
        assert(inserter.status=='waiting_for_source_items')
        assert(inserter.pickup_target=='iron-chest')
        assert(inserter.source_inventory['coal']==3)
        assert(inserter.drop_position.x==7)
        assert(inserter.drop_target==nil)
        assert(inserter.direction==12)
    """)


def test_tile_map_bounds_are_clamped():
    lua = runtime()
    lua.execute("""
        small=storage.actions.get_tile_map(1,10,10,0)
        assert(small.radius==1 and #small.rows==3)
        large=storage.actions.get_tile_map(1,10,10,1000)
        assert(large.radius==32 and #large.rows==65)
    """)


def test_engine_mocks_reject_removed_surface_and_tile_members():
    # Canary for the mock contract: 2.0.77 LuaSurface has no get_tiles and
    # LuaTile has no walkable, so production Lua reading either must fail here.
    lua = runtime()
    with pytest.raises(LuaError, match="LuaSurface doesn't contain key get_tiles"):
        lua.execute("return surface.get_tiles")
    with pytest.raises(LuaError, match="LuaTile doesn't contain key walkable"):
        lua.execute("return surface.get_tile(0, 0).walkable")


def test_client_validates_center_and_radius():
    tool = GetTileMap.__new__(GetTileMap)
    tool.player_index = 1
    tool.game_state = Mock()
    tool.game_state._program_runtime = None
    tool.name = "get_tile_map"
    tool.execute = Mock(return_value=({"rows": []}, 0))
    with pytest.raises(ValueError, match="center must be a Position"):
        tool((0, 0))
    with pytest.raises(ValueError, match="radius"):
        tool(Position(x=0, y=0), radius=0)
    tool.execute = Mock(return_value=(True, 0))
    with pytest.raises(Exception, match="Could not build tile map"):
        tool(Position(x=0, y=0))


def test_client_normalizes_lua_arrays_to_lists():
    from fle.env.tools.agent.get_tile_map.client import _normalize_arrays

    assert _normalize_arrays({1: "a", 2: "b"}) == ["a", "b"]
    assert _normalize_arrays(
        {"rows": {1: "x"}, "entities": {1: {"position": {1: 3, 2: 4}}}}
    ) == {"rows": ["x"], "entities": [{"position": [3, 4]}]}
