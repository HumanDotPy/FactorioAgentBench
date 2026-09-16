from unittest.mock import Mock

import pytest

from fle.env.entities import Position
from fle.env.tools.agent.refuel.client import Refuel
from tests.actions.lua_stub_helpers import lua_stub

pytestmark = pytest.mark.no_factorio


def runtime():
    return lua_stub(
        """
        storage={actions={},utils={}}
        defines={inventory={fuel=4,chest=1,crafter_input=2}}
        prototypes={item={
            coal={name='coal',fuel_value=4000000,stack_size=50},
            wood={name='wood',fuel_value=2000000,stack_size=50},
            ['iron-ore']={name='iron-ore',stack_size=50},
        }}
        removals={}
        main_contents={}
        entities={}

        function make_inventory(slots)
            local inv={}
            for i=1,1 do inv[i]={valid_for_read=false} end
            for i,stack in pairs(slots or {}) do inv[i]=stack end
            function inv.insert(item)
                local stack_size=(prototypes.item[item.name] or {}).stack_size or 1
                local remaining=item.count
                for i=1,#inv do
                    local s=inv[i]
                    if s.valid_for_read and s.name==item.name then
                        local take=math.min(stack_size-s.count, remaining)
                        s.count=s.count+take
                        remaining=remaining-take
                        if remaining<=0 then return item.count end
                    end
                end
                for i=1,#inv do
                    if not inv[i].valid_for_read then
                        local take=math.min(stack_size, remaining)
                        inv[i]={valid_for_read=true,name=item.name,count=take}
                        remaining=remaining-take
                        if remaining<=0 then return item.count end
                    end
                end
                return item.count-remaining
            end
            return inv
        end

        function make_fuel_entity(name, entity_type, inventory)
            return {
                name=name, type=entity_type, valid=true, position={x=0,y=0},
                get_inventory=function(def)
                    if def==defines.inventory.fuel then return inventory end
                    return nil
                end,
            }
        end

        function make_chest()
            return {name='iron-chest', type='container', valid=true,
                position={x=0,y=0}, get_inventory=function() return nil end}
        end

        function make_player(contents)
            main_contents=contents or {}
            local main={}
            for name,count in pairs(main_contents) do
                main[#main+1]={valid_for_read=true,name=name,count=count}
            end
            local p={position={x=1,y=1}}
            p.surface={find_entities_filtered=function(query)
                local out={}
                for _,e in ipairs(entities) do
                    if query.name==nil or e.name==query.name then
                        out[#out+1]=e
                    end
                end
                return out
            end}
            function p.get_main_inventory() return main end
            function p.remove_item(item)
                local take=math.min(main_contents[item.name] or 0, item.count)
                main_contents[item.name]=(main_contents[item.name] or 0)-take
                removals[#removals+1]={name=item.name,count=take}
                return take
            end
            return p
        end

        storage.utils.ensure_valid_character=function(player_index)
            return storage.test_player
        end
        storage.utils.serialize_entity=function(entity)
            return {name=entity.name, position=entity.position}
        end
        """,
        "tools/agent/refuel/server.lua",
    )


def test_refuel_picks_best_fuel_by_value():
    lua = runtime()
    lua.execute("""
        entities={make_fuel_entity('stone-furnace','furnace',make_inventory())}
        storage.test_player=make_player({coal=10, wood=100})
        local result=storage.actions.refuel(1,0,0,nil)
        assert(result.status=='refueled')
        assert(result.fuel=='coal')
        assert(result.available==10)
        assert(result.inserted==10)
        assert(result.remaining_fuel==40)
        assert(result.entity.name=='stone-furnace')
        assert(main_contents['coal']==0)
        assert(main_contents['wood']==100)
    """)


def test_refuel_respects_existing_fuel_type_and_capacity():
    lua = runtime()
    lua.execute("""
        local inv=make_inventory({[1]={valid_for_read=true,name='wood',count=20}})
        entities={make_fuel_entity('burner-inserter','inserter',inv)}
        storage.test_player=make_player({wood=30, coal=100})
        local result=storage.actions.refuel(1,0,0,nil)
        assert(result.status=='refueled')
        assert(result.fuel=='wood')
        assert(result.inserted==30)
        assert(result.remaining_fuel==0)
        assert(main_contents['wood']==0)
        assert(main_contents['coal']==100)
    """)


def test_refuel_clamps_to_remaining_capacity():
    lua = runtime()
    lua.execute("""
        local inv=make_inventory({[1]={valid_for_read=true,name='coal',count=40}})
        entities={make_fuel_entity('stone-furnace','furnace',inv)}
        storage.test_player=make_player({coal=5})
        local result=storage.actions.refuel(1,0,0,nil)
        assert(result.status=='refueled')
        assert(result.fuel=='coal')
        assert(result.available==5)
        assert(result.inserted==5)
        assert(result.remaining_fuel==5)
        assert(main_contents['coal']==0)
    """)


def test_refuel_reports_full_and_empty_inventory():
    lua = runtime()
    lua.execute("""
        local inv=make_inventory({[1]={valid_for_read=true,name='coal',count=50}})
        entities={make_fuel_entity('stone-furnace','furnace',inv)}
        storage.test_player=make_player({coal=100})
        local result=storage.actions.refuel(1,0,0,nil)
        assert(result.status=='fuel_full')
        assert(result.inserted==0)
        assert(result.remaining_fuel==0)
        assert(result.available==100)
        assert(main_contents['coal']==100)

        entities={make_fuel_entity('stone-furnace','furnace',make_inventory())}
        storage.test_player=make_player({['iron-ore']=50})
        result=storage.actions.refuel(1,0,0,nil)
        assert(result.status=='no_fuel')
        assert(result.inserted==0)
        assert(result.fuel==nil)
    """)


def test_refuel_reports_fuel_mismatch():
    lua = runtime()
    lua.execute("""
        local inv=make_inventory({[1]={valid_for_read=true,name='wood',count=20}})
        entities={make_fuel_entity('stone-furnace','furnace',inv)}
        storage.test_player=make_player({coal=100})
        local result=storage.actions.refuel(1,0,0,nil)
        assert(result.status=='fuel_mismatch')
        assert(result.fuel=='wood')
        assert(result.available==0)
        assert(result.inserted==0)
        assert(result.remaining_fuel==30)
        assert(main_contents['coal']==100)
    """)


def test_refuel_explains_non_fuelable_entities():
    lua = runtime()
    with pytest.raises(Exception, match="no fuel slot"):
        lua.execute("""
            entities={make_chest()}
            storage.test_player=make_player({coal=10})
            storage.actions.refuel(1,0,0,nil)
        """)


def test_refuel_client_passes_target_and_normalizes_receipt():
    tool = Refuel.__new__(Refuel)
    tool.player_index = 1
    tool.ensure_reachable = Mock()
    tool.execute = Mock(return_value=({"status": "refueled", "fuel": "coal"}, 0))

    receipt = tool(Position(x=2, y=3))

    tool.execute.assert_called_once_with(1, 2, 3, None)
    assert receipt["status"] == "refueled"
    assert receipt["fuel"] == "coal"
    assert receipt["available"] is None

    tool.execute = Mock(return_value=("no fuel slot", 0))
    with pytest.raises(Exception, match="no fuel slot"):
        tool(Position(x=2, y=3))
