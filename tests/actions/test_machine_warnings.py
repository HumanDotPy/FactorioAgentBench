from pathlib import Path

import pytest
from lupa.lua54 import LuaRuntime

pytestmark = pytest.mark.no_factorio


def runtime():
    lua = LuaRuntime()
    lua.execute("""
        storage={alerts={},utils={}}
        script={on_event=function() end}
        defines={
            events={on_tick=1},
            direction={north=0,east=4,south=8,west=12},
            inventory={
                fuel=1,
                burnt_result=2,
                chest=3,
                furnace_source=4,
                furnace_result=5,
                assembling_machine_input=6,
                assembling_machine_output=7,
                rocket_silo_rocket=8,
                rocket_silo_input=9,
                rocket_silo_output=10,
                rocket_silo_modules=11,
            },
            entity_status={
                working=1,
                full_output=2,
                waiting_for_space_in_destination=3,
            },
        }
        prototypes={item={coal={fuel_value=4000000}}}
        game={tick=0,surfaces={}}

        storage.utils.get_contents_compat=function(inventory)
            local contents={}
            if inventory==nil then return contents end
            for i=1,#inventory do
                local stack=inventory[i]
                if stack and stack.valid_for_read then
                    contents[stack.name]=(contents[stack.name] or 0)+stack.count
                end
            end
            return contents
        end

        function stack(name,count,stack_size)
            return {valid_for_read=true,name=name,count=count,
                prototype={stack_size=stack_size or 100}}
        end

        function make_inv(capacity,stacks)
            local inv={}
            for i=1,capacity do
                inv[i]=stacks[i] or {valid_for_read=false}
            end
            inv.is_full=function()
                for i=1,#inv do
                    local stack=inv[i]
                    if not stack.valid_for_read
                        or stack.count<stack.prototype.stack_size then
                        return false
                    end
                end
                return true
            end
            inv.is_empty=function()
                for i=1,#inv do
                    if inv[i].valid_for_read then return false end
                end
                return true
            end
            inv.can_insert=function(item) return not inv.is_full() end
            inv.get_item_count=function(name)
                local count=0
                for i=1,#inv do
                    local stack=inv[i]
                    if stack.valid_for_read and stack.name==name then
                        count=count+stack.count
                    end
                end
                return count
            end
            return inv
        end

        function make_furnace(opts)
            opts=opts or {}
            local source=opts.source or make_inv(2,{})
            local result=opts.result or make_inv(2,{})
            local fuel=opts.fuel or make_inv(1,{stack('coal',5)})
            local inventories={
                [defines.inventory.furnace_source]=source,
                [defines.inventory.furnace_result]=result,
                [defines.inventory.fuel]=fuel,
            }
            return {
                name=opts.name or 'stone-furnace',
                type='furnace',
                status=opts.status or defines.entity_status.working,
                position={x=0,y=0},
                prototype={},
                burner={currently_burning='coal'},
                get_recipe=function() return opts.recipe or {name='iron-plate'} end,
                get_inventory=function(def) return inventories[def] end,
                get_output_inventory=function() return result end,
            }
        end

        function make_drill(opts)
            opts=opts or {}
            local output=opts.output or make_inv(3,{})
            local fuel=opts.fuel or make_inv(1,{stack('coal',5)})
            local inventories={[defines.inventory.fuel]=fuel}
            return {
                name='burner-mining-drill',
                type='mining-drill',
                status=opts.status or defines.entity_status.working,
                position={x=0,y=0},
                prototype={},
                burner={currently_burning='coal'},
                mining_target=opts.mining_target or {name='iron-ore'},
                drop_position=opts.drop_position or {x=1,y=0},
                get_inventory=function(def) return inventories[def] end,
                get_output_inventory=function() return output end,
                surface={
                    find_entities_filtered=function(query)
                        if query.type=='item-entity' then
                            return opts.items_on_ground or {}
                        end
                        return opts.destination and {opts.destination} or {}
                    end,
                },
            }
        end
    """)
    root = Path(__file__).parents[2]
    lua.execute((root / "fle/env/mods/alerts.lua").read_text())
    return lua


def test_full_furnace_result_warns_with_item():
    lua = runtime()
    lua.execute("""
        local furnace=make_furnace({
            status=defines.entity_status.full_output,
            source=make_inv(2,{stack('iron-ore',2)}),
            result=make_inv(1,{stack('iron-plate',100)}),
        })
        local warnings=storage.utils.get_issues(furnace)
        assert(#warnings==1)
        assert(warnings[1]=="'furnace result full: iron-plate 100; extract to resume'")
    """)


def test_full_furnace_result_warns_even_without_full_output_status():
    lua = runtime()
    lua.execute("""
        local furnace=make_furnace({
            status=defines.entity_status.working,
            source=make_inv(2,{stack('iron-ore',2)}),
            result=make_inv(1,{stack('iron-plate',100)}),
        })
        local warnings=storage.utils.get_issues(furnace)
        assert(#warnings==1)
        assert(warnings[1]=="'furnace result full: iron-plate 100; extract to resume'")
    """)


def test_furnace_with_output_space_has_no_warnings():
    lua = runtime()
    lua.execute("""
        local furnace=make_furnace({
            source=make_inv(2,{stack('iron-ore',2)}),
            result=make_inv(2,{stack('iron-plate',3)}),
        })
        local warnings=storage.utils.get_issues(furnace)
        assert(#warnings==0)
    """)


def test_full_assembler_output_warns_with_item():
    lua = runtime()
    lua.execute("""
        local output=make_inv(1,{stack('iron-gear-wheel',100)})
        local input=make_inv(4,{})
        local entity={
            name='assembling-machine-1',type='assembling-machine',
            status=defines.entity_status.full_output,
            position={x=0,y=0},prototype={},
            get_recipe=function() return nil end,
            get_inventory=function(def)
                if def==defines.inventory.assembling_machine_output then
                    return output
                end
                if def==defines.inventory.assembling_machine_input then
                    return input
                end
                return nil
            end,
        }
        local warnings=storage.utils.get_issues(entity)
        assert(#warnings==1)
        assert(warnings[1]=="'output full: iron-gear-wheel 100; extract to resume'")
    """)


def test_drill_destination_furnace_result_full_warns():
    lua = runtime()
    lua.execute("""
        local furnace=make_furnace({
            status=defines.entity_status.full_output,
            source=make_inv(2,{stack('iron-ore',2)}),
            result=make_inv(1,{stack('iron-plate',100)}),
        })
        local drill=make_drill({
            status=defines.entity_status.waiting_for_space_in_destination,
            destination=furnace,
        })
        local warnings=storage.utils.get_issues(drill)
        assert(#warnings==1)
        assert(warnings[1]=="'furnace result at drop position is full: iron-plate 100; extract to resume'")
    """)


def test_drill_destination_furnace_result_full_warns_without_status():
    lua = runtime()
    lua.execute("""
        local furnace=make_furnace({
            status=defines.entity_status.working,
            source=make_inv(2,{stack('iron-ore',2)}),
            result=make_inv(1,{stack('iron-plate',100)}),
        })
        local drill=make_drill({
            status=defines.entity_status.waiting_for_space_in_destination,
            destination=furnace,
        })
        local warnings=storage.utils.get_issues(drill)
        assert(#warnings==1)
        assert(warnings[1]=="'furnace result at drop position is full: iron-plate 100; extract to resume'")
    """)


def test_output_warning_caps_item_list_at_two():
    lua = runtime()
    lua.execute("""
        local output=make_inv(3,{
            stack('iron-plate',10,100),
            stack('copper-plate',20,100),
            stack('coal',30,100),
        })
        local input=make_inv(4,{})
        local entity={
            name='assembling-machine-1',type='assembling-machine',
            status=defines.entity_status.full_output,
            position={x=0,y=0},prototype={},
            get_recipe=function() return nil end,
            get_inventory=function(def)
                if def==defines.inventory.assembling_machine_output then
                    return output
                end
                if def==defines.inventory.assembling_machine_input then
                    return input
                end
                return nil
            end,
        }
        local warnings=storage.utils.get_issues(entity)
        assert(#warnings==1)
        assert(warnings[1]=="'output full: iron-plate 10, copper-plate 20; extract to resume'")
    """)


def test_drill_feeding_healthy_furnace_has_no_warnings():
    lua = runtime()
    lua.execute("""
        local furnace=make_furnace({
            source=make_inv(2,{stack('iron-ore',1)}),
            result=make_inv(2,{stack('iron-plate',3)}),
        })
        local drill=make_drill({
            status=defines.entity_status.working,
            destination=furnace,
        })
        local warnings=storage.utils.get_issues(drill)
        assert(#warnings==0)
    """)


def test_full_drill_output_warns_without_mislabeled_duplicate():
    lua = runtime()
    lua.execute("""
        local drill=make_drill({
            status=defines.entity_status.waiting_for_space_in_destination,
            output=make_inv(1,{stack('iron-ore',100)}),
        })
        local warnings=storage.utils.get_issues(drill)
        local output_warning=nil
        for _,warning in ipairs(warnings) do
            assert(string.find(warning,'fuel source')==nil)
            assert(string.find(warning,'chest is full')==nil)
            if string.find(warning,'output full',1,true) then
                output_warning=warning
            end
        end
        assert(output_warning=="'output full: iron-ore 100; extract to resume'")
    """)
