import pytest

from fle.env.entities import Dimensions, Entity, Position, TileDimensions
from fle.env.game_types import Prototype
from fle.env.tools.agent.catch_output.client import CatchOutput, _catch_tile
from fle.env.tools.agent.place_entity.client import PlaceObject
from tests.actions.lua_stub_helpers import lua_stub

pytestmark = pytest.mark.no_factorio


def drill(
    name="burner-mining-drill",
    position=(0.0, 0.0),
    drop=(0.0, -1.5),
    tile=(2, 2),
    entity_id=7,
):
    return Entity(
        id=entity_id,
        name=name,
        position=Position(x=position[0], y=position[1]),
        energy=0,
        dimensions=Dimensions(width=tile[0], height=tile[1]),
        tile_dimensions=TileDimensions(tile_width=tile[0], tile_height=tile[1]),
        health=300,
        drop_position=None if drop is None else Position(x=drop[0], y=drop[1]),
    )


def make_client_tool(response, entities=None):
    tool = CatchOutput.__new__(CatchOutput)
    tool.player_index = 1
    tool.calls = []

    def execute(*args):
        tool.calls.append(args)
        return response, 0.0

    tool.execute = execute
    tool.ensure_reachable = lambda target, stop_distance=5.5: Position(x=0, y=0)
    if entities is not None:
        tool.get_entities = lambda entities=set(), position=None, radius=1000: list(
            entities
        )
    return tool


def test_client_receipt_computes_catch_tile_footprint_and_parity():
    response = {
        "status": "placed",
        "placed": {
            "entity_id": 42,
            "name": "iron-chest",
            "position": {"x": -11.5, "y": -69.5},
        },
        "warnings": [],
        "tick": 90,
    }
    tool = make_client_tool(response)
    source = drill(position=(-12.0, -69.0), drop=(-11.5, -69.5), tile=(2, 2))

    receipt = tool(source)

    assert tool.calls == [(1, 7, "iron-chest", -12.0, -69.0)]
    assert receipt["status"] == "placed"
    assert receipt["drop_position"] == {"x": -11.5, "y": -69.5}
    assert receipt["catch_tile"] == {"x": -11.5, "y": -69.5}
    assert receipt["source"]["parity"] == "corner"
    assert receipt["source"]["footprint"] == {
        "left_top": {"x": -13.0, "y": -70.0},
        "right_bottom": {"x": -11.0, "y": -68.0},
    }
    assert receipt["placed"]["entity_id"] == 42
    assert receipt["item_on_ground_before"] == 0
    assert receipt["tick"] == 90


def test_client_position_source_resolves_machine_and_rejects_missing_drop():
    tool = make_client_tool({"status": "blocked", "warnings": ["blocked"]})
    tool.get_entities = lambda entities=set(), position=None, radius=1000: [drill()]

    receipt = tool(Position(x=0.0, y=0.0))

    assert receipt["catch_tile"] == {"x": 0.5, "y": -1.5}
    assert receipt["status"] == "blocked"

    tool.get_entities = lambda entities=set(), position=None, radius=1000: [
        drill(drop=None)
    ]
    with pytest.raises(ValueError, match="mining drill"):
        tool(Position(x=0.0, y=0.0))

    with pytest.raises(ValueError, match="no drop_position"):
        make_client_tool({"status": "placed"})(drill(drop=None))


def test_catch_tile_recipe_floors_then_centers():
    assert _catch_tile(Position(x=-12.0, y=-69.0)) == Position(x=-11.5, y=-68.5)
    assert _catch_tile(Position(x=0.5, y=0.5)) == Position(x=0.5, y=0.5)


def catch_lua(stub=""):
    return lua_stub(
        """
        storage={utils={},actions={},entity_handles={},agent_characters={}}
        game={tick=123}
        defines={inventory={chest=1,furnace_source=2,assembling_machine_input=3,
                crafter_input=4},
            build_check_type={manual=1}}
        place_calls={}
        catch_tile_entities={}
        wide_entities={}
        storage.utils.ensure_valid_character=function(index)
            return storage.agent_characters[index]
        end
        player={position={x=0,y=0},surface={}}
        player.surface.find_entities_filtered=function(query)
            if query.position and query.radius and query.radius<=0.5 then
                return catch_tile_entities
            end
            if query.position and query.radius then
                return wide_entities
            end
            return {}
        end
        storage.agent_characters[1]=player
        storage.actions.place_entity=function(player_index,prototype,direction,x,y,exact)
            place_calls[#place_calls+1]={prototype=prototype,direction=direction,
                x=x,y=y,exact=exact}
            return {id=42,name=prototype,position={x=x,y=y}}
        end
        function make_drill(opts)
            opts=opts or {}
            return {name=opts.name or 'burner-mining-drill',type='mining-drill',
                valid=true,unit_number=opts.entity_id or 7,
                position={x=opts.x or 0,y=opts.y or 0},
                prototype={tile_width=opts.width or 2,tile_height=opts.height or 2},
                drop_position={x=opts.drop_x or 0,y=opts.drop_y or 0}}
        end
        function make_chest(entity_id)
            return {name='steel-chest',type='container',valid=true,
                unit_number=entity_id or 9,position={x=0.5,y=-1.5},
                get_inventory=function(def)
                    if def==defines.inventory.chest then return {} end
                    return nil
                end}
        end
        function make_blocker(entity_id)
            return {name='stone-furnace',type='furnace',valid=true,
                unit_number=entity_id or 11,position={x=0.5,y=-1.5},
                get_inventory=function(def) return nil end}
        end
        """
        + stub,
        "tools/agent/catch_output/server.lua",
        unpack=True,
    )


def test_lua_catch_tile_footprint_and_ready_placement():
    lua = catch_lua()
    lua.execute(
        """
        local source=make_drill({x=-12,y=-69,drop_x=-11.5,drop_y=-69.5})
        storage.entity_handles[7]=source
        local receipt=storage.actions.catch_output(1,7,'iron-chest',-12,-69)
        assert(receipt.status=='placed')
        assert(receipt.catch_tile.x==-11.5 and receipt.catch_tile.y==-69.5)
        assert(receipt.source.parity=='corner')
        assert(receipt.source.footprint.left_top.x==-13)
        assert(receipt.source.footprint.right_bottom.y==-68)
        assert(receipt.placed.entity_id==42)
        assert(receipt.item_on_ground_before==0)
        assert(receipt.tick==123)
        assert(#place_calls==1)
        assert(place_calls[1].exact==true)
        assert(place_calls[1].prototype=='iron-chest')
        assert(place_calls[1].x==-11.5 and place_calls[1].y==-69.5)
        """
    )


def test_lua_blocked_and_receiver_catch_tiles():
    lua = catch_lua()
    lua.execute(
        """
        local source=make_drill({drop_y=-1.5})
        storage.entity_handles[7]=source
        wide_entities={make_drill({entity_id=20,x=0,y=-3,drop_x=0.5,drop_y=-1.5})}
        local blocked=storage.actions.catch_output(1,7,'iron-chest',0,0)
        assert(blocked.status=='blocked')
        assert(#place_calls==0)
        assert(string.find(blocked.warnings[1],'output tile')~=nil)

        wide_entities={}
        catch_tile_entities={make_chest(9)}
        local served=storage.actions.catch_output(1,7,'iron-chest',0,0)
        assert(served.status=='already_receiver')
        assert(#place_calls==0)
        assert(string.find(served.warnings[1],'accepts items')~=nil)

        catch_tile_entities={make_blocker(11)}
        local covered=storage.actions.catch_output(1,7,'iron-chest',0,0)
        assert(covered.status=='blocked')
        assert(#place_calls==0)
        assert(string.find(covered.warnings[1],'footprint')~=nil)

        catch_tile_entities={{name='item-on-ground',type='item-entity',valid=true,
            stack={name='iron-ore',count=3}}}
        local accumulated=storage.actions.catch_output(1,7,'iron-chest',0,0)
        assert(accumulated.status=='placed')
        assert(accumulated.item_on_ground_before==3)
        assert(accumulated.item_on_ground['iron-ore']==3)
        assert(#place_calls==1)
        """
    )


def test_place_entity_rejection_adds_drop_tile_hint():
    lua = lua_stub(
        """
        storage={utils={},actions={},agent_characters={}}
        game={tick=0}
        defines={inventory={},build_check_type={manual=1}}
        prototypes={entity={}}
        prototypes.entity['steel-chest']={type='container',collision_box={
            left_top={x=-0.35,y=-0.35},right_bottom={x=0.35,y=0.35}}}
        created={}
        hint_candidates={}
        player={position={x=0,y=0},reach_distance=10,
            get_item_count=function(name) return 1 end,
            surface={find_entities_filtered=function(query)
                if query.area then return hint_candidates end
                return {}
            end}}
        storage.agent_characters[1]=player
        storage.utils.ensure_valid_character=function(index)
            return storage.agent_characters[index]
        end
        storage.utils.get_entity_direction=function(entity,direction)
            return direction or 0
        end
        storage.utils.inserter_engine_direction=function(entity,direction)
            return direction or 0
        end
        storage.utils.inserter_direction_report=function(serialized)
            return serialized
        end
        storage.utils.can_place_entity=function() return false end
        storage.utils.spatial_diagnostics=function()
            return {overlapping_entities={{prototype='burner-mining-drill',
                    type='mining-drill',entity_id=7,position={x=0,y=0},distance=1}},
                blocked_by={prototype='burner-mining-drill',type='mining-drill',
                    entity_id=7,position={x=0,y=0},distance=1},
                footprint={left_top={x=0.65,y=-0.35},
                    right_bottom={x=1.35,y=0.35}},
                colliding_tiles={},reason='occupied'}
        end
        """,
        "tools/agent/place_entity/server.lua",
        unpack=True,
    )
    lua.execute(
        """
        hint_candidates={{name='burner-mining-drill',type='mining-drill',valid=true,
            unit_number=7,position={x=0,y=0},
            drop_position={x=1.0,y=0.0}}}
        local result=storage.actions.place_entity(1,'steel-chest',0,1,0,true)
        assert(result.error==true)
        assert(result.reason=='placement_rejected')
        assert(result.diagnostics.blocked_by.prototype=='burner-mining-drill')
        assert(result.drop_tile_hint~=nil)
        assert(result.drop_tile_hint.name=='burner-mining-drill')
        assert(result.drop_tile_hint.catch_tile.x==1.5)
        assert(result.drop_tile_hint.catch_tile.y==0.5)
        assert(string.find(result.drop_tile_hint.message,'output tile')~=nil)
        assert(#created==0)
        """
    )


def test_client_requires_prototype_and_bool_path():
    tool = make_client_tool({"status": "placed"})
    with pytest.raises(ValueError, match="Prototype"):
        tool(drill(), prototype="iron-chest")
    with pytest.raises(ValueError, match="path"):
        tool(drill(), path="yes")


def drill_response(drop_position=None, resources=None, drop_report=None):
    response = {
        "id": 7,
        "name": "burner-mining-drill",
        "position": {"x": 0, "y": 0},
        "direction": 0,
        "health": 300,
        "energy": 0,
        "type": "mining-drill",
        "status": "normal",
        "dimensions": {"width": 2, "height": 2},
        "tile_dimensions": {"tile_width": 2, "tile_height": 2},
        "resources": resources if resources is not None else [],
        "drop_position": (
            drop_position if drop_position is not None else {"x": 0, "y": -1.5}
        ),
    }
    if drop_report is not None:
        response["drop_report"] = drop_report
    return response


def place_response(response):
    tool = PlaceObject.__new__(PlaceObject)
    tool.player_index = 1
    tool.connection = None
    tool.ensure_reachable = lambda target, stop_distance=5.5: Position(x=0, y=0)
    tool.execute = lambda *args: (response, 0.0)
    return tool(Prototype.BurnerMiningDrill, position=Position(x=0, y=0))


def test_drop_tile_and_catch_tile_are_reported():
    entity = place_response(
        drill_response(
            drop_position={"x": -12, "y": -70.5},
            drop_report={"entities": [], "ground_items": 0, "ground_by_item": {}},
        )
    )

    assert entity.drop_tile == {"x": -12.0, "y": -71.0}
    assert entity.catch_tile == {"x": -11.5, "y": -70.5}


def test_no_receiver_at_catch_tile_produces_drop_warning():
    entity = place_response(
        drill_response(
            drop_position={"x": 0, "y": -1.5},
            drop_report={"entities": [], "ground_items": 0, "ground_by_item": {}},
        )
    )

    assert entity.drop_receivers == []
    assert entity.drop_ground_items == 0
    assert "no receiving entity at the catch tile" in entity.drop_warning
    assert "(0.5, -1.5)" in entity.drop_warning


def test_chest_at_catch_tile_suppresses_drop_warning():
    entity = place_response(
        drill_response(
            drop_position={"x": 0, "y": -1.5},
            drop_report={
                "entities": [
                    {
                        "name": "wooden-chest",
                        "type": "container",
                        "position": {"x": 0.5, "y": -1.5},
                        "entity_id": 9,
                        "input_inventory": True,
                    }
                ],
                "ground_items": 0,
                "ground_by_item": {},
            },
        )
    )

    assert entity.drop_receivers == [
        {
            "name": "wooden-chest",
            "position": {"x": 0.5, "y": -1.5},
            "entity_id": 9,
        }
    ]
    assert getattr(entity, "drop_warning", None) is None


def test_belt_counts_as_receiver_but_ground_items_still_warn():
    belt_only = place_response(
        drill_response(
            drop_position={"x": 0, "y": -1.5},
            drop_report={
                "entities": [
                    {
                        "name": "transport-belt",
                        "type": "transport-belt",
                        "position": {"x": 0.5, "y": -1.5},
                        "entity_id": 11,
                        "input_inventory": False,
                    }
                ],
                "ground_items": 0,
                "ground_by_item": {},
            },
        )
    )
    assert getattr(belt_only, "drop_warning", None) is None

    accumulating = place_response(
        drill_response(
            drop_position={"x": 0, "y": -1.5},
            drop_report={
                "entities": [],
                "ground_items": 3,
                "ground_by_item": {"iron-ore": 3},
            },
        )
    )
    assert accumulating.drop_ground_items == 3
    assert accumulating.drop_by_item == {"iron-ore": 3}
    assert "accumulating on the ground" in accumulating.drop_warning


def test_missing_lua_drop_report_keeps_tiles_without_a_warning():
    entity = place_response(drill_response(drop_position={"x": 0, "y": -1.5}))

    assert entity.catch_tile == {"x": 0.5, "y": -1.5}
    assert getattr(entity, "drop_warning", None) is None


def test_mixed_resources_produce_resource_warning():
    entity = place_response(
        drill_response(
            resources=[
                {"name": "iron-ore", "count": 120},
                {"name": "copper-ore", "count": 30},
            ]
        )
    )

    warning = entity.resource_warning
    assert warning["resources"] == {"iron-ore": 120, "copper-ore": 30}
    assert warning["dominant"] == "iron-ore"
    assert warning["total"] == 150
    assert "dominant iron-ore" in warning["message"]


def test_single_resource_has_no_resource_warning():
    entity = place_response(
        drill_response(resources=[{"name": "iron-ore", "count": 120}])
    )

    assert getattr(entity, "resource_warning", None) is None
