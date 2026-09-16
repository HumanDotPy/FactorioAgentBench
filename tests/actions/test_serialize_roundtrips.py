import pytest

from tests.actions.lua_stub_helpers import lua_stub, load_env

pytestmark = pytest.mark.no_factorio


def runtime():
    return lua_stub(
        """
        storage={actions={},utils={},agent_characters={}}
        defines={direction={north=0,east=4,south=8,west=12},
            events={on_tick=1},
            entity_status={normal=1,working=2,full_output=3,
                no_minable_resources=4,preparing_rocket_for_launch=5},
            inventory={item_main=1,chest=2,fuel=3}}
        prototypes={item={coal={name='coal'}},quality={normal={name='normal'},rare={name='rare'}},
            entity={}}
        helpers={table_to_json=function(t)
            return (t.n or '')..':'..tostring(t.c)..':'..tostring(t.q)..':'..tostring(t.f)
        end}
        script={on_nth_tick=function() end,on_event=function() end}
        game={surfaces={{get_tile=function() return {name='grass-1'} end}}}
        """,
        "mods/initialise.lua",
        "mods/utils.lua",
        "mods/connection_points.lua",
        "mods/serialize.lua",
    )


def test_item_stack_quality_roundtrip():
    lua = runtime()
    result = lua.execute(
        """
        local serialized={}
        local slot={is_blueprint=false,is_blueprint_book=false,is_upgrade_item=false,
            is_deconstruction_item=false,is_item_with_tags=false,is_item_with_label=false,
            name='iron-plate',count=5,health=10,type='item',quality={name='rare'}}
        storage.utils.serialize_item_stack(slot,serialized)
        assert(serialized.n=='iron-plate' and serialized.c==5)
        assert(serialized.q=='rare')
        local captured=nil
        local target={set_stack=function(stack) captured=stack; return true end}
        storage.utils.deserialize_item_stack(target,serialized)
        assert(captured.quality=='rare')
        local normal={}
        local plain={is_blueprint=false,is_blueprint_book=false,is_upgrade_item=false,
            is_deconstruction_item=false,is_item_with_tags=false,is_item_with_label=false,
            name='iron-plate',count=1,health=10,type='item',quality={name='normal'}}
        storage.utils.serialize_item_stack(plain,normal)
        assert(normal.q==nil)
        return 'ok'
        """
    )
    assert result == "ok"


def test_inventory_bar_and_sparse_positions_roundtrip():
    lua = runtime()
    result = lua.execute(
        """
        local function slot(name,count)
            return {valid_for_read=true,name=name,count=count,health=10,type='item'}
        end
        local inventory={}
        inventory[1]=slot('iron-plate',3)
        inventory[2]=slot('iron-plate',3)
        inventory[4]=slot('copper-plate',1)
        inventory.supports_bar=function() return true end
        inventory.get_bar=function() return 2 end
        inventory.supports_filters=function() return false end
        local serialized=storage.utils.serialize_inventory(inventory)
        assert(serialized.b==2)
        assert(#serialized.i==2)
        assert(serialized.i[1].n=='iron-plate' and serialized.i[1].r==1)
        assert(serialized.i[2].s==4 and serialized.i[2].n=='copper-plate')
        local totals={}
        local function target(i)
            return {set_stack=function(stack)
                totals[stack.name]=(totals[stack.name] or 0)+stack.count
                return true
            end}
        end
        local restored={}
        restored[1]=target(1)
        restored[2]=target(2)
        restored[4]=target(4)
        restored.supports_bar=function() return true end
        restored.set_bar=function(bar) totals.bar=bar end
        storage.utils.deserialize_inventory(restored,serialized)
        assert(totals.bar==2)
        assert(totals['iron-plate']==6)
        assert(totals['copper-plate']==1)
        return 'ok'
        """
    )
    assert result == "ok"


def test_equipment_grid_quality_and_burner_roundtrip():
    lua = runtime()
    result = lua.execute(
        """
        local function inventory()
            return {supports_bar=function() return false end,
                supports_filters=function() return false end}
        end
        local equipment={name='burner-generator-equipment',position={x=0,y=0},
            shield=0,energy=0,quality={name='rare'},
            burner={inventory=inventory(),burnt_result_inventory=inventory(),
                currently_burning={name='coal'},remaining_burning_fuel=42}}
        local grid={width=1,height=1,get=function(pos) return equipment end}
        local serialized=storage.utils.serialize_equipment_grid(grid)
        assert(#serialized==1)
        assert(serialized[1].q=='rare')
        assert(serialized[1].b=='coal')
        assert(serialized[1].f==42)
        assert(serialized[1].i and serialized[1].r)
        local captured={}
        local restored_equipment={burner={}}
        local restored_grid={clear=function() end,put=function(def)
            captured.quality=def.quality
            captured.name=def.name
            return restored_equipment
        end}
        storage.utils.deserialize_equipment_grid(restored_grid,serialized)
        assert(captured.quality=='rare')
        assert(captured.name=='burner-generator-equipment')
        assert(restored_equipment.burner.currently_burning==prototypes.item['coal'])
        assert(restored_equipment.burner.remaining_burning_fuel==42)
        return 'ok'
        """
    )
    assert result == "ok"


def test_belt_inventory_merge_uses_each_line_table():
    lua = runtime()
    result = lua.execute(
        """
        storage.utils.get_issues=function() return {} end
        storage.utils.get_contents_compat=function(line) return line.contents end
        prototypes.entity['transport-belt']={
            collision_box={left_top={x=-0.5,y=-0.5},right_bottom={x=0.5,y=0.5}},
            tile_width=1,tile_height=1}
        local line1={contents={['iron-plate']=3},can_insert_at_back=function() return true end}
        local line2={contents={['copper-plate']=2},can_insert_at_back=function() return true end}
        local entity={valid=true,unit_number=7,name='transport-belt',type='transport-belt',
            direction=defines.direction.north,position={x=0,y=0},health=100,energy=0,
            status=defines.entity_status.working,
            belt_neighbours={inputs={},outputs={}},
            get_transport_line=function(index)
                if index==1 then return line1 else return line2 end
            end,
            get_inventory=function() return nil end,
            surface={find_entities_filtered=function() return {} end}}
        local serialized=storage.utils.serialize_entity(entity)
        assert(serialized.inventory.left['iron-plate']==3)
        assert(serialized.inventory.right['copper-plate']==2)
        assert(serialized.inventory.left['copper-plate']==nil)
        assert(serialized.inventory.right['iron-plate']==nil)
        assert(serialized.direction==defines.direction.north)
        assert(serialized.status=='"working"')
        return 'ok'
        """
    )
    assert result == "ok"


def test_fluid_machine_connection_points_are_serialized():
    lua = runtime()
    result = lua.execute(
        """
        storage.utils.get_issues=function() return {} end
        prototypes.entity['pump']={type='pump',tile_width=1,tile_height=2,
            collision_box={left_top={x=-1,y=-0.5},right_bottom={x=1,y=0.5}}}
        prototypes.entity['pipe-to-ground']={type='pipe-to-ground',
            tile_width=1,tile_height=1,
            collision_box={left_top={x=-0.5,y=-0.5},right_bottom={x=0.5,y=0.5}}}
        prototypes.entity['heat-exchanger']={type='boiler',tile_width=3,
            tile_height=2,
            collision_box={left_top={x=-1.5,y=-1},right_bottom={x=1.5,y=1}}}
        local function base(name, entity_type)
            return {valid=true,unit_number=1,name=name,type=entity_type,
                position={x=10,y=10},direction=defines.direction.north,
                health=100,energy=0,status=defines.entity_status.working,
                get_inventory=function() return nil end,
                surface={find_entities_filtered=function() return {} end,
                    get_tile=function() return {name='grass-1'} end}}
        end
        local pump = base('pump','pump')
        pump.fluidbox={get_connections=function(index)
            if index==1 then return {{position={x=10,y=8.5}}} end
            return {{position={x=10,y=11.5}}}
        end}
        local serialized_pump=storage.utils.serialize_entity(pump)
        assert(serialized_pump.input_position.y==8.5)
        assert(serialized_pump.output_position.y==11.5)
        assert(#serialized_pump.connection_points==2)
        assert(serialized_pump.connection_points[1].y==8.5)

        local pipe = base('pipe-to-ground','pipe-to-ground')
        pipe.fluidbox={get_pipe_connections=function()
                return {{position={x=10,y=9}}}
            end,
            get_fluid_segment_contents=function() return nil end,
            get_fluid_segment_id=function() return 0 end}
        local serialized_pipe=storage.utils.serialize_entity(pipe)
        assert(serialized_pipe.connections[1].y==9)
        assert(#serialized_pipe.connection_points==1)
        assert(serialized_pipe.connection_points[1].y==9)

        local exchanger = base('heat-exchanger','boiler')
        exchanger.fluidbox={}
        local serialized_exchanger=storage.utils.serialize_entity(exchanger)
        assert(serialized_exchanger.steam_output_point.y==8.5)
        return #serialized_exchanger.connection_points
        """
    )
    assert result == 3


def test_get_closest_entity_radius_is_caller_controlled():
    lua = runtime()
    result = lua.execute(
        """
        local queries={}
        local player={force='player',surface={find_entities_filtered=function(q)
            queries[#queries+1]=q
            return {}
        end}}
        storage.utils.get_closest_entity(player,{x=0,y=0})
        storage.utils.get_closest_entity(player,{x=0,y=0},1)
        assert(queries[1].radius==5)
        assert(queries[2].radius==1)
        return 'ok'
        """
    )
    assert result == "ok"


def test_serialize_recipe_keeps_numeric_types():
    lua = runtime()
    result = lua.execute(
        """
        local recipe={name='iron-gear-wheel',category='crafting',enabled=true,energy=0.5,
            ingredients={{name='iron-plate',type='item',amount=2}},
            products={{name='iron-gear-wheel',type='item',amount=1,probability=1}}}
        local serialized=storage.utils.serialize_recipe(recipe)
        assert(type(serialized.energy)=='number' and serialized.energy==0.5)
        assert(type(serialized.ingredients[1].amount)=='number')
        assert(serialized.ingredients[1].amount==2)
        assert(type(serialized.products[1].amount)=='number')
        assert(type(serialized.products[1].probability)=='number')
        return 'ok'
        """
    )
    assert result == "ok"


def test_get_contents_compat_keeps_quality_distinct():
    lua = runtime()
    result = lua.execute(
        """
        local inventory={get_contents=function()
            return {
                {name='iron-plate',count=3,quality='normal'},
                {name='iron-plate',count=2,quality='rare'},
                {name='copper-plate',count=1,quality='normal'},
            }
        end}
        local contents=storage.utils.get_contents_compat(inventory)
        assert(contents['iron-plate']==3)
        assert(contents['iron-plate@rare']==2)
        assert(contents['copper-plate']==1)
        return 'ok'
        """
    )
    assert result == "ok"


def test_serialized_status_matches_python_from_string():
    from fle.env.entities import EntityStatus

    lua = runtime()
    quoted = lua.execute(
        "return storage.utils.entity_status_names(defines.entity_status.no_minable_resources)"
    )
    assert quoted == '"no_minable_resources"'
    assert EntityStatus.from_string(quoted) is EntityStatus.NO_MINABLE_RESOURCES
    assert EntityStatus.from_string("normal") is EntityStatus.NORMAL
    assert EntityStatus.from_string(None) is None


def test_unknown_status_is_not_reported_as_normal():
    lua = runtime()
    assert lua.eval("storage.utils.entity_status_names(nil)") == '"unknown"'
    assert lua.eval("storage.utils.entity_status_names(9999)") == '"unknown"'
    assert (
        lua.eval("storage.utils.entity_status_names(defines.entity_status.working)")
        == '"working"'
    )


def test_shared_round_is_used_without_global_math_round():
    lua = runtime()
    assert lua.eval("math.round") is None
    assert lua.eval("storage.utils.round(1.4)") == 1
    assert lua.eval("storage.utils.round(1.6)") == 2
    assert lua.eval("storage.utils.round(-1.6)") == -2
    assert lua.eval("storage.utils.round(3)") == 3
    assert lua.eval("storage.utils.round(0.25 * 2) / 2") == 0.5


def test_connect_entities_defines_no_global_math_round():
    lua = lua_stub(
        """
        storage={actions={},utils={},agent_characters={}}
        defines={direction={north=0,east=4,south=8,west=12},events={on_tick=1}}
        script={on_nth_tick=function() end,on_event=function() end}
        """,
        "mods/initialise.lua",
        "mods/utils.lua",
        "tools/agent/connect_entities/server.lua",
    )
    assert lua.eval("math.round") is None
    assert lua.eval("storage.actions.connect_entities ~= nil") is True


def test_electric_pole_flow_rate_is_a_rate_not_cumulative_energy():
    lua = runtime()
    result = lua.execute(
        """
        defines.flow_precision_index={one_minute=60}
        storage.utils.get_issues=function() return {} end
        prototypes.entity['small-electric-pole']={
            collision_box={left_top={x=-0.5,y=-0.5},right_bottom={x=0.5,y=0.5}},
            tile_width=1,tile_height=1}
        local stats={input_counts={['solar-panel']=123456,['steam-engine']=5000},
            output_counts={},
            get_flow_count=function(params)
                if params.name=='solar-panel' then return 30 end
                return 20
            end}
        local pole={valid=true,unit_number=9,name='small-electric-pole',
            type='electric-pole',position={x=0,y=0},direction=defines.direction.north,
            health=100,energy=0,status=defines.entity_status.working,
            electric_network_statistics=stats,
            get_inventory=function() return nil end,
            surface={find_entities_filtered=function() return {} end,
                get_tile=function() return {name='grass-1'} end}}
        local serialized=storage.utils.serialize_entity(pole)
        assert(serialized.flow_rate==50)
        return serialized.flow_rate
        """
    )
    assert result == 50


def test_save_entity_state_shares_canonical_status_and_raw_direction():
    lua = runtime()
    load_env(lua, "tools/admin/save_entity_state/server.lua")
    result = lua.execute(
        """
        local prototype={has_flag=function() return true end,
            collision_box={left_top={x=-0.5,y=-0.5},right_bottom={x=0.5,y=0.5}},
            tile_width=1,tile_height=1}
        local entity={name='wooden-chest',type='container',unit_number=3,valid=true,
            position={x=1.5,y=2},direction=12,health=50,energy=0,active=true,
            status=defines.entity_status.working,
            to_be_deconstructed=function() return false end,
            to_be_upgraded=function() return false end,
            get_inventory=function() return nil end,
            bounding_box=prototype.collision_box,
            prototype=prototype}
        local surface={find_entities_filtered=function(query) return {entity} end}
        storage.agent_characters[1]={surface=surface,force={name='player'}}
        storage.utils.get_issues=function() return {} end
        local states=storage.actions.save_entity_state(1,10,false,false,false)
        assert(#states==1)
        assert(states[1].status=='"working"')
        assert(states[1].direction==12)
        return 'ok'
        """
    )
    assert result == "ok"
