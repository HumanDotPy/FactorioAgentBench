"""Agent-facing direction contract for rotatable prototypes (stub world).

Agent-facing inserter directions name the DROP side; blueprints and the engine
store the PICKUP side. This test places every prototype in the table in all
four directions through the real ``place_entity`` boundary and asserts the
read-back geometry from the real ``serialize_entity``.
"""

import pytest

from fle.env.entities import Direction
from tests.actions.lua_stub_helpers import lua_stub

pytestmark = pytest.mark.no_factorio

OPPOSITE = {
    Direction.NORTH.value: Direction.SOUTH.value,
    Direction.EAST.value: Direction.WEST.value,
    Direction.SOUTH.value: Direction.NORTH.value,
    Direction.WEST.value: Direction.EAST.value,
}

DIRECTIONS = (
    Direction.NORTH.value,
    Direction.EAST.value,
    Direction.SOUTH.value,
    Direction.WEST.value,
)


def runtime():
    lua = lua_stub(
        """
        storage={actions={},utils={},agent_characters={}}
        defines={direction={north=0,east=4,south=8,west=12},
            events={on_tick=1},
            entity_status={normal=1,working=2,full_output=3,
                no_minable_resources=4,waiting_for_source_items=6},
            inventory={item_main=1,chest=2,fuel=3,assembling_machine_input=4,
                crafter_input=5,furnace_source=6},
            build_check_type={manual=1}}
        prototypes={item={},quality={normal={name='normal'}},entity={}}
        script={on_nth_tick=function() end,on_event=function() end}
        """,
        "mods/initialise.lua",
        "mods/utils.lua",
        "mods/serialize.lua",
        "tools/agent/place_entity/server.lua",
        unpack=True,
    )
    lua.execute(
        """
        game={surfaces={{get_tile=function() return {name='grass-1'} end,
            find_entities_filtered=function() return {} end}}}
        created={}
        simulate_mirrored_geometry=false
        local id=0
        local vectors={[0]={x=0,y=-1},[4]={x=1,y=0},[8]={x=0,y=1},[12]={x=-1,y=0}}
        local function vec(direction,distance)
            local v=vectors[direction]
            return {x=v.x*distance,y=v.y*distance}
        end
        surface={}
        function surface.create_entity(params)
            id=id+1
            local name=params.name
            local kind=prototypes.entity[name].type
            local entity={valid=true,name=name,type=kind,unit_number=id,
                position={x=params.position.x,y=params.position.y},
                direction=params.direction,health=100,energy=0,
                status=defines.entity_status.normal,surface=surface,
                prototype=prototypes.entity[name],
                get_inventory=function() return nil end}
            if kind=='inserter' then
                local pickup=vec(params.direction,1)
                local drop=vec(params.direction,1.2)
                if simulate_mirrored_geometry then
                    drop={x=-drop.x,y=-drop.y}
                end
                entity.pickup_position={x=entity.position.x+pickup.x,
                    y=entity.position.y+pickup.y}
                entity.drop_position={x=entity.position.x-drop.x,
                    y=entity.position.y-drop.y}
            elseif kind=='mining-drill' then
                local drop=vec(params.direction,1.2)
                entity.drop_position={x=entity.position.x+drop.x,
                    y=entity.position.y+drop.y}
            else
                entity.belt_neighbours={inputs={},outputs={}}
                entity.get_transport_line=function(index)
                    return {contents={},get_contents=function() return {} end,
                        can_insert_at_back=function() return true end}
                end
            end
            created[#created+1]=entity
            return entity
        end
        function surface.find_entities_filtered(query) return {} end
        function surface.can_place_entity(query) return true end
        player={position={x=10.5,y=10.5},reach_distance=10,force={name='player'},
            surface=surface,
            get_item_count=function() return 1 end,
            remove_item=function() return 1 end,
            get_main_inventory=function()
                return {get_item_count=function() return 1 end,
                    remove=function() return 1 end}
            end}
        storage.agent_characters[1]=player
        storage.utils.ensure_valid_character=function() return player end
        storage.utils.can_place_entity=function() return true end
        storage.utils.get_issues=function() return {} end
        storage.utils.attach_connection_report=function(serialized) return serialized end
        storage.utils.spatial_diagnostics=function() return {} end
        local prototype_table={
            {kind='inserter',names={'burner-inserter','inserter','fast-inserter',
                'long-handed-inserter','bulk-inserter'}},
            {kind='mining-drill',names={'burner-mining-drill','electric-mining-drill'}},
            {kind='transport-belt',names={'transport-belt','fast-transport-belt',
                'express-transport-belt','underground-belt','fast-underground-belt',
                'express-underground-belt'}},
            {kind='splitter',names={'splitter','fast-splitter','express-splitter'}},
        }
        entity_prototypes=prototype_table
        for _,group in ipairs(prototype_table) do
            for _,name in ipairs(group.names) do
                prototypes.entity[name]={type=group.kind,tile_width=1,tile_height=1,
                    collision_box={left_top={x=-0.5,y=-0.5},
                        right_bottom={x=0.5,y=0.5}}}
            end
        end
        """
    )
    return lua


def run_contract(lua, mirrored=False):
    return lua.execute(
        """
        simulate_mirrored_geometry=%s
        local results={}
        for _,group in ipairs(entity_prototypes) do
            for _,name in ipairs(group.names) do
                for _,direction in ipairs({0,4,8,12}) do
                    created={}
                    local receipt=storage.actions.place_entity(1,name,direction,10.5,10.5,true)
                    results[#results+1]={name=name,kind=group.kind,
                        requested=direction,engine=created[1].direction,
                        receipt=receipt}
                end
            end
        end
        return results
        """
        % ("true" if mirrored else "false")
    )


def test_every_rotatable_prototype_round_trips_agent_direction():
    lua = runtime()
    groups = lua.eval("entity_prototypes")
    expected = 4 * sum(len(groups[index]["names"]) for index in range(1, 5))
    results = run_contract(lua)
    assert len(results) == expected
    seen = set()
    for index in range(1, len(results) + 1):
        row = results[index]
        name = row["name"]
        kind = row["kind"]
        requested = int(row["requested"])
        receipt = row["receipt"]
        seen.add(name)
        assert receipt["direction"] == requested, (name, requested)
        if kind == "inserter":
            assert row["engine"] == OPPOSITE[requested], (name, requested)
            assert receipt["drop_side"] == requested, (name, requested)
            assert receipt["pickup_side"] == OPPOSITE[requested], (name, requested)
            assert receipt["drop_side_name"] is not None
            assert receipt["pickup_side_name"] is not None
        else:
            assert row["engine"] == requested, (name, requested)
            assert receipt["drop_side"] is None
        if kind in ("transport-belt", "underground-belt"):
            position = row["receipt"]["position"]
            direction = requested
            offsets = {0: (0.0, -1.0), 4: (1.0, 0.0), 8: (0.0, 1.0), 12: (-1.0, 0.0)}
            dx, dy = offsets[direction]
            assert receipt["output_position"]["x"] == position["x"] + dx
            assert receipt["output_position"]["y"] == position["y"] + dy
            assert receipt["input_position"]["x"] == position["x"] - dx
            assert receipt["input_position"]["y"] == position["y"] - dy
    assert seen == {
        "burner-inserter",
        "inserter",
        "fast-inserter",
        "long-handed-inserter",
        "bulk-inserter",
        "burner-mining-drill",
        "electric-mining-drill",
        "transport-belt",
        "fast-transport-belt",
        "express-transport-belt",
        "underground-belt",
        "fast-underground-belt",
        "express-underground-belt",
        "splitter",
        "fast-splitter",
        "express-splitter",
    }


def test_direction_helper_is_self_inverse_and_identity_for_non_inserters():
    lua = runtime()
    for name in ("burner-inserter", "long-handed-inserter"):
        for direction in DIRECTIONS:
            engine = lua.eval(
                f"storage.utils.inserter_engine_direction('{name}', {direction})"
            )
            assert engine == OPPOSITE[direction]
            assert (
                lua.eval(f"storage.utils.inserter_engine_direction('{name}', {engine})")
                == direction
            )
    for name in ("transport-belt", "electric-mining-drill"):
        for direction in DIRECTIONS:
            assert (
                lua.eval(
                    f"storage.utils.inserter_engine_direction('{name}', {direction})"
                )
                == direction
            )


def test_placement_warns_when_geometry_does_not_match_requested_drop_side():
    lua = runtime()
    results = run_contract(lua, mirrored=True)
    warnings = [
        results[index]["receipt"]["direction_warning"]
        for index in range(1, len(results) + 1)
        if results[index]["kind"] == "inserter"
        and results[index]["receipt"]["direction_warning"]
    ]
    assert warnings
    assert all("drop side" in warning for warning in warnings)


def test_waiting_for_source_items_reports_looking_at_tile():
    lua = runtime()
    result = lua.execute(
        """
        local pickup_x=10.5
        local inserter={valid=true,name='burner-inserter',type='inserter',
            unit_number=900,position={x=11.5,y=10.5},direction=12,
            health=100,energy=0,status=defines.entity_status.waiting_for_source_items,
            pickup_position={x=pickup_x,y=10.5},drop_position={x=12.7,y=10.5},
            get_inventory=function() return nil end}
        local chest={valid=true,name='wooden-chest',type='container',
            unit_number=901,position={x=10.5,y=10.5},status=defines.entity_status.normal}
        function chest.get_inventory(define)
            if define==defines.inventory.chest then
                return {get_contents=function()
                    return {{name='coal',count=5,quality='normal'}} end}
            end
            return nil
        end
        inserter.surface={find_entities_filtered=function(query)
            if query.position and query.radius then return {chest} end
            return {}
        end}
        prototypes.entity['burner-inserter']={type='inserter',tile_width=1,tile_height=1,
            collision_box={left_top={x=-0.5,y=-0.5},right_bottom={x=0.5,y=0.5}}}
        local serialized=storage.utils.serialize_entity(inserter)
        return serialized
        """
    )
    assert result["status"] == '"waiting_for_source_items"'
    looking_at = result["status_reason"]["looking_at"]
    assert looking_at["tile"]["x"] == 10.5
    assert looking_at["tile"]["y"] == 10.5
    assert looking_at["entity"]["name"] == "wooden-chest"
    assert looking_at["entity"]["entity_id"] == 901
    assert looking_at["item"] == "coal"
