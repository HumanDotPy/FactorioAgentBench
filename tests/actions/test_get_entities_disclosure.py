from types import SimpleNamespace

import pytest

from fle.env.tools.agent.get_entities.client import EntityList, GetEntities
from tests.actions.lua_stub_helpers import lua_stub, stub_client

pytestmark = pytest.mark.no_factorio


def server_runtime():
    return lua_stub(
        """
        storage={actions={},utils={}}
        player_force={name='player'}
        enemy_force={name='enemy'}
        neutral_force={name='neutral'}
        character={name='character',type='character',force=player_force,
            position={x=0,y=0}}
        storage.utils.ensure_valid_character=function() return character end
        storage.utils.serialize_entity=function(entity)
            return {name=entity.name, type=entity.type}
        end
        helpers={json_to_table=function(text) return {} end}
        ground_results={
            {name='item-on-ground', type='item-entity', valid=true,
                position={x=4.5,y=4.5},
                stack={valid_for_read=true,name='iron-ore',count=7}},
            {name='item-on-ground', type='item-entity', valid=true,
                position={x=5.5,y=5.5},
                stack={valid_for_read=true,name='copper-ore',count=3}},
        }
        surface={find_entities_filtered=function(query)
            assert(query.area ~= nil)
            if query.type=='item-entity' then return ground_results end
            return {
                {name='stone-furnace', type='furnace', force=player_force, valid=true,
                    position={x=1,y=1},
                    bounding_box={left_top={x=0,y=0},right_bottom={x=2,y=2}}},
                {name='electric-mining-drill', type='mining-drill', force=player_force,
                    valid=true, position={x=0.5,y=0.5},
                    bounding_box={left_top={x=-1,y=-1},right_bottom={x=2,y=2}}},
                {name='iron-ore', type='item-entity', force=player_force, valid=true,
                    position={x=3,y=3}},
                {name='character', type='character', force=player_force, valid=true},
                {name='gun-turret', type='ammo-turret', force=enemy_force, valid=true},
                {name='tree-01', type='tree', force=neutral_force, valid=true},
                {name='broken', type='furnace', force=player_force, valid=false},
            }
        end}
        player={position={x=0,y=0},force=player_force,surface=surface}
        character.surface=surface
        """,
        "tools/agent/get_entities/server.lua",
    )


def test_server_reports_ground_items_footprint_and_disclosure():
    lua = server_runtime()
    result = lua.execute("""
        local response=storage.actions.get_entities(1,10,'[]',0,0)
        assert(#response.entities==2)
        assert(response.other_forces==2)
        assert(#response.other_force_names==2)
        assert(response.other_force_names[1]=='enemy')
        assert(response.other_force_names[2]=='neutral')
        assert(response.characters_skipped==1)
        assert(response.skipped==1)
        assert(response.ground_item_stacks==2)
        assert(response.ground_item_totals['iron-ore']==7)
        assert(response.ground_item_totals['copper-ore']==3)
        assert(response.ground_items_truncated==false)
        assert(#response.ground_items==2)
        assert(response.ground_items[1].name=='iron-ore')
        assert(response.ground_items[1].count==7)
        assert(response.ground_items[1].position.x==4.5)
        local furnace, drill
        for _,entity in ipairs(response.entities) do
            if entity.name=='stone-furnace' then furnace=entity end
            if entity.name=='electric-mining-drill' then drill=entity end
        end
        assert(furnace.tile_size.width==2 and furnace.tile_size.height==2)
        assert(furnace.center_parity.x==0 and furnace.center_parity.y==0)
        assert(furnace.snapped_center.x==1.5 and furnace.snapped_center.y==1.5)
        assert(drill.tile_size.width==3 and drill.tile_size.height==3)
        assert(drill.center_parity.x==1 and drill.center_parity.y==1)
        assert(drill.snapped_center.x==0.5 and drill.snapped_center.y==0.5)
        return 'ok'
    """)
    assert result == "ok"


def _client(response):
    tool = stub_client(GetEntities, response=response)
    tool.name = "get_entities"
    tool.game_state = SimpleNamespace(_program_runtime=None)
    return tool


def _record(name, position, **overrides):
    record = {
        "name": name,
        "type": "assembling-machine",
        "position": {"x": position, "y": position},
        "direction": 0,
        "status": "working",
        "energy": 0,
        "health": 100,
        "dimensions": {"width": 1, "height": 1},
        "tile_dimensions": {"tile_width": 1, "tile_height": 1},
    }
    record.update(overrides)
    return record


def test_client_exposes_ground_items_without_double_counting():
    response = {
        "entities": [
            _record(
                "assembling-machine-1",
                1,
                inventory=[{"iron-plate": 2}, {"copper-plate": 1}],
                tile_size={"width": 3, "height": 3},
                center_parity={"x": 1, "y": 1},
                snapped_center={"x": 1.5, "y": 1.5},
            ),
            {"name": "unknown-thing", "position": {"x": 2, "y": 2}},
        ],
        "ground_items": [
            {"name": "iron-ore", "count": 7, "position": {"x": -12.5, "y": -69.5}}
        ],
        "ground_item_stacks": 2,
        "ground_item_totals": {"iron-ore": 9},
        "ground_items_truncated": False,
        "other_forces": 3,
        "other_force_names": ["enemy"],
        "characters_skipped": 2,
        "skipped": 1,
    }
    result = _client(response)(set(), radius=10)
    assert isinstance(result, EntityList)
    assert result.other_forces == 3
    assert result.characters_skipped == 2
    assert result.server_skipped == 1
    assert result.unmatched == 1
    assert len(result) == 1
    machine = result[0]
    assert machine.inventory["iron-plate"] == 2
    assert machine.inventory["copper-plate"] == 1
    assert machine.tile_size == {"width": 3, "height": 3}
    assert machine.center_parity == {"x": 1, "y": 1}
    assert result.ground_item_count == 2
    assert result.ground_item_totals == {"iron-ore": 9}
    assert result.ground_items[0].name == "iron-ore"
    assert result.ground_items[0].count == 7
    assert result.ground_items[0].position.x == -12.5
    payload = result.as_dict()
    assert payload["ground_item_count"] == 2
    assert payload["ground_items"][0]["name"] == "iron-ore"
    assert "other_forces=3" in repr(result)

    legacy = _client([_record("assembling-machine-1", 1)])(set(), radius=10)
    assert len(legacy) == 1
    assert legacy.ground_items == []
    assert legacy.ground_item_count == 0
