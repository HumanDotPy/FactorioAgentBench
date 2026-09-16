from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.extract_area.client import ExtractArea
from tests.actions.lua_stub_helpers import lua_stub, stub_client

pytestmark = pytest.mark.no_factorio


def runtime(fast=False):
    return lua_stub(
        """
        storage={actions={},agent_characters={},utils={},fast=%s}
        game={tick=4242}
        defines={inventory={
            chest=1,
            furnace_source=2,furnace_result=3,
            assembling_machine_input=2,assembling_machine_output=3,
            crafter_input=4,crafter_output=5,
            rocket_silo_input=6,rocket_silo_output=7,rocket_silo_rocket=8,
            lab_input=9,fuel=10,burnt_result=11,item_main=1,
            robot_cargo=12,robot_repair=13,car_trunk=14,
            roboport_material=15,roboport_robot=16,
            artillery_turret_ammo=17,turret_ammo=18,beacon_modules=19}}
        insert_blocked={}
        insert_limited={}

        storage.utils.get_contents_compat=function(inventory)
            return inventory.contents
        end

        function make_inventory(contents)
            local inv={contents=contents}
            function inv.remove(stack)
                local have=inv.contents[stack.name] or 0
                local removed=math.min(have,stack.count)
                inv.contents[stack.name]=have-removed
                if inv.contents[stack.name]==0 then inv.contents[stack.name]=nil end
                return removed
            end
            function inv.insert(stack)
                inv.contents[stack.name]=(inv.contents[stack.name] or 0)+stack.count
                return stack.count
            end
            return inv
        end

        function make_entity(props)
            local entity=props
            entity.valid=true
            entity.get_inventory=function(id)
                entity.queried_ids=entity.queried_ids or {}
                if entity.queried_ids[id] then
                    error('inventory id read twice: '..tostring(id))
                end
                entity.queried_ids[id]=true
                if entity.inventories then return entity.inventories[id] end
                return nil
            end
            return entity
        end

        function make_player(entities, position)
            local surface={
                find_entities_filtered=function(query) return entities end,
            }
            local player={
                valid=true,force='player',position=position or {x=0,y=0},
                surface=surface,inserted={},insert_order={},
            }
            function player.insert(stack)
                local accepted=stack.count
                if insert_blocked[stack.name] then accepted=0 end
                if insert_limited[stack.name]~=nil then
                    accepted=math.min(accepted,insert_limited[stack.name])
                end
                player.inserted[stack.name]=(player.inserted[stack.name] or 0)+accepted
                player.insert_order[#player.insert_order+1]=stack.name
                return accepted
            end
            local main={}
            function main.can_insert(stack)
                return not insert_blocked[stack.name]
            end
            function player.get_main_inventory() return main end
            storage.agent_characters[1]=player
            return player
        end
        """
        % ("true" if fast else "false"),
        "tools/agent/extract_area/server.lua",
    )


def test_extracts_matching_items_from_machine_inventories():
    lua = runtime()
    lua.execute("""
        local plates_a=make_inventory({['iron-plate']=7})
        local plates_b=make_inventory({['iron-plate']=3})
        storage.agent_characters[1]=make_player({
            make_entity({name='stone-furnace',type='furnace',unit_number=2,
                position={x=1.5,y=1.5},
                inventories={[defines.inventory.furnace_result]=plates_a}}),
            make_entity({name='steel-furnace',type='furnace',unit_number=1,
                position={x=3.5,y=1.5},
                inventories={[defines.inventory.assembling_machine_output]=plates_b}}),
        })
        result=storage.actions.extract_area(1,0,0,4,4,{'iron-plate'},10,512,4096)
        assert(result.status=='completed','status '..result.status)
        assert(result.scanned==2)
        assert(result.extracted['iron-plate']==10)
        assert(plates_a.contents['iron-plate']==nil)
        assert(plates_b.contents['iron-plate']==nil)
        assert(storage.agent_characters[1].inserted['iron-plate']==10)
        assert(result.tick==4242)
        assert(result.area.left==0 and result.area.right==4)
        assert(result.inventory_full==nil)
        assert(result.truncated==false)
    """)


def test_aliased_inventory_ids_are_scanned_once():
    lua = runtime()
    lua.execute("""
        local inv=make_inventory({['iron-plate']=5})
        make_player({
            make_entity({name='stone-furnace',type='furnace',unit_number=1,
                position={x=1,y=1},
                inventories={[defines.inventory.assembling_machine_input]=inv}}),
        })
        result=storage.actions.extract_area(1,0,0,2,2,{'iron-plate'},10,512,4096,true)
        assert(result.extracted['iron-plate']==5)
        assert(inv.contents['iron-plate']==nil)
    """)


def test_items_none_takes_product_slots_only_by_default():
    lua = runtime()
    lua.execute("""
        local output=make_inventory({['iron-plate']=4})
        local fuel=make_inventory({['coal']=3})
        make_player({
            make_entity({name='stone-furnace',type='furnace',unit_number=1,
                position={x=1,y=1},
                inventories={
                    [defines.inventory.furnace_result]=output,
                    [defines.inventory.fuel]=fuel}}),
        })
        result=storage.actions.extract_area(1,0,0,2,2,nil,10,512,4096)
        assert(result.status=='completed')
        assert(result.extracted['iron-plate']==4)
        assert(result.extracted['coal']==nil)
        assert(output.contents['iron-plate']==nil)
        assert(fuel.contents['coal']==3)
    """)


def test_include_inputs_true_takes_fuel_too():
    lua = runtime()
    lua.execute("""
        local output=make_inventory({['iron-plate']=4})
        local fuel=make_inventory({['coal']=3})
        make_player({
            make_entity({name='stone-furnace',type='furnace',unit_number=1,
                position={x=1,y=1},
                inventories={
                    [defines.inventory.furnace_result]=output,
                    [defines.inventory.fuel]=fuel}}),
        })
        result=storage.actions.extract_area(1,0,0,2,2,nil,10,512,4096,true)
        assert(result.status=='completed')
        assert(result.extracted['iron-plate']==4)
        assert(result.extracted['coal']==3)
        assert(output.contents['iron-plate']==nil)
        assert(fuel.contents['coal']==nil)
    """)


def test_item_filter_does_not_reach_fuel_without_include_inputs():
    lua = runtime()
    lua.execute("""
        local output=make_inventory({['iron-plate']=4})
        local fuel=make_inventory({['coal']=3})
        make_player({
            make_entity({name='stone-furnace',type='furnace',unit_number=1,
                position={x=1,y=1},
                inventories={
                    [defines.inventory.furnace_result]=output,
                    [defines.inventory.fuel]=fuel}}),
        })
        result=storage.actions.extract_area(1,0,0,2,2,{'coal'},10,512,4096)
        assert(result.status=='no_targets')
        assert(result.extracted['coal']==nil)
        assert(fuel.contents['coal']==3)
    """)


def test_item_filter_leaves_other_stacks_alone():
    lua = runtime()
    lua.execute("""
        local output=make_inventory({['iron-plate']=4})
        local fuel=make_inventory({['coal']=3})
        make_player({
            make_entity({name='stone-furnace',type='furnace',unit_number=1,
                position={x=1,y=1},
                inventories={
                    [defines.inventory.furnace_result]=output,
                    [defines.inventory.fuel]=fuel}}),
        })
        result=storage.actions.extract_area(1,0,0,2,2,{'iron-plate'},10,512,4096)
        assert(result.extracted['iron-plate']==4)
        assert(result.extracted['coal']==nil)
        assert(fuel.contents['coal']==3)
    """)


def test_out_of_reach_entities_are_reported_not_extracted():
    lua = runtime()
    lua.execute("""
        local output=make_inventory({['iron-plate']=4})
        make_player({
            make_entity({name='stone-furnace',type='furnace',unit_number=1,
                position={x=50,y=0},
                inventories={[defines.inventory.furnace_result]=output}}),
        },{x=0,y=0})
        result=storage.actions.extract_area(1,-1,-1,51,1,{'iron-plate'},10,512,4096)
        assert(result.status=='partial','status '..result.status)
        assert(result.extracted['iron-plate']==nil)
        assert(#result.out_of_reach==1)
        assert(result.out_of_reach[1].name=='stone-furnace')
        assert(result.out_of_reach[1].position.x==50)
        assert(output.contents['iron-plate']==4)
        assert(result.scanned==1)
    """)


def test_fast_mode_ignores_reach():
    lua = runtime(fast=True)
    lua.execute("""
        local output=make_inventory({['iron-plate']=4})
        make_player({
            make_entity({name='stone-furnace',type='furnace',unit_number=1,
                position={x=50,y=0},
                inventories={[defines.inventory.furnace_result]=output}}),
        },{x=0,y=0})
        result=storage.actions.extract_area(1,-1,-1,51,1,{'iron-plate'},10,512,4096)
        assert(result.status=='completed','status '..result.status)
        assert(result.extracted['iron-plate']==4)
        assert(#result.out_of_reach==0)
    """)


def test_inventory_full_stops_before_removal():
    lua = runtime()
    lua.execute("""
        insert_blocked['iron-plate']=true
        local output=make_inventory({['iron-plate']=4})
        make_player({
            make_entity({name='stone-furnace',type='furnace',unit_number=1,
                position={x=1.5,y=1.5},
                inventories={[defines.inventory.furnace_result]=output}}),
        })
        result=storage.actions.extract_area(1,0,0,3,3,{'iron-plate'},10,512,4096)
        assert(result.status=='inventory_full','status '..result.status)
        assert(result.inventory_full.name=='iron-plate')
        assert(result.inventory_full.position.x==1.5)
        assert(result.extracted['iron-plate']==nil)
        assert(output.contents['iron-plate']==4)
        assert(#storage.agent_characters[1].insert_order==0)
    """)


def test_inventory_full_restores_what_did_not_fit():
    lua = runtime()
    lua.execute("""
        insert_limited['iron-plate']=2
        local output=make_inventory({['iron-plate']=5})
        make_player({
            make_entity({name='stone-furnace',type='furnace',unit_number=1,
                position={x=1.5,y=1.5},
                inventories={[defines.inventory.furnace_result]=output}}),
        })
        result=storage.actions.extract_area(1,0,0,3,3,{'iron-plate'},10,512,4096)
        assert(result.status=='inventory_full')
        assert(result.extracted['iron-plate']==2)
        assert(output.contents['iron-plate']==3)
    """)


def test_max_entities_truncates_scan():
    lua = runtime()
    lua.execute("""
        local third=make_inventory({['iron-plate']=1})
        make_player({
            make_entity({name='a',type='furnace',unit_number=1,
                position={x=1,y=1},
                inventories={[defines.inventory.furnace_result]=make_inventory({['iron-plate']=1})}}),
            make_entity({name='b',type='furnace',unit_number=2,
                position={x=2,y=1},
                inventories={[defines.inventory.furnace_result]=make_inventory({['iron-plate']=1})}}),
            make_entity({name='c',type='furnace',unit_number=3,
                position={x=3,y=1},
                inventories={[defines.inventory.furnace_result]=third}}),
        })
        result=storage.actions.extract_area(1,0,0,4,2,nil,10,2,4096)
        assert(result.scanned==2)
        assert(result.extracted['iron-plate']==2)
        assert(result.truncated==true)
        assert(result.status=='partial')
        assert(third.contents['iron-plate']==1)
    """)


def test_max_items_caps_extraction():
    lua = runtime()
    lua.execute("""
        local output=make_inventory({['iron-plate']=10})
        make_player({
            make_entity({name='stone-furnace',type='furnace',unit_number=1,
                position={x=1,y=1},
                inventories={[defines.inventory.furnace_result]=output}}),
        })
        result=storage.actions.extract_area(1,0,0,2,2,nil,10,512,4)
        assert(result.extracted['iron-plate']==4)
        assert(result.truncated==true)
        assert(result.status=='partial')
        assert(output.contents['iron-plate']==6)
    """)


def test_entities_are_processed_in_unit_number_order():
    lua = runtime()
    lua.execute("""
        make_player({
            make_entity({name='c',type='furnace',unit_number=3,
                position={x=3,y=1},
                inventories={[defines.inventory.furnace_result]=make_inventory({['steel-plate']=1})}}),
            make_entity({name='a',type='furnace',unit_number=1,
                position={x=1,y=1},
                inventories={[defines.inventory.furnace_result]=make_inventory({['copper-plate']=1})}}),
            make_entity({name='b',type='furnace',unit_number=2,
                position={x=2,y=1},
                inventories={[defines.inventory.furnace_result]=make_inventory({['iron-plate']=1})}}),
        })
        result=storage.actions.extract_area(1,0,0,4,2,nil,10,512,4096)
        local order=storage.agent_characters[1].insert_order
        assert(order[1]=='copper-plate')
        assert(order[2]=='iron-plate')
        assert(order[3]=='steel-plate')
        assert(result.extracted['copper-plate']==1)
    """)


def test_entities_without_unit_number_fall_back_to_position():
    lua = runtime()
    lua.execute("""
        make_player({
            make_entity({name='later',type='furnace',
                position={x=2,y=1},
                inventories={[defines.inventory.furnace_result]=make_inventory({['steel-plate']=1})}}),
            make_entity({name='earlier',type='furnace',
                position={x=1,y=1},
                inventories={[defines.inventory.furnace_result]=make_inventory({['copper-plate']=1})}}),
        })
        storage.actions.extract_area(1,0,0,4,2,nil,10,512,4096)
        local order=storage.agent_characters[1].insert_order
        assert(order[1]=='copper-plate')
        assert(order[2]=='steel-plate')
    """)


def test_characters_are_skipped():
    lua = runtime()
    lua.execute("""
        make_player({
            make_entity({name='character',type='character',unit_number=1,
                position={x=1,y=1},
                inventories={[defines.inventory.chest]=make_inventory({['iron-plate']=5})}}),
        })
        result=storage.actions.extract_area(1,0,0,2,2,nil,10,512,4096)
        assert(result.status=='no_targets')
        assert(result.scanned==1)
        assert(#storage.agent_characters[1].insert_order==0)
    """)


def test_no_targets_when_nothing_matches():
    lua = runtime()
    lua.execute("""
        make_player({
            make_entity({name='stone-furnace',type='furnace',unit_number=1,
                position={x=1,y=1},
                inventories={[defines.inventory.furnace_result]=make_inventory({['copper-plate']=1})}}),
        })
        result=storage.actions.extract_area(1,0,0,2,2,{'iron-plate'},10,512,4096)
        assert(result.status=='no_targets')
        assert(next(result.extracted)==nil)
    """)


def test_server_reports_missing_character():
    lua = runtime()
    lua.execute("""
        result=storage.actions.extract_area(99,0,0,1,1,nil,10,512,4096)
        assert(result.error~=nil)
        assert(result.status==nil)
    """)


def test_client_validates_arguments():
    tool = stub_client(ExtractArea, response={"status": "completed"})
    tool.ensure_reachable = Mock()

    with pytest.raises(ValueError, match="top_left must be a Position"):
        tool((0, 0), Position(x=1, y=1))
    with pytest.raises(ValueError, match="bottom_right must be a Position"):
        tool(Position(x=0, y=0), (1, 1))
    with pytest.raises(ValueError, match="items"):
        tool(Position(x=0, y=0), Position(x=1, y=1), items=42)
    with pytest.raises(ValueError, match="items"):
        tool(Position(x=0, y=0), Position(x=1, y=1), items=[])
    with pytest.raises(ValueError, match="items"):
        tool(Position(x=0, y=0), Position(x=1, y=1), items=[42])
    with pytest.raises(ValueError, match="path"):
        tool(Position(x=0, y=0), Position(x=1, y=1), path=1)
    with pytest.raises(ValueError, match="interaction_radius"):
        tool(Position(x=0, y=0), Position(x=1, y=1), interaction_radius=0)
    with pytest.raises(ValueError, match="interaction_radius"):
        tool(Position(x=0, y=0), Position(x=1, y=1), interaction_radius=-1)
    with pytest.raises(ValueError, match="interaction_radius"):
        tool(Position(x=0, y=0), Position(x=1, y=1), interaction_radius=True)
    with pytest.raises(ValueError, match="max_entities"):
        tool(Position(x=0, y=0), Position(x=1, y=1), max_entities=0)
    with pytest.raises(ValueError, match="max_entities"):
        tool(Position(x=0, y=0), Position(x=1, y=1), max_entities=True)
    with pytest.raises(ValueError, match="max_items"):
        tool(Position(x=0, y=0), Position(x=1, y=1), max_items=0)
    with pytest.raises(ValueError, match="max_items"):
        tool(Position(x=0, y=0), Position(x=1, y=1), max_items=-5)
    with pytest.raises(ValueError, match="include_inputs"):
        tool(Position(x=0, y=0), Position(x=1, y=1), include_inputs=1)
    with pytest.raises(ValueError, match="area must be at most 64x64 tiles"):
        tool(Position(x=0, y=0), Position(x=64, y=0))
    with pytest.raises(ValueError, match="area must be at most 64x64 tiles"):
        tool(Position(x=0, y=0), Position(x=0, y=64))

    tool.execute.assert_not_called()
    tool.ensure_reachable.assert_not_called()


def test_client_passes_arguments_and_does_not_walk_when_path_false():
    tool = stub_client(
        ExtractArea,
        player_index=2,
        response={
            "status": "partial",
            "scanned": 1,
            "extracted": {"iron-plate": 3},
            "out_of_reach": [
                {"name": "far", "position": {"x": 40, "y": 0}},
            ],
            "truncated": False,
        },
    )
    tool.ensure_reachable = Mock()

    result = tool(
        Position(x=0.5, y=0.5),
        Position(x=3.5, y=7.5),
        [Prototype.IronPlate],
        path=False,
        interaction_radius=8.0,
        max_entities=100,
        max_items=50,
        include_inputs=True,
    )

    tool.ensure_reachable.assert_not_called()
    tool.execute.assert_called_once_with(
        2, 0.5, 0.5, 3.5, 7.5, ["iron-plate"], 8.0, 100, 50, True
    )
    assert result["status"] == "partial"
    assert result["extracted"] == {"iron-plate": 3}
    assert result["out_of_reach"] == [{"name": "far", "position": {"x": 40, "y": 0}}]
    assert result["inventory_full"] is None


def test_client_walks_to_nearest_out_of_reach_and_merges_extracted():
    tool = stub_client(
        ExtractArea,
        side_effect=[
            (
                {
                    "status": "partial",
                    "extracted": {"iron-plate": 2},
                    "out_of_reach": [
                        {"name": "far", "position": {"x": 60, "y": 0}},
                        {"name": "near", "position": {"x": 50, "y": 0}},
                    ],
                },
                0,
            ),
            (
                {
                    "status": "completed",
                    "extracted": {"iron-plate": 3},
                    "out_of_reach": [],
                },
                0,
            ),
        ],
    )
    tool.game_state = SimpleNamespace(player_location=Position(x=0, y=0))
    tool.ensure_reachable = Mock(return_value=Position(x=49, y=0))

    result = tool(
        Position(x=0, y=0),
        Position(x=61, y=1),
        items=[Prototype.IronPlate],
    )

    assert tool.execute.call_count == 2
    tool.ensure_reachable.assert_called_once_with(Position(x=50, y=0))
    assert result["status"] == "completed"
    assert result["extracted"] == {"iron-plate": 5}


def test_client_stops_when_walking_makes_no_progress():
    stuck = {
        "status": "partial",
        "extracted": {},
        "out_of_reach": [{"name": "far", "position": {"x": 50, "y": 0}}],
    }
    tool = stub_client(ExtractArea, response=stuck)
    tool.game_state = SimpleNamespace(player_location=Position(x=0, y=0))
    tool.ensure_reachable = Mock(return_value=Position(x=0, y=0))

    result = tool(Position(x=0, y=0), Position(x=51, y=1))

    assert tool.execute.call_count == 2
    assert result["status"] == "partial"
    assert result["out_of_reach"] == [{"name": "far", "position": {"x": 50, "y": 0}}]


def test_client_inventory_full_skips_walking():
    tool = stub_client(
        ExtractArea,
        response={
            "status": "inventory_full",
            "extracted": {},
            "out_of_reach": [{"name": "far", "position": {"x": 50, "y": 0}}],
            "inventory_full": {"name": "iron-plate", "position": {"x": 1, "y": 1}},
        },
    )
    tool.game_state = SimpleNamespace(player_location=Position(x=0, y=0))
    tool.ensure_reachable = Mock()

    result = tool(Position(x=0, y=0), Position(x=51, y=1))

    tool.execute.assert_called_once()
    tool.ensure_reachable.assert_not_called()
    assert result["status"] == "inventory_full"
    assert result["inventory_full"]["name"] == "iron-plate"


def test_client_raises_on_server_error():
    tool = stub_client(ExtractArea, response={"error": "Player not found"})
    tool.ensure_reachable = Mock()

    with pytest.raises(Exception, match="Could not extract area"):
        tool(Position(x=0, y=0), Position(x=1, y=1))

    tool.execute = Mock(return_value=("boom", 0))
    with pytest.raises(Exception, match="Could not extract area"):
        tool(Position(x=0, y=0), Position(x=1, y=1))


def test_client_normalizes_integer_keyed_out_of_reach():
    tool = stub_client(
        ExtractArea,
        response={
            "status": "partial",
            "extracted": {},
            "out_of_reach": {1: {"name": "far", "position": {"x": 5, "y": 6}}},
        },
    )
    tool.ensure_reachable = Mock()

    result = tool(Position(x=0, y=0), Position(x=1, y=1), path=False)

    assert result["out_of_reach"] == [{"name": "far", "position": {"x": 5, "y": 6}}]
