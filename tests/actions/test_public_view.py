from pathlib import Path
from unittest.mock import Mock

from lupa.lua54 import LuaRuntime
import pytest

from fle.env.tools.admin.public_view.client import PublicView


pytestmark = pytest.mark.no_factorio


def test_map_bounds_unknown_coverage_and_no_detailed_serialization():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        storage={actions={},agent_characters={}}
        game={tick=120}
        surface={index=1,
            is_chunk_generated=function(p) return p[1]>=0 end,
            count_tiles_filtered=function(f) assert(f.area); return 0 end,
            count_entities_filtered=function(f) assert(f.area); return 0 end,
            find_entities_filtered=function(f) assert(f.limit==9); return {} end}
        storage.agent_characters[1]={valid=true,surface=surface,force={},position={x=0,y=0}}
    """)
    lua.execute(
        (
            Path(__file__).parents[2] / "fle/env/tools/admin/public_view/server.lua"
        ).read_text(encoding="utf-8")
    )
    lua.execute("""
        result=storage.actions.public_view(1,192,8)
        assert(#result.cells<=256 and #result.entities==0)
        assert(result.detail=='map' and result.tick==120 and game.tick==120)
        assert(result.cells[1].unknown and result.cells[1].water==nil)
        assert(result.cells[#result.cells].walkable)
        assert(result.cell_size==32)
    """)


def test_nearby_entities_surface_status_drops_and_ground_items():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        storage={actions={},agent_characters={},utils={}}
        game={tick=120}
        defines={entity_status={working=1,waiting_for_source_items=2},
            inventory={fuel=1}}
        storage.utils.get_issues=function(entity) return {} end
        chest_inventory={{valid_for_read=true,name='coal',count=3}}
        chest={name='wooden-chest', type='container', status=nil, valid=true,
            position={x=3,y=3}, direction=0, unit_number=4,
            get_inventory=function(kind) return chest_inventory end}
        inserter={name='burner-inserter', type='inserter', status=2, valid=true,
            position={x=2,y=3}, direction=4, unit_number=2,
            held_stack={valid_for_read=false},
            drop_position={x=3,y=3}, pickup_position={x=1,y=3}}
        ground={name='item-on-ground', type='item-on-ground', status=nil, valid=true,
            position={x=4,y=4}, direction=0,
            stack={valid_for_read=true,name='iron-ore',count=7}}
        surface={index=1,
            is_chunk_generated=function(p) return true end,
            count_tiles_filtered=function(f) return 0 end,
            count_entities_filtered=function(f) return 0 end,
            find_entities_filtered=function(f)
                if f.position then return {chest} end
                assert(f.limit == 9)
                return {inserter, ground, chest}
            end}
        storage.agent_characters[1]={valid=true,surface=surface,force={},
            position={x=0,y=0}}
    """)
    lua.execute(
        (
            Path(__file__).parents[2] / "fle/env/tools/admin/public_view/server.lua"
        ).read_text(encoding="utf-8")
    )
    lua.execute("""
        result=storage.actions.public_view(1,32,8)
        local inserter, ground, chest
        for _,entry in ipairs(result.entities) do
            if entry.name=='burner-inserter' then inserter=entry end
            if entry.name=='item-on-ground' then ground=entry end
            if entry.name=='wooden-chest' then chest=entry end
        end
        assert(inserter.status=='waiting_for_source_items')
        assert(inserter.drop_position.x==3)
        assert(inserter.drop_target=='wooden-chest')
        assert(inserter.pickup_target=='wooden-chest')
        assert(inserter.source_inventory['coal']==3)
        assert(ground.item=='iron-ore' and ground.count==7)
        assert(chest.status=='unknown')
        assert(result.entities_truncated==false)
    """)


def test_public_view_client_normalizes_wire_arrays_and_rejects_unbounded_reads():
    tool = PublicView.__new__(PublicView)
    tool.player_index = 1
    tool.execute = Mock(return_value=({"cells": {1: {"water": 2}}, "entities": {}}, 0))
    assert tool()["cells"] == [{"water": 2}]
    assert tool()["entities"] == []
    with pytest.raises(ValueError, match="radius"):
        tool(1024)
    with pytest.raises(ValueError, match="entity_limit"):
        tool(32, 1024)


def test_public_view_unitless_entities_get_distinct_ids():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        storage={actions={},agent_characters={},utils={}}
        game={tick=1}
        defines={entity_status={},inventory={}}
        storage.utils.get_issues=function() return {} end
        trees={
            {name='tree-01', type='tree', status=nil, valid=true,
                position={x=1.5,y=1.5}, direction=0},
            {name='tree-01', type='tree', status=nil, valid=true,
                position={x=4.5,y=1.5}, direction=0},
        }
        surface={index=2,
            is_chunk_generated=function() return true end,
            count_tiles_filtered=function() return 0 end,
            count_entities_filtered=function() return 0 end,
            find_entities_filtered=function(f) return trees end}
        storage.agent_characters[1]={valid=true,surface=surface,force={},
            position={x=0,y=0}}
    """)
    lua.execute(
        (
            Path(__file__).parents[2] / "fle/env/tools/admin/public_view/server.lua"
        ).read_text(encoding="utf-8")
    )
    lua.execute("""
        result=storage.actions.public_view(1,32,8)
        assert(#result.entities==2)
        assert(result.entities[1].entity_id=='2:tree-01@1.5,1.5')
        assert(result.entities[2].entity_id=='2:tree-01@4.5,1.5')
        assert(result.entities[1].entity_id ~= result.entities[2].entity_id)
    """)
