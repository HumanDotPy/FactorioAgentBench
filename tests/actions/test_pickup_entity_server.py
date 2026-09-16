from unittest.mock import Mock

import pytest

from fle.env.entities import Direction, Entity, Position, UndergroundBelt
from fle.env.game_types import Prototype
from fle.env.tools.agent.pickup_entity.client import PickupEntity
from tests.actions.lua_stub_helpers import lua_stub, stub_client

pytestmark = pytest.mark.no_factorio


def runtime():
    return lua_stub(
        """
        storage={actions={},utils={},agent_characters={}}
        defines={inventory={chest=1,character_main=2}}
        game={tick=0}
        rendering={draw_circle=function() end}
        main_contents={}
        main_removed={}
        main_capacity=1000
        can_insert_override=nil

        function main_used()
            local total=0
            for _,count in pairs(main_contents) do total=total+count end
            return total
        end

        function main_insert(item)
            local room=main_capacity-main_used()
            local take=math.min(room,item.count)
            if take>0 then
                main_contents[item.name]=(main_contents[item.name] or 0)+take
            end
            return take
        end

        function main_remove(item)
            local have=main_contents[item.name] or 0
            local take=math.min(have,item.count)
            main_contents[item.name]=have-take
            main_removed[#main_removed+1]={name=item.name,count=take}
            return take
        end

        player={
            position={x=0,y=0},
            surface=nil,
            get_main_inventory=function()
                return {can_insert=function(stack)
                    if can_insert_override~=nil then return can_insert_override end
                    return main_used()+stack.count<=main_capacity
                end}
            end,
            insert=function(item) return main_insert(item) end,
            remove_item=function(item) return main_remove(item) end,
        }
        storage.utils.ensure_valid_character=function() return player end
        storage.utils.get_contents_compat=function(inv) return inv end

        function make_ground_item(name,count,quality)
            local item={name='item-on-ground',type='item-on-ground',
                valid=true,position={x=0.5,y=0.5}}
            item.stack={name=name,count=count}
            if quality~=nil then
                if type(quality)=='table' then item.stack.quality=quality
                else item.stack.quality={name=quality} end
            end
            function item.destroy(opts)
                if item.destroy_raises then error('destroy failed') end
                item.valid=false
                item.destroyed=true
            end
            return item
        end

        function locked_ground_item(name,count)
            local item=make_ground_item(name,count)
            local raw=item.stack
            item.stack=setmetatable({},{__index=raw,__newindex=function(t,k,v)
                if k=='count' then error('read-only stack count') end
                rawset(raw,k,v)
            end})
            return item
        end

        function make_placed(name,inventories,entity_type)
            local e={name=name,type=entity_type or 'container',valid=true,
                position={x=0.5,y=0.5}}
            function e.can_be_destroyed() return e.destroyable~=false end
            function e.get_inventory(id)
                if inventories then return inventories[id] end
                return nil
            end
            function e.destroy(opts)
                if e.destroy_raises then error('destroy failed') end
                e.valid=false
                e.destroyed=true
            end
            return e
        end

        placed={}
        ground={}

        function make_surface(create_ok)
            return {
                find_entities_filtered=function(query)
                    if query.name=='item-on-ground' then return ground end
                    return placed
                end,
                create_entity=function(params)
                    if not create_ok then return nil end
                    local created=make_ground_item(params.stack.name,
                        params.stack.count,params.stack.quality)
                    ground[#ground+1]=created
                    return created
                end,
            }
        end
        player.surface=make_surface(true)
        """,
        "tools/agent/pickup_entity/server.lua",
    )


def execute(snippet):
    runtime().execute(snippet)


def test_ground_pickup_filters_by_name_then_quality():
    execute("""
        ground[1]=make_ground_item('iron-ore',3)
        ground[2]=make_ground_item('iron-ore',4,'uncommon')
        ground[3]=make_ground_item('copper-plate',5)
        local result=storage.actions.pickup_entity(1,0.5,0.5,'iron-ore')
        assert(result.status=='completed')
        assert(result.requested.name=='iron-ore')
        assert(result.requested.quality==nil)
        assert(result.picked_up['iron-ore']==7)
        assert(result.picked_up['copper-plate']==nil)
        assert(ground[3].valid and not ground[3].destroyed)
        assert((main_contents['copper-plate'] or 0)==0)
    """)
    execute("""
        ground[1]=make_ground_item('iron-ore',3)
        ground[2]=make_ground_item('iron-ore',4,'uncommon')
        local result=storage.actions.pickup_entity(1,0.5,0.5,'iron-ore','uncommon')
        assert(result.requested.name=='iron-ore')
        assert(result.requested.quality=='uncommon')
        assert(result.picked_up['iron-ore']==4)
        assert(ground[1].valid and not ground[1].destroyed)
        assert(main_contents['iron-ore']==4)
    """)


def test_ground_pickup_no_match_keeps_unrelated_stacks():
    execute("""
        ground[1]=make_ground_item('copper-plate',4)
        local ok,err=pcall(storage.actions.pickup_entity,1,0.5,0.5,'iron-ore')
        assert(not ok)
        assert(string.find(tostring(err),"No ground stack matching",1,true)~=nil)
        assert(ground[1].valid and not ground[1].destroyed)
        assert((main_contents['copper-plate'] or 0)==0)
    """)


def test_ground_pickup_without_item_filter_takes_every_stack():
    execute("""
        ground[1]=make_ground_item('iron-ore',3)
        ground[2]=make_ground_item('copper-plate',4,'uncommon')
        local result=storage.actions.pickup_entity(1,0.5,0.5,nil)
        assert(result.requested=='all')
        assert(result.status=='completed')
        assert(result.picked_up['iron-ore']==3)
        assert(result.picked_up['copper-plate']==4)
        assert(ground[1].valid==false and ground[2].valid==false)
        assert(main_contents['iron-ore']==3 and main_contents['copper-plate']==4)
    """)
    execute("""
        local ok,err=pcall(storage.actions.pickup_entity,1,0.5,0.5,nil)
        assert(not ok)
        assert(string.find(tostring(err),'No items on the ground')~=nil)
    """)
    execute("""
        local chest=make_placed('wooden-chest',nil)
        placed[1]=chest
        local ok,err=pcall(storage.actions.pickup_entity,1,0.5,0.5,nil)
        assert(not ok)
        assert(string.find(tostring(err),'No items on the ground')~=nil)
        assert(chest.valid and not chest.destroyed)
    """)


def test_ground_partial_pickup_keeps_or_recreates_remainder():
    execute("""
        main_capacity=3
        ground[1]=make_ground_item('iron-ore',5)
        local result=storage.actions.pickup_entity(1,0.5,0.5,'iron-ore')
        assert(result.status=='partial')
        assert(result.picked_up['iron-ore']==3)
        assert(#result.leftovers==1 and result.leftovers[1].count==2)
        assert(ground[1].valid and ground[1].stack.count==2)
        assert(main_contents['iron-ore']==3)
    """)
    execute("""
        main_capacity=3
        ground[1]=locked_ground_item('iron-ore',5)
        local result=storage.actions.pickup_entity(1,0.5,0.5,'iron-ore')
        assert(result.status=='partial')
        assert(result.picked_up['iron-ore']==3)
        assert(result.leftovers[1].count==2)
        assert(ground[1].valid==false)
        assert(#ground==2 and ground[2].valid and ground[2].stack.count==2)
        assert(main_contents['iron-ore']==3)
    """)


def test_ground_recreate_failure_reports_loss():
    execute("""
        main_capacity=3
        player.surface=make_surface(false)
        ground[1]=locked_ground_item('iron-ore',5)
        local result=storage.actions.pickup_entity(1,0.5,0.5,'iron-ore')
        assert(result.status=='partial')
        assert(result.picked_up['iron-ore']==3)
        assert(#result.leftovers==0)
        assert(#result.lost==1 and result.lost[1].count==2)
        assert(ground[1].valid==false)
        assert(main_contents['iron-ore']==3)
    """)


def test_ground_destroy_failure_rolls_back_and_reports_nothing_picked_up():
    execute("""
        ground[1]=make_ground_item('iron-ore',2)
        ground[1].destroy_raises=true
        local ok,err=pcall(storage.actions.pickup_entity,1,0.5,0.5,'iron-ore')
        assert(not ok)
        assert(string.find(tostring(err),'Could not remove')~=nil)
        assert((main_contents['iron-ore'] or 0)==0)
        assert(#ground==1 and ground[1].valid)
        assert(main_removed[1].count==2)
    """)


def test_placed_entity_refused_before_destroy():
    execute("""
        main_capacity=2
        can_insert_override=true
        local chest=make_placed('wooden-chest',{[1]={['iron-plate']=5}})
        placed[1]=chest
        local ok,err=pcall(storage.actions.pickup_entity,1,0.5,0.5,'wooden-chest')
        assert(not ok)
        assert(string.find(tostring(err),'Inventory is full')~=nil)
        assert(chest.valid and not chest.destroyed)
        assert((main_contents['iron-plate'] or 0)==0)
        assert((main_contents['wooden-chest'] or 0)==0)
    """)
    execute("""
        main_capacity=0
        local chest=make_placed('wooden-chest',nil)
        placed[1]=chest
        local ok,err=pcall(storage.actions.pickup_entity,1,0.5,0.5,'wooden-chest')
        assert(not ok)
        assert(string.find(tostring(err),'Inventory is full')~=nil)
        assert(chest.valid and not chest.destroyed)
        assert(#main_removed==0)
    """)


def test_protected_entity_is_refused():
    execute("""
        local chest=make_placed('wooden-chest',nil)
        chest.destroyable=false
        placed[1]=chest
        local ok,err=pcall(storage.actions.pickup_entity,1,0.5,0.5,'wooden-chest')
        assert(not ok)
        assert(string.find(tostring(err),'protected')~=nil)
        assert(chest.valid)
    """)


def client():
    tool = stub_client(PickupEntity)
    tool.ensure_reachable = Mock()
    return tool


def test_client_returns_partial_receipt():
    tool = client()
    receipt = {
        "status": "partial",
        "picked_up": {"iron-ore": 3},
        "leftovers": [
            {"name": "iron-ore", "count": 2, "position": {"x": 0.5, "y": 0.5}}
        ],
    }
    tool.execute = Mock(return_value=(receipt, 0))
    position = Position(x=0.5, y=0.5)

    result = tool(Prototype.IronOre, position)

    tool.ensure_reachable.assert_called_once_with(position)
    assert result == receipt


def test_client_leftovers_without_pickup_raise():
    tool = client()
    tool.execute = Mock(
        return_value=(
            {
                "status": "failed",
                "picked_up": {},
                "leftovers": [{"name": "iron-ore", "count": 4}],
            },
            0,
        )
    )
    with pytest.raises(Exception, match="left on the ground"):
        tool(Prototype.IronOre, Position(x=0.5, y=0.5))


def test_client_empty_hand_ground_sweep():
    tool = client()
    receipt = {"status": "completed", "requested": "all", "picked_up": {}}
    tool.execute = Mock(return_value=(receipt, 0))
    position = Position(x=0.5, y=0.5)

    result = tool(position=position)

    tool.ensure_reachable.assert_called_once_with(position)
    tool.execute.assert_called_once_with(1, 0.5, 0.5, None, None)
    assert result == receipt


def test_client_forwards_entity_quality():
    tool = client()
    tool.execute = Mock(return_value=({}, 0))
    entity = Entity.model_construct(
        name="iron-ore",
        position=Position(x=0.5, y=0.5),
        quality="uncommon",
    )

    tool(entity)

    tool.execute.assert_called_once_with(1, 0.5, 0.5, "iron-ore", "uncommon")


def test_client_underground_belt_ensures_reachability():
    tool = client()
    tool.execute = Mock(
        side_effect=[
            ({"status": "completed", "picked_up": {"underground-belt": 1}}, 0),
            ({"status": "completed", "picked_up": {"underground-belt": 1}}, 0),
        ]
    )
    belt = UndergroundBelt.model_construct(
        name="underground-belt",
        direction=Direction.UP,
        position=Position(x=1, y=1),
        output_position=Position(x=3, y=1),
        input_position=Position(x=-1, y=1),
        is_input=True,
    )

    result = tool(belt)

    tool.ensure_reachable.assert_called_once_with(belt)
    assert tool.execute.call_count == 2
    assert result["status"] == "completed"
