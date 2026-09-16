import pytest

from tests.actions.lua_stub_helpers import lua_stub

pytestmark = pytest.mark.no_factorio


def runtime():
    return lua_stub(
        """
        storage={actions={},utils={},agent_characters={}}
        defines={entity_status={working=1,no_fuel=2,waiting_for_source_items=3,
                normal=4,waiting_for_space_in_destination=5},
            inventory={crafter_input=1,furnace_source=2,chest=3,fuel=4}}
        storage.utils.get_contents_compat=function(inventory)
            return inventory.contents
        end
        force={name='player'}
        position_results={}
        resource_results={}
        entity_results={}
        surface={find_entities_filtered=function(query)
            if query.position then
                return position_results[query.position.x] or {}
            end
            if query.type=='resource' then return resource_results end
            assert(query.force==force)
            return entity_results
        end}
        chest_inventory={contents={coal=3}}
        position_results[4]={{name='iron-chest', valid=true,
            get_inventory=function(kind) return chest_inventory end}}
        position_results[2]={}
        position_results[6]={}
        resource_results={{name='iron-ore', amount=50}}
        entity_results={
            {name='electric-mining-drill', type='mining-drill', status=5, valid=true,
                unit_number=1, position={x=1,y=1}, drop_position={x=2,y=2},
                surface=surface,
                bounding_box={left_top={x=-0.5,y=-0.5},right_bottom={x=2.5,y=2.5}}},
            {name='burner-inserter', type='inserter', status=3, valid=true,
                unit_number=2, position={x=5,y=0}, pickup_position={x=4,y=0},
                drop_position={x=6,y=0},
                bounding_box={left_top={x=4.5,y=-0.5},right_bottom={x=5.5,y=0.5}}},
            {name='burner-inserter', type='inserter', status=1, valid=true,
                unit_number=5, position={x=5,y=0}, drop_position={x=6,y=0},
                bounding_box={left_top={x=4.5,y=-0.5},right_bottom={x=5.5,y=0.5}}},
            {name='electric-mining-drill', type='mining-drill', status=1, valid=true,
                unit_number=9, position={x=1,y=1}, drop_position={x=2,y=2},
                surface=surface,
                bounding_box={left_top={x=-0.5,y=-0.5},right_bottom={x=2.5,y=2.5}}},
            {name='item-on-ground', type='item-entity', status=nil, valid=true,
                position={x=0,y=0},
                stack={valid_for_read=true,name='iron-ore',count=7}},
            {name='item-on-ground', type='item-entity', status=nil, valid=true,
                position={x=1,y=0},
                stack={valid_for_read=true,name='iron-ore',count=2}},
            {name='item-on-ground', type='item-entity', status=nil, valid=true,
                position={x=3,y=3},
                stack={valid_for_read=true,name='coal',count=5}},
            {name='stone-furnace', type='furnace', status=99, valid=true,
                unit_number=4, position={x=8,y=8},
                bounding_box={left_top={x=7,y=7},right_bottom={x=9,y=9}}},
        }
        storage.agent_characters[1]={valid=true,force=force,surface=surface}
        """,
        "tools/admin/entity_census/server.lua",
    )


def test_census_reports_stalls_ground_items_drop_targets_and_footprints():
    lua = runtime()
    result = lua.execute("""
        local result=storage.actions.entity_census(1)
        assert(result.total==8)
        assert(result.stalls.by_status['waiting_for_space_in_destination']==1)
        assert(result.stalls.by_status['waiting_for_source_items']==1)
        assert(result.stalls.buffer_full==1)
        assert(result.stalls.by_product['iron-ore']==1)
        assert(result.census['stone-furnace']['unknown']==1)

        assert(result.ground_items['iron-ore']==9)
        assert(result.ground_items['coal']==5)
        assert(result.ground_item_stacks==3)
        assert(#result.ground_item_positions==3)
        assert(result.ground_items_truncated==false)
        local total_ground=0
        for _,entry in ipairs(result.ground_item_positions) do
            total_ground=total_ground+entry.count
        end
        assert(total_ground==14)

        assert(result.missing_drop_target_count==2)
        assert(#result.missing_drop_targets==2)
        local drill_missing, inserter_missing
        for _,entry in ipairs(result.missing_drop_targets) do
            if entry.type=='mining-drill' then drill_missing=entry end
            if entry.type=='inserter' then inserter_missing=entry end
        end
        assert(drill_missing.drop_position.x==2)
        assert(drill_missing.tile_size.width==3)
        assert(drill_missing.center_parity.x==0)
        assert(inserter_missing.drop_position.x==6)

        local drill, inserter
        for _,detail in ipairs(result.stalls.detail) do
            if detail.type=='mining-drill' then drill=detail end
            if detail.type=='inserter' then inserter=detail end
        end
        assert(drill.product=='iron-ore')
        assert(drill.drop_empty==true)
        assert(drill.tile_size.width==3)
        assert(drill.center_parity.x==0)
        assert(drill.snapped_center.x==1.5)
        assert(inserter.pickup_target=='iron-chest')
        assert(inserter.source_inventory['coal']==3)
        assert(inserter.drop_position.x==6)
        assert(inserter.tile_size.width==1)
        return 'ok'
    """)
    assert result == "ok"


def test_census_without_character_returns_empty():
    lua = runtime()
    result = lua.execute("""
        storage.agent_characters[1]=nil
        local result=storage.actions.entity_census(1)
        assert(result.total==0)
        return 'ok'
    """)
    assert result == "ok"
