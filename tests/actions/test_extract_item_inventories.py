import pytest

from tests.actions.lua_stub_helpers import lua_stub

pytestmark = pytest.mark.no_factorio


def runtime():
    # defines.inventory mirrors the live 2.0.77 keys, so a reference to a
    # removed define resolves to nil exactly like the engine. The old scan
    # referenced 1.1-era names (lab_source, mining_drill_input, reactor_*,
    # car_fuel, storage_tank); the first nil silently truncated every entry
    # after burnt_result, making lab_input/turret_ammo unreachable.
    return lua_stub(
        """
        storage={actions={},utils={},agent_characters={}}
        script={on_event=function()end,on_nth_tick=function()end}
        game={tick=0}
        defines={inventory={
            chest=1,furnace_source=2,furnace_result=3,
            assembling_machine_input=2,assembling_machine_output=3,
            fuel=4,burnt_result=5,lab_input=6,item_main=1,
            robot_cargo=7,robot_repair=8,car_trunk=9,
            roboport_material=10,roboport_robot=11,
            artillery_turret_ammo=12,turret_ammo=13,beacon_modules=14,
            character_main=15,character_guns=16,character_ammo=17,
            character_armor=18,character_vehicle=19,character_trash=20}}
        function make_inventory(contents)
            local inv={contents=contents}
            function inv.get_item_count(name) return inv.contents[name] or 0 end
            function inv.remove(stack)
                local have=inv.contents[stack.name] or 0
                local removed=math.min(have,stack.count)
                inv.contents[stack.name]=have-removed
                if inv.contents[stack.name]==0 then inv.contents[stack.name]=nil end
                return removed
            end
            return inv
        end
        function make_entity(name, entity_type, inventory_id, inventory)
            local entity={name=name,type=entity_type,valid=true,position={x=1,y=1}}
            function entity.get_inventory(id)
                if id==inventory_id then return inventory end
                return nil
            end
            return entity
        end
        function make_player(entities, capacity)
            local surface={find_entities_filtered=function(query)
                local out={}
                for _,entity in ipairs(entities) do
                    if (query.name==nil or entity.name==query.name)
                        and entity.valid then
                        if query.radius==nil then
                            out[#out+1]=entity
                        else
                            local dx=entity.position.x-query.position.x
                            local dy=entity.position.y-query.position.y
                            if math.sqrt(dx*dx+dy*dy)<=query.radius then
                                out[#out+1]=entity
                            end
                        end
                    end
                end
                return out
            end}
            local main={capacity=capacity or 1000,contents={}}
            function main.used()
                local total=0
                for _,count in pairs(main.contents) do total=total+count end
                return total
            end
            function main.can_insert(stack)
                return main.used()+stack.count<=main.capacity
            end
            local player={valid=true,position={x=0,y=0},surface=surface,
                inserted={},main=main}
            function player.insert(stack)
                local take=math.min(main.capacity-main.used(),stack.count)
                if take>0 then
                    main.contents[stack.name]=(main.contents[stack.name] or 0)+take
                    player.inserted[stack.name]=(player.inserted[stack.name] or 0)+take
                end
                return take
            end
            function player.get_main_inventory() return main end
            function player.remove_item(stack)
                local have=main.contents[stack.name] or 0
                local take=math.min(have,stack.count)
                main.contents[stack.name]=have-take
                return take
            end
            return player
        end
        storage.utils.ensure_valid_character=function(player_index)
            return storage.agent_characters[player_index]
        end
        """,
        "tools/agent/extract_item/server.lua",
    )


def test_extract_item_reads_lab_input_after_removed_entries():
    lua = runtime()
    lua.execute("""
        local inventory=make_inventory({['iron-plate']=7})
        local lab=make_entity('lab','lab',defines.inventory.lab_input,inventory)
        storage.agent_characters[1]=make_player({lab})
        result=storage.actions.extract_item(1,'iron-plate',5,0,0,'lab')
        assert(result==5,'expected 5 extracted, got '..tostring(result))
        assert(inventory.contents['iron-plate']==2)
        assert(storage.agent_characters[1].inserted['iron-plate']==5)
    """)


def test_extract_item_reads_tail_ammo_inventory():
    lua = runtime()
    lua.execute("""
        local inventory=make_inventory({['firearm-magazine']=3})
        local turret=make_entity('gun-turret','ammo-turret',
            defines.inventory.turret_ammo,inventory)
        storage.agent_characters[1]=make_player({turret})
        result=storage.actions.extract_item(1,'firearm-magazine',2,0,0,nil)
        assert(result==2,'expected 2 extracted, got '..tostring(result))
        assert(inventory.contents['firearm-magazine']==1)
    """)


def test_extract_item_reports_missing_items_instead_of_crashing():
    lua = runtime()
    with pytest.raises(
        Exception, match="Could not find a valid lab entity containing iron-plate"
    ):
        lua.execute("""
            local inventory=make_inventory({})
            local lab=make_entity('lab','lab',defines.inventory.lab_input,inventory)
            storage.agent_characters[1]=make_player({lab})
            storage.actions.extract_item(1,'iron-plate',5,0,0,'lab')
        """)


def test_extract_stays_tied_to_requested_target():
    lua = runtime()
    lua.execute("""
        local first=make_inventory({['iron-plate']=7})
        local second=make_inventory({['iron-plate']=7})
        local lab_first=make_entity('lab','lab',defines.inventory.lab_input,first)
        lab_first.position={x=1,y=1}
        local lab_second=make_entity('lab','lab',defines.inventory.lab_input,second)
        lab_second.position={x=5,y=1}
        storage.agent_characters[1]=make_player({lab_first,lab_second})
        local result=storage.actions.extract_item(1,'iron-plate',4,5,1,nil)
        assert(result==4)
        assert(first.contents['iron-plate']==7)
        assert(second.contents['iron-plate']==3)
    """)


def test_named_target_missing_at_position_is_reported():
    lua = runtime()
    with pytest.raises(Exception, match="Could not find a valid lab entity at"):
        lua.execute("""
            local inventory=make_inventory({['iron-plate']=7})
            local chest=make_entity('iron-chest','container',
                defines.inventory.chest,inventory)
            chest.position={x=5,y=1}
            storage.agent_characters[1]=make_player({chest})
            storage.actions.extract_item(1,'iron-plate',5,5,1,'lab')
        """)


def test_reach_check_rejects_distant_character():
    lua = runtime()
    with pytest.raises(Exception, match="too far away"):
        lua.execute("""
            local inventory=make_inventory({['iron-plate']=7})
            local lab=make_entity('lab','lab',defines.inventory.lab_input,inventory)
            storage.agent_characters[1]=make_player({lab})
            storage.agent_characters[1].position={x=100,y=100}
            storage.actions.extract_item(1,'iron-plate',5,1,1,'lab')
        """)


def test_reach_check_is_skipped_in_fast_mode():
    lua = runtime()
    lua.execute("""
        storage.fast=true
        local inventory=make_inventory({['iron-plate']=7})
        local lab=make_entity('lab','lab',defines.inventory.lab_input,inventory)
        storage.agent_characters[1]=make_player({lab})
        storage.agent_characters[1].position={x=100,y=100}
        local result=storage.actions.extract_item(1,'iron-plate',5,1,1,'lab')
        assert(result==5)
        storage.fast=nil
    """)


def test_extraction_is_clipped_to_inventory_room():
    lua = runtime()
    lua.execute("""
        local inventory=make_inventory({['iron-plate']=7})
        local lab=make_entity('lab','lab',defines.inventory.lab_input,inventory)
        local player=make_player({lab},3)
        storage.agent_characters[1]=player
        local result=storage.actions.extract_item(1,'iron-plate',5,1,1,'lab')
        assert(result==3,'expected 3 extracted, got '..tostring(result))
        assert(inventory.contents['iron-plate']==4)
        assert(player.inserted['iron-plate']==3)
    """)


def test_full_inventory_is_reported_not_reinserted():
    lua = runtime()
    with pytest.raises(Exception, match="Inventory has no room"):
        lua.execute("""
            local inventory=make_inventory({['iron-plate']=7})
            local lab=make_entity('lab','lab',defines.inventory.lab_input,inventory)
            storage.agent_characters[1]=make_player({lab},0)
            storage.actions.extract_item(1,'iron-plate',5,1,1,'lab')
        """)
