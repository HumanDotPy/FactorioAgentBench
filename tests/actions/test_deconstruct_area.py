from pathlib import Path
from unittest.mock import Mock

import pytest
from lupa.lua54 import LuaRuntime

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.deconstruct_area.client import DeconstructArea

pytestmark = pytest.mark.no_factorio


def runtime():
    lua = LuaRuntime()
    lua.execute("""
        storage={actions={},agent_characters={},utils={}}
        storage.utils.get_contents_compat=function(inv) return inv end
        game={tick=4242}
        defines={inventory={chest=1,chest_alias=1,fuel=2}}
        player_entities={}
        neutral_entities={}
        inserted={}
        removed_items={}
        insert_blocked={}
        insert_room={}

        function make_entity(props)
            local e=props
            e.valid=true
            e.destroyed=false
            e.can_be_destroyed=function() return e.destroyable~=false end
            e.destroy=function(opts)
                if e.destroy_raises then error('destroy failed') end
                e.valid=false
                e.destroyed=true
                e.destroy_options=opts
            end
            e.get_inventory=function(id)
                if e.inventories then return e.inventories[id] end
                return nil
            end
            e.get_transport_line=function(index)
                if e.lanes then return e.lanes[index] end
                return nil
            end
            return e
        end

        function make_player()
            local inventory={can_insert=function(stack)
                return not insert_blocked[stack.name]
            end}
            return {
                force='player',
                get_main_inventory=function() return inventory end,
                insert=function(stack)
                    if insert_blocked[stack.name] then return 0 end
                    local count=stack.count
                    if insert_room[stack.name]~=nil then
                        count=math.min(count,insert_room[stack.name])
                        insert_room[stack.name]=insert_room[stack.name]-count
                    end
                    if count>0 then
                        inserted[#inserted+1]={name=stack.name,count=count}
                    end
                    return count
                end,
                remove_item=function(stack)
                    removed_items[#removed_items+1]={
                        name=stack.name,count=stack.count}
                    return stack.count
                end,
            }
        end

        function make_surface()
            return {
                find_entities_filtered=function(query)
                    if query.force=='neutral' then return neutral_entities end
                    return player_entities
                end,
            }
        end

        storage.agent_characters[1]=make_player()
        storage.agent_characters[1].surface=make_surface()
    """)
    lua.execute(
        (
            Path(__file__).parents[2]
            / "fle/env/tools/agent/deconstruct_area/server.lua"
        ).read_text()
    )
    return lua


def test_belt_is_removed_and_lane_contents_returned():
    lua = runtime()
    lua.execute("""
        belt=make_entity({
            name='transport-belt', type='transport-belt', unit_number=1,
            position={x=1.5,y=1.5},
            lanes={[1]={['iron-plate']=3},[2]={['copper-plate']=2}},
        })
        player_entities[1]=belt
        result=storage.actions.deconstruct_area(1,0,0,3,3,nil,true,512)
        assert(result.status=='completed')
        assert(result.removed==1)
        assert(belt.destroyed and not belt.valid)
        assert(result.items_returned['transport-belt']==1)
        assert(result.items_returned['iron-plate']==3)
        assert(result.items_returned['copper-plate']==2)
        assert(#inserted==3)
        assert(result.tick==4242)
        assert(result.area.left==0 and result.area.right==3)
    """)


def test_chest_contents_are_returned_once_per_inventory_id():
    lua = runtime()
    lua.execute("""
        chest=make_entity({
            name='wooden-chest', type='container', unit_number=2,
            position={x=0.5,y=0.5},
            inventories={[1]={['iron-plate']=5}},
        })
        player_entities[1]=chest
        result=storage.actions.deconstruct_area(1,0,0,2,2,nil,true,512)
        assert(result.removed==1)
        assert(result.items_returned['wooden-chest']==1)
        assert(result.items_returned['iron-plate']==5)
        assert(chest.destroyed)
    """)


def test_neutral_tree_yields_wood_and_is_destroyed():
    lua = runtime()
    lua.execute("""
        tree=make_entity({
            name='tree-01', type='tree', unit_number=3,
            position={x=0.5,y=0.5}, minable=true,
            prototype={mineable_properties={products={{name='wood',amount=4}}}},
        })
        neutral_entities[1]=tree
        result=storage.actions.deconstruct_area(1,0,0,2,2,nil,true,512)
        assert(result.removed==1)
        assert(result.items_returned['wood']==4)
        assert(tree.destroyed and not tree.valid)
    """)


def test_neutral_entities_are_ignored_when_disabled():
    lua = runtime()
    lua.execute("""
        tree=make_entity({
            name='tree-01', type='tree', unit_number=4,
            position={x=0.5,y=0.5}, minable=true,
            prototype={mineable_properties={products={{name='wood',amount=4}}}},
        })
        neutral_entities[1]=tree
        result=storage.actions.deconstruct_area(1,0,0,2,2,nil,false,512)
        assert(result.removed==0)
        assert(tree.valid and not tree.destroyed)
    """)


def test_protected_entity_is_skipped_and_stays_valid():
    lua = runtime()
    lua.execute("""
        chest=make_entity({
            name='wooden-chest', type='container', unit_number=5,
            position={x=1.5,y=1.5}, destroyable=false,
        })
        player_entities[1]=chest
        result=storage.actions.deconstruct_area(1,0,0,3,3,nil,true,512)
        assert(result.status=='completed')
        assert(result.removed==0)
        assert(chest.valid and not chest.destroyed)
        assert(#result.skipped==1)
        assert(result.skipped[1].reason=='protected')
        assert(result.skipped[1].name=='wooden-chest')
        assert(result.skipped[1].position.x==1.5)
        assert(#inserted==0)
    """)


def test_inventory_full_stops_before_removal():
    lua = runtime()
    lua.execute("""
        insert_blocked['wooden-chest']=true
        chest=make_entity({
            name='wooden-chest', type='container', unit_number=6,
            position={x=0.5,y=0.5},
            inventories={[1]={['iron-plate']=5}},
        })
        belt=make_entity({
            name='transport-belt', type='transport-belt', unit_number=7,
            position={x=1.5,y=0.5},
        })
        player_entities[1]=chest
        player_entities[2]=belt
        result=storage.actions.deconstruct_area(1,0,0,3,2,nil,true,512)
        assert(result.status=='inventory_full')
        assert(result.removed==0)
        assert(result.inventory_full.name=='wooden-chest')
        assert(result.inventory_full.position.x==0.5)
        assert(result.inventory_full.position.y==0.5)
        assert(chest.valid and not chest.destroyed)
        assert(belt.valid and not belt.destroyed)
        assert(#inserted==1)
        assert(inserted[1].name=='iron-plate' and inserted[1].count==5)
        assert(#removed_items==1)
        assert(removed_items[1].name=='iron-plate' and removed_items[1].count==5)
    """)


def test_overflow_rolls_back_and_lists_unreturned_items():
    lua = runtime()
    lua.execute("""
        insert_room['iron-plate']=3
        chest=make_entity({
            name='wooden-chest', type='container', unit_number=61,
            position={x=0.5,y=0.5},
            inventories={[1]={['iron-plate']=5}},
        })
        player_entities[1]=chest
        result=storage.actions.deconstruct_area(1,0,0,2,2,nil,true,512)
        assert(result.status=='inventory_full')
        assert(result.removed==0)
        assert(next(result.items_returned)==nil)
        assert(chest.valid and not chest.destroyed)
        local overflow={}
        for _,entry in ipairs(result.overflow) do
            overflow[entry.name]=(overflow[entry.name] or 0)+entry.count
        end
        assert(overflow['iron-plate']==2)
        assert(overflow['wooden-chest']==1)
        assert(#inserted==1 and inserted[1].count==3)
        assert(#removed_items==1 and removed_items[1].count==3)
    """)


def test_destroy_failure_keeps_entity_and_rolls_back_returns():
    lua = runtime()
    lua.execute("""
        chest=make_entity({
            name='wooden-chest', type='container', unit_number=62,
            position={x=0.5,y=0.5}, destroy_raises=true,
        })
        player_entities[1]=chest
        result=storage.actions.deconstruct_area(1,0,0,2,2,nil,true,512)
        assert(result.status=='completed')
        assert(result.removed==0)
        assert(next(result.items_returned)==nil)
        assert(chest.valid and not chest.destroyed)
        assert(#result.skipped==1)
        assert(result.skipped[1].reason=='destroy_failed')
        assert(#inserted==1 and inserted[1].name=='wooden-chest')
        assert(#removed_items==1 and removed_items[1].name=='wooden-chest')
        assert(#result.overflow==0)
    """)


def test_max_entities_truncates_and_sets_requested():
    lua = runtime()
    lua.execute("""
        for i=1,3 do
            player_entities[#player_entities+1]=make_entity({
                name='wooden-chest', type='container', unit_number=10+i,
                position={x=i-0.5,y=0.5},
            })
        end
        result=storage.actions.deconstruct_area(1,0,0,4,2,nil,true,2)
        assert(result.requested==3)
        assert(result.truncated==true)
        assert(result.removed==2)
        assert(player_entities[3].valid and not player_entities[3].destroyed)
        assert(player_entities[1].destroyed and player_entities[2].destroyed)
    """)


def test_max_entities_is_clamped_to_at_least_one():
    lua = runtime()
    lua.execute("""
        for i=1,2 do
            player_entities[#player_entities+1]=make_entity({
                name='wooden-chest', type='container', unit_number=20+i,
                position={x=i-0.5,y=0.5},
            })
        end
        result=storage.actions.deconstruct_area(1,0,0,3,1,nil,true,0)
        assert(result.removed==1)
        assert(result.truncated==true)
    """)


def test_prototype_filter_keeps_only_matching_names():
    lua = runtime()
    lua.execute("""
        player_entities[1]=make_entity({
            name='wooden-chest', type='container', unit_number=31,
            position={x=0.5,y=0.5}})
        player_entities[2]=make_entity({
            name='transport-belt', type='transport-belt', unit_number=32,
            position={x=1.5,y=0.5}})
        result=storage.actions.deconstruct_area(1,0,0,3,2,'wooden-chest',true,512)
        assert(result.requested==1)
        assert(result.removed==1)
        assert(result.items_returned['wooden-chest']==1)
        assert(result.items_returned['transport-belt']==nil)
        assert(player_entities[2].valid and not player_entities[2].destroyed)
    """)


def test_special_types_are_skipped_with_reasons():
    lua = runtime()
    lua.execute("""
        player_entities[1]=make_entity({
            name='entity-ghost', type='entity-ghost', unit_number=41,
            position={x=0.5,y=0.5}})
        player_entities[2]=make_entity({
            name='character', type='character', unit_number=42,
            position={x=1.5,y=0.5}})
        neutral_entities[1]=make_entity({
            name='iron-ore', type='resource', unit_number=43,
            position={x=0.5,y=1.5}})
        neutral_entities[2]=make_entity({
            name='character-corpse', type='corpse', unit_number=44,
            position={x=1.5,y=1.5}})
        neutral_entities[3]=make_entity({
            name='rock-huge', type='simple-entity', unit_number=45,
            position={x=2.5,y=1.5}, minable=false,
            prototype={mineable_properties={products={{name='stone',amount=20}}}}})
        result=storage.actions.deconstruct_area(1,0,0,4,3,nil,true,512)
        assert(result.removed==0)
        assert(result.requested==0)
        assert(result.status=='completed')
        local reasons={}
        for _,entry in ipairs(result.skipped) do reasons[entry.name]=entry.reason end
        assert(reasons['entity-ghost']=='ghost')
        assert(reasons['character']=='self')
        assert(reasons['iron-ore']=='resource')
        assert(reasons['character-corpse']=='not_mineable')
        assert(reasons['rock-huge']=='not_mineable')
    """)


def test_server_reports_missing_character():
    lua = runtime()
    lua.execute("""
        result=storage.actions.deconstruct_area(99,0,0,1,1,nil,true,512)
        assert(result.error ~= nil)
        assert(result.status==nil)
    """)


def test_client_validates_arguments():
    tool = DeconstructArea.__new__(DeconstructArea)
    tool.player_index = 1
    tool.ensure_reachable = Mock()
    tool.execute = Mock(return_value=({"status": "completed"}, 0))

    with pytest.raises(ValueError, match="top_left must be a Position"):
        tool((0, 0), Position(x=1, y=1))
    with pytest.raises(ValueError, match="bottom_right must be a Position"):
        tool(Position(x=0, y=0), (1, 1))
    with pytest.raises(ValueError, match="prototype"):
        tool(Position(x=0, y=0), Position(x=1, y=1), prototype=42)
    with pytest.raises(ValueError, match="prototype"):
        tool(Position(x=0, y=0), Position(x=1, y=1), prototype="")
    with pytest.raises(ValueError, match="include_neutral"):
        tool(Position(x=0, y=0), Position(x=1, y=1), include_neutral=1)
    with pytest.raises(ValueError, match="max_entities"):
        tool(Position(x=0, y=0), Position(x=1, y=1), max_entities=0)
    with pytest.raises(ValueError, match="max_entities"):
        tool(Position(x=0, y=0), Position(x=1, y=1), max_entities=2049)
    with pytest.raises(ValueError, match="max_entities"):
        tool(Position(x=0, y=0), Position(x=1, y=1), max_entities=True)
    with pytest.raises(ValueError, match="area must be at most 64x64 tiles"):
        tool(Position(x=0, y=0), Position(x=64, y=0))
    with pytest.raises(ValueError, match="area must be at most 64x64 tiles"):
        tool(Position(x=0, y=0), Position(x=0, y=64))

    tool.ensure_reachable.assert_not_called()


def test_client_passes_arguments_and_walks_to_centre():
    tool = DeconstructArea.__new__(DeconstructArea)
    tool.player_index = 2
    tool.ensure_reachable = Mock()
    tool.execute = Mock(
        return_value=(
            {
                "status": "completed",
                "removed": 1,
                "items_returned": {"wood": 4},
                "skipped": {1: {"name": "x", "reason": "protected"}},
                "truncated": False,
            },
            0,
        )
    )

    result = tool(
        Position(x=0.5, y=0.5),
        Position(x=5.5, y=7.5),
        Prototype.WoodenChest,
        include_neutral=False,
        max_entities=100,
    )

    tool.ensure_reachable.assert_called_once_with(Position(x=2.5, y=3.5))
    tool.execute.assert_called_once_with(
        2, 0.5, 0.5, 5.5, 7.5, "wooden-chest", False, 100
    )
    assert result["status"] == "completed"
    assert result["items_returned"] == {"wood": 4}
    assert result["skipped"] == [{"name": "x", "reason": "protected"}]


def test_client_raises_on_server_error():
    tool = DeconstructArea.__new__(DeconstructArea)
    tool.player_index = 1
    tool.ensure_reachable = Mock()

    tool.execute = Mock(return_value=({"error": "Player not found"}, 0))
    with pytest.raises(Exception, match="Could not deconstruct area"):
        tool(Position(x=0, y=0), Position(x=1, y=1))

    tool.execute = Mock(return_value=("boom", 0))
    with pytest.raises(Exception, match="Could not deconstruct area"):
        tool(Position(x=0, y=0), Position(x=1, y=1))


def test_client_normalizes_nested_arrays_to_lists():
    from fle.env.tools.agent.deconstruct_area.client import _normalize_arrays

    response = {
        "skipped": {1: {"name": "tree-01", "position": {1: 2, 2: 3}}},
        "items_returned": {"wood": 4},
    }
    normalized = _normalize_arrays(response)
    assert normalized["skipped"] == [{"name": "tree-01", "position": [2, 3]}]
    assert normalized["items_returned"] == {"wood": 4}
