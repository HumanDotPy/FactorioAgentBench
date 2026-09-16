from unittest.mock import Mock

import pytest

from fle.env.entities import BeltGroup, Direction, Position, TransportBelt
from fle.env.game_types import Prototype
from fle.env.tools.agent.insert_item.client import InsertItem
from tests.actions.lua_stub_helpers import lua_stub, stub_client

pytestmark = pytest.mark.no_factorio


def runtime():
    return lua_stub(
        """
        storage={actions={},utils={}}
        defines={
            inventory={chest=1,crafter_input=2,fuel=3,character_main=4},
            direction={north=0,east=4,south=8,west=12},
        }
        prototypes={
            item={
                coal={name='coal',fuel_value=4000000,stack_size=50},
                wood={name='wood',fuel_value=2000000,stack_size=50},
                ['iron-ore']={name='iron-ore',stack_size=50},
                ['iron-gear-wheel']={name='iron-gear-wheel',stack_size=100},
            },
            recipe={},
        }
        serpent={line=function() return 'pos' end}

        insert_limit=nil
        main_insert_limit=nil
        main_removed={}
        player_item_count=nil

        function make_inv(slots, capacity)
            local inv={}
            for i=1,capacity do
                inv[i]=slots[i] or {valid_for_read=false}
            end
            function inv.is_empty()
                for _,s in ipairs(inv) do
                    if s.valid_for_read then return false end
                end
                return true
            end
            function inv.can_insert(item) return true end
            function inv.insert(item)
                local limit=insert_limit
                insert_limit=nil
                local remaining=item.count
                if limit~=nil then
                    remaining=math.min(remaining, limit)
                end
                if remaining<=0 then return 0 end
                local wanted=remaining
                for i=1,#inv do
                    local s=inv[i]
                    if s.valid_for_read and s.name==item.name then
                        local space=(prototypes.item[item.name].stack_size or 100)-s.count
                        local take=math.min(space, remaining)
                        s.count=s.count+take
                        remaining=remaining-take
                        if remaining<=0 then return wanted end
                    end
                end
                for i=1,#inv do
                    if not inv[i].valid_for_read then
                        local space=prototypes.item[item.name].stack_size or 100
                        local take=math.min(space, remaining)
                        inv[i]={valid_for_read=true,name=item.name,count=take}
                        remaining=remaining-take
                        if remaining<=0 then return wanted end
                    end
                end
                return wanted-remaining
            end
            function inv.remove(item)
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

        function make_main(capacity)
            local inv={}
            inv.contents={}
            function inv.used()
                local total=0
                for _,count in pairs(inv.contents) do total=total+count end
                return total
            end
            function inv.can_insert(item)
                return inv.used()+item.count <= capacity
            end
            function inv.insert(item)
                local limit=main_insert_limit
                main_insert_limit=nil
                local take=math.min(capacity-inv.used(), item.count)
                if limit~=nil then
                    take=math.min(take, limit)
                end
                if take>0 then
                    inv.contents[item.name]=(inv.contents[item.name] or 0)+take
                end
                return take
            end
            function inv.remove(item)
                local have=inv.contents[item.name] or 0
                local take=math.min(have, item.count)
                inv.contents[item.name]=have-take
                main_removed[#main_removed+1]={name=item.name,count=take}
                return take
            end
            return inv
        end

        fuel=make_inv({{valid_for_read=true,name='wood',count=2}},1)
        chest_inv=make_inv({},1)
        input=make_inv({},5)
        main=make_main(500)
        current_entity=nil
        player={
            position={x=1,y=1},force='player',
            surface={find_entities_filtered=function(query)
                return {current_entity}
            end},
            get_item_count=function() return player_item_count or 100 end,
            get_inventory=function(def) return main end,
            insert=function(item) return main.insert(item) end,
            remove_item=function(item) return main.remove(item) end,
        }
        storage.utils.ensure_valid_character=function() return player end
        storage.utils.serialize_entity=function(entity)
            return {marker='serialized',name=entity.name,
                position=entity.position,warnings={}}
        end

        function make_furnace()
            return {
                name='stone-furnace',type='furnace',burner={},
                position={x=0,y=0},
                get_inventory=function(def)
                    if def==defines.inventory.fuel then return fuel end
                    return input
                end,
                insert=function(item) return fuel.insert(item) end,
            }
        end

        function make_chest()
            return {
                name='iron-chest',type='container',
                position={x=0,y=0},
                get_inventory=function(def)
                    if def==defines.inventory.chest then return chest_inv end
                    return nil
                end,
                insert=function(item) return chest_inv.insert(item) end,
            }
        end

        function make_assembler(output_name, output_inventory)
            return {
                name='assembling-machine-1',type='assembling-machine',
                position={x=0,y=0},
                get_recipe=function()
                    return {
                        ingredients={{name='iron-ore',amount=2}},
                        products={{name=output_name,amount=1}},
                    }
                end,
                get_output_inventory=function() return output_inventory end,
                get_module_inventory=function() return nil end,
                insert=function() return 0 end,
            }
        end
        """,
        "tools/agent/insert_item/server.lua",
    )


def test_fuel_swap_requires_replace_and_names_blocker():
    lua = runtime()
    lua.execute("""
        current_entity=make_furnace()
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
        current_entity=make_furnace()
        local result = storage.actions.insert_item(1, 'coal', 10,
            0, 0, 'stone-furnace', true)
        assert(result.replaced_fuel ~= nil)
        assert(result.replaced_fuel.name == 'wood')
        assert(result.replaced_fuel.count == 2)
        assert(fuel[1].name == 'coal' and fuel[1].count == 10)
        assert(main.contents['wood'] == 2)
    """)


def test_fuel_insert_without_conflict_is_untouched():
    lua = runtime()
    lua.execute("""
        current_entity=make_furnace()
        fuel[1]={valid_for_read=true,name='coal',count=5}
        local result = storage.actions.insert_item(1, 'coal', 10,
            0, 0, 'stone-furnace', false)
        assert(result.replaced_fuel == nil)
        assert(result.inserted == 10 and result.requested == 10)
        assert(result.insert_status == 'completed')
    """)


def test_partial_insert_reports_partial_receipt():
    lua = runtime()
    lua.execute("""
        current_entity=make_furnace()
        insert_limit=3
        local result = storage.actions.insert_item(1, 'coal', 10,
            0, 0, 'stone-furnace', true)
        assert(result.inserted == 3)
        assert(result.requested == 10)
        assert(result.insert_status == 'partial')
        assert(#result.warnings >= 1)
        assert(string.find(result.warnings[1], 'partial insert') ~= nil)
        assert(fuel[1].name == 'coal' and fuel[1].count == 3)
        assert(main.contents['wood'] == 2)
        insert_limit=nil
    """)


def test_failed_new_insert_restores_old_fuel():
    lua = runtime()
    lua.execute("""
        current_entity=make_furnace()
        insert_limit=0
        local ok, err = pcall(storage.actions.insert_item, 1, 'coal', 10,
            0, 0, 'stone-furnace', true)
        assert(not ok)
        assert(string.find(tostring(err), 'Failed to insert') ~= nil)
        assert(fuel[1].name == 'wood' and fuel[1].count == 2)
        assert((main.contents['wood'] or 0) == 0)
        assert(#main_removed == 1 and main_removed[1].name == 'wood'
            and main_removed[1].count == 2)
        insert_limit=nil
    """)


def test_partial_player_take_during_swap_restores_remainder():
    lua = runtime()
    lua.execute("""
        current_entity=make_furnace()
        main_insert_limit=1
        local ok, err = pcall(storage.actions.insert_item, 1, 'coal', 10,
            0, 0, 'stone-furnace', true)
        assert(not ok)
        assert(string.find(tostring(err), 'could not move all') ~= nil)
        assert(fuel[1].name == 'wood' and fuel[1].count == 1)
        assert(main.contents['wood'] == 1)
        main_insert_limit=nil
    """)


def test_partial_target_capacity_reports_remaining_capacity():
    lua = runtime()
    lua.execute("""
        current_entity=make_furnace()
        fuel[1]={valid_for_read=true,name='coal',count=40}
        local result = storage.actions.insert_item(1, 'coal', 20,
            0, 0, 'stone-furnace', false)
        assert(result.inserted == 10)
        assert(result.requested == 20)
        assert(result.insert_status == 'partial')
        assert(result.remaining_capacity == 0)
        assert(fuel[1].name == 'coal' and fuel[1].count == 50)
    """)


def test_nothing_accepted_names_remaining_capacity():
    lua = runtime()
    lua.execute("""
        current_entity=make_furnace()
        fuel[1]={valid_for_read=true,name='coal',count=50}
        local ok, err = pcall(storage.actions.insert_item, 1, 'coal', 20,
            0, 0, 'stone-furnace', false)
        assert(not ok)
        assert(string.find(tostring(err), 'nothing could be accepted') ~= nil)
        assert(string.find(tostring(err), 'Remaining capacity: 0') ~= nil)
        assert(fuel[1].count == 50)
    """)


def test_player_stock_shortfall_is_a_partial_receipt():
    lua = runtime()
    lua.execute("""
        current_entity=make_furnace()
        player_item_count=3
        fuel[1]={valid_for_read=false}
        local result = storage.actions.insert_item(1, 'coal', 10,
            0, 0, 'stone-furnace', false)
        assert(result.inserted == 3)
        assert(result.requested == 10)
        assert(result.insert_status == 'partial')
        assert(result.remaining_capacity == 47)
    """)


def test_chest_insert_clamps_to_capacity():
    lua = runtime()
    lua.execute("""
        current_entity=make_chest()
        chest_inv[1]={valid_for_read=true,name='iron-ore',count=48}
        local result = storage.actions.insert_item(1, 'iron-ore', 20,
            0, 0, 'iron-chest', false)
        assert(result.inserted == 2)
        assert(result.requested == 20)
        assert(result.insert_status == 'partial')
        assert(result.remaining_capacity == 0)
        assert(chest_inv[1].count == 50)
    """)


def test_assembler_product_insert_is_reported():
    lua = runtime()
    lua.execute("""
        local output={insert=function(item) return item.count end}
        current_entity=make_assembler('iron-gear-wheel', output)
        local result = storage.actions.insert_item(1, 'iron-gear-wheel', 100,
            0, 0, 'assembling-machine-1', false)
        assert(result.assembler_output_insert ~= nil)
        assert(result.assembler_output_insert.name == 'iron-gear-wheel')
        assert(result.assembler_output_insert.count == 100)
        local warned=false
        for _,warning in ipairs(result.warnings) do
            if string.find(warning, 'production statistics') ~= nil then
                warned=true
            end
        end
        assert(warned)
    """)


def make_belt(position):
    return TransportBelt.model_construct(
        name="transport-belt",
        direction=Direction.UP,
        position=position,
        input_position=Position(x=position.x, y=position.y + 1),
        output_position=Position(x=position.x, y=position.y - 1),
    )


def make_group(input_position, belt_position):
    return BeltGroup.model_construct(
        id=7,
        position=Position(x=0, y=0),
        belts=[make_belt(belt_position)],
        inputs=[make_belt(input_position)],
        outputs=[],
        inventory={},
    )


def test_belt_coordinate_zero_is_not_treated_as_missing():
    tool = stub_client(
        InsertItem,
        response={
            "inserted": 5,
            "requested": 5,
            "insert_status": "completed",
            "warnings": [],
        },
    )
    tool.ensure_reachable = Mock()
    fresh = make_belt(Position(x=0, y=0))
    tool.get_entities = Mock(return_value=[fresh])

    group = make_group(Position(x=0, y=0), Position(x=9, y=9))
    result = tool(Prototype.IronOre, group, quantity=5)

    tool.execute.assert_called_once_with(1, "iron-ore", 5, 0, 0, None, False)
    assert result is fresh
    assert result.inserted == 5
    assert result.insert_status == "completed"


def test_belt_partial_insert_is_surfaced():
    tool = stub_client(
        InsertItem,
        response={
            "inserted": 3,
            "requested": 5,
            "insert_status": "partial",
            "warnings": ["partial insert: 3 of 5 iron-ore inserted"],
        },
    )
    tool.ensure_reachable = Mock()
    fresh = make_belt(Position(x=0, y=0))
    tool.get_entities = Mock(return_value=[fresh])

    result = tool(Prototype.IronOre, make_group(Position(x=0, y=0), Position(x=0, y=0)))

    assert result.inserted == 3
    assert result.requested == 5
    assert result.insert_status == "partial"
    assert any("partial insert" in warning for warning in result.warnings)


def test_receipt_surfaces_remaining_capacity_when_reported():
    target = make_belt(Position(x=0, y=0))
    result = InsertItem._apply_receipt(
        target,
        {
            "inserted": 2,
            "requested": 5,
            "insert_status": "partial",
            "remaining_capacity": 0,
        },
        5,
    )
    assert result.inserted == 2
    assert result.remaining_capacity == 0

    result = InsertItem._apply_receipt(
        make_belt(Position(x=1, y=1)),
        {"inserted": 5, "requested": 5, "insert_status": "completed"},
        5,
    )
    assert not hasattr(result, "remaining_capacity")


def test_belt_response_without_inserted_count_raises():
    tool = stub_client(InsertItem, response={"marker": "serialized"})
    tool.ensure_reachable = Mock()
    tool.get_entities = Mock(return_value=[make_belt(Position(x=0, y=0))])

    with pytest.raises(Exception, match="did not report how many items"):
        tool(Prototype.IronOre, make_group(Position(x=0, y=0), Position(x=0, y=0)))
