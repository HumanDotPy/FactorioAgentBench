from pathlib import Path

import pytest
from lupa.lua54 import LuaRuntime

pytestmark = pytest.mark.no_factorio

ENV = Path(__file__).parents[2] / "fle/env"


def runtime():
    # defines.inventory mirrors the live 2.0.77 keys, so a reference to a
    # removed define resolves to nil exactly like the engine. The old scan
    # referenced 1.1-era names (lab_source, mining_drill_input, reactor_*,
    # car_fuel, storage_tank); the first nil silently truncated every entry
    # after burnt_result, making lab_input/turret_ammo unreachable.
    lua = LuaRuntime()
    lua.execute("""
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
        function make_player(entities)
            local surface={find_entities_filtered=function(query) return entities end}
            local player={valid=true,position={x=0,y=0},surface=surface,inserted={}}
            function player.insert(stack)
                player.inserted[stack.name]=(player.inserted[stack.name] or 0)+stack.count
                return stack.count
            end
            return player
        end
        storage.utils.ensure_valid_character=function(player_index)
            return storage.agent_characters[player_index]
        end
    """)
    lua.execute((ENV / "tools/agent/extract_item/server.lua").read_text())
    return lua


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
