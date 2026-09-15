from pathlib import Path

import pytest
from lupa.lua54 import LuaRuntime

pytestmark = pytest.mark.no_factorio


def runtime():
    lua = LuaRuntime()
    lua.execute("""
        storage={actions={},utils={}}
        defines={
            inventory={chest=1,crafter_input=2,fuel=3,character_main=4},
            direction={north=0,east=4,south=8,west=12},
        }
        prototypes={
            item={
                coal={name='coal',fuel_value=4000000},
                wood={name='wood',fuel_value=2000000},
            },
            recipe={},
        }
        serpent={line=function() return 'pos' end}

        function make_inv(items, capacity)
            local inv={}
            for i=1,capacity do
                inv[i]=items[i] or {valid_for_read=false}
            end
            inv.is_empty=function()
                for _,s in ipairs(inv) do
                    if s.valid_for_read then return false end
                end
                return true
            end
            inv.can_insert=function(item) return true end
            inv.remove=function(item)
                local removed=0
                local wanted=item.count or 0
                for i=1,#inv do
                    local s=inv[i]
                    if s.valid_for_read
                        and (item.name==nil or s.name==item.name) then
                        local take=math.min(s.count, wanted-removed)
                        s.count=s.count-take
                        removed=removed+take
                        if s.count<=0 then inv[i]={valid_for_read=false} end
                        if removed>=wanted then break end
                    end
                end
                return removed
            end
            return inv
        end

        fuel=make_inv({{valid_for_read=true,name='wood',count=2}},1)
        input=make_inv({},5)
        entity={
            name='stone-furnace',type='furnace',burner={},
            position={x=0,y=0},
            get_inventory=function(def)
                if def==defines.inventory.fuel then return fuel end
                return input
            end,
            insert=function(item)
                for i=1,#fuel do
                    local s=fuel[i]
                    if s.valid_for_read and s.name==item.name then
                        s.count=s.count+item.count
                        return item.count
                    end
                end
                for i=1,#fuel do
                    if not fuel[i].valid_for_read then
                        fuel[i]={valid_for_read=true,name=item.name,
                            count=item.count}
                        return item.count
                    end
                end
                return 0
            end,
        }
        main=make_inv({},50)
        player={
            position={x=1,y=1},force='player',
            surface={find_entities_filtered=function(query) return {entity} end},
            get_item_count=function() return 100 end,
            get_inventory=function(def) return main end,
            insert=function(item) return item.count end,
            remove_item=function() end,
        }
        storage.utils.ensure_valid_character=function() return player end
        storage.utils.serialize_entity=function() return {marker='serialized'} end
    """)
    root = Path(__file__).parents[2]
    lua.execute((root / "fle/env/tools/agent/insert_item/server.lua").read_text())
    return lua


def test_fuel_swap_requires_replace_and_names_blocker():
    lua = runtime()
    lua.execute("""
        local ok, err = pcall(storage.actions.insert_item, 1, 'coal', 10,
            0, 0, 'stone-furnace', false)
        assert(not ok)
        assert(string.find(tostring(err), 'fuel slot holds 2 wood') ~= nil)
        assert(string.find(tostring(err), 'replace=true') ~= nil)
        assert(fuel[1].name == 'wood' and fuel[1].count == 2)
    """)


def test_fuel_swap_replaces_and_reports_moved_items():
    lua = runtime()
    lua.execute("""
        local result = storage.actions.insert_item(1, 'coal', 10,
            0, 0, 'stone-furnace', true)
        assert(result.replaced_fuel ~= nil)
        assert(result.replaced_fuel.name == 'wood')
        assert(result.replaced_fuel.count == 2)
        assert(fuel[1].name == 'coal')
    """)


def test_fuel_insert_without_conflict_is_untouched():
    lua = runtime()
    lua.execute("""
        fuel[1]={valid_for_read=true,name='coal',count=5}
        local result = storage.actions.insert_item(1, 'coal', 10,
            0, 0, 'stone-furnace', false)
        assert(result.replaced_fuel == nil)
    """)
