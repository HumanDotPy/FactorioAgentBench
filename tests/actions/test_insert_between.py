import pytest

from tests.actions.lua_stub_helpers import lua_stub

pytestmark = pytest.mark.no_factorio

WORLD = """
prototypes.entity['wooden-chest']={type='container',tile_width=1,tile_height=1,
    collision_box={left_top={x=-0.5,y=-0.5},right_bottom={x=0.5,y=0.5}}}
prototypes.entity['burner-inserter']={type='inserter',tile_width=1,tile_height=1,
    inserter_pickup_position={0,-1},inserter_drop_position={0,1.2}}
world_entities={}
function surface.find_entities_filtered(query)
    local found={}
    if query.position and query.radius then
        for _,entity in ipairs(world_entities) do
            local dx=entity.position.x-query.position.x
            local dy=entity.position.y-query.position.y
            if math.sqrt(dx*dx+dy*dy)<=query.radius then
                found[#found+1]=entity
            end
        end
    end
    return found
end
"""


def runtime():
    lua = lua_stub(
        """
        storage={utils={},actions={},agent_characters={}}
        prototypes={entity={}}
        defines={direction={north=0,east=4,south=8,west=12}}
        placement_calls={}
        placement_result=nil
        surface={}
        player={position={x=1.5,y=0.5},surface=surface,
            force={name='player'}}
        storage.agent_characters[1]=player
        storage.utils.ensure_valid_character=function() return player end
        storage.utils.inserter_engine_direction=function(entity_name,direction)
            local prototype=prototypes.entity[entity_name]
            if prototype and prototype.type=='inserter' then
                return (direction+8)%16
            end
            return direction
        end
        function storage.actions.place_entity(player_index,inserter,direction,x,y,exact)
            placement_calls[#placement_calls+1]={inserter=inserter,direction=direction,
                x=x,y=y,exact=exact}
            if placement_result == 'raise' then
                error("No "..inserter.." in inventory. Current inventory: empty")
            end
            if placement_result == 'blocked' then
                return {error=true,reason='placement_rejected'}
            end
            return {direction=direction,position={x=x,y=y},drop_side=direction}
        end
        """,
        "tools/agent/insert_between/server.lua",
        unpack=True,
    )
    lua.execute(WORLD)
    lua.execute(
        """
        function add_chest(unit_number,x,y)
            local chest={name='wooden-chest',type='container',valid=true,
                unit_number=unit_number,position={x=x,y=y}}
            world_entities[#world_entities+1]=chest
            return chest
        end
        """
    )
    return lua


def test_places_inserter_in_the_gap_with_drop_side_toward_target():
    lua = runtime()
    result = lua.execute(
        """
        add_chest(1,0.5,0.5)
        add_chest(2,2.5,0.5)
        return storage.actions.insert_between(1,'burner-inserter',0.5,0.5,2.5,0.5)
        """
    )
    assert result["status"] == "placed"
    assert result["tile"]["x"] == 1.5
    assert result["tile"]["y"] == 0.5
    assert result["direction"] == 4
    assert result["pickup_tile"]["x"] == 0.5
    assert result["pickup_tile"]["y"] == 0.5
    assert result["drop_tile"]["x"] == 2.5
    assert result["drop_tile"]["y"] == 0.5
    assert result["attempts"] == 1
    assert result["entity"]["direction"] == 4


def test_edge_adjacent_entities_report_impossible():
    lua = runtime()
    result = lua.execute(
        """
        add_chest(1,0.5,0.5)
        add_chest(2,1.5,0.5)
        return storage.actions.insert_between(1,'burner-inserter',0.5,0.5,1.5,0.5)
        """
    )
    assert result["status"] == "impossible"
    assert "edge-adjacent" in result["reason"]
    assert lua.eval("#placement_calls") == 0


def test_diagonal_entities_report_impossible():
    lua = runtime()
    result = lua.execute(
        """
        add_chest(1,0.5,0.5)
        add_chest(2,1.5,1.5)
        return storage.actions.insert_between(1,'burner-inserter',0.5,0.5,1.5,1.5)
        """
    )
    assert result["status"] == "impossible"
    assert "diagonal" in result["reason"]


def test_too_far_entities_report_the_required_spacing():
    lua = runtime()
    result = lua.execute(
        """
        add_chest(1,0.5,0.5)
        add_chest(2,5.5,0.5)
        return storage.actions.insert_between(1,'burner-inserter',0.5,0.5,5.5,0.5)
        """
    )
    assert result["status"] == "impossible"
    assert "1 tile(s) and drops 1 tile(s)" in result["reason"]


def test_blocked_candidate_reports_rejections():
    lua = runtime()
    result = lua.execute(
        """
        placement_result='blocked'
        add_chest(1,0.5,0.5)
        add_chest(2,2.5,0.5)
        return storage.actions.insert_between(1,'burner-inserter',0.5,0.5,2.5,0.5)
        """
    )
    assert result["status"] == "impossible"
    assert result["attempts"] >= 1
    assert "geometrically valid" in result["reason"]
    assert result["rejections"][1]["reason"] == "placement_rejected"
    assert result["rejections"][1]["tile"]["x"] == 1.5


def test_missing_inventory_aborts_with_the_inventory_reason():
    lua = runtime()
    result = lua.execute(
        """
        placement_result='raise'
        add_chest(1,0.5,0.5)
        add_chest(2,2.5,0.5)
        return storage.actions.insert_between(1,'burner-inserter',0.5,0.5,2.5,0.5)
        """
    )
    assert result["status"] == "impossible"
    assert "inventory" in result["reason"]


def test_same_entity_target_is_reported():
    lua = runtime()
    result = lua.execute(
        """
        add_chest(1,0.5,0.5)
        return storage.actions.insert_between(1,'burner-inserter',0.5,0.5,0.5,0.5)
        """
    )
    assert result["status"] == "impossible"
    assert "same entity" in result["reason"]


def test_non_inserter_prototype_is_rejected():
    lua = runtime()
    with pytest.raises(Exception):
        lua.execute(
            """
            add_chest(1,0.5,0.5)
            add_chest(2,2.5,0.5)
            return storage.actions.insert_between(1,'wooden-chest',0.5,0.5,2.5,0.5)
            """
        )


def test_long_handed_inserter_bridges_a_three_tile_gap():
    lua = runtime()
    result = lua.execute(
        """
        prototypes.entity['long-handed-inserter']={type='inserter',
            tile_width=1,tile_height=1,
            inserter_pickup_position={0,-2},
            inserter_drop_position={0,2.2}}
        add_chest(1,0.5,0.5)
        add_chest(2,4.5,0.5)
        return storage.actions.insert_between(1,'long-handed-inserter',0.5,0.5,4.5,0.5)
        """
    )
    assert result["status"] == "placed"
    assert result["tile"]["x"] == 2.5
    assert result["direction"] == 4
    assert result["pickup_tile"]["x"] == 0.5
    assert result["drop_tile"]["x"] == 4.5
