import pytest

from tests.actions.lua_stub_helpers import lua_stub

pytestmark = pytest.mark.no_factorio

CHEST = """
prototypes.entity['steel-chest']={type='container',tile_width=1,tile_height=1,
    collision_box={left_top={x=-0.35,y=-0.35},right_bottom={x=0.35,y=0.35}}}
"""

DRILL = """
prototypes.entity['electric-mining-drill']={type='mining-drill',tile_width=3,tile_height=3,
    mining_drill_radius=2.49,
    collision_box={left_top={x=-1.5,y=-1.5},right_bottom={x=1.5,y=1.5}}}
"""


def runtime():
    lua = lua_stub(
        """
        storage={utils={},actions={},agent_characters={}}
        game={tick=0}
        defines={
            events={on_tick=1},
            direction={north=0,east=4,south=8,west=12},
            build_check_type={manual=1},
        }
        script={on_nth_tick=function() end, on_event=function() end}
        prototypes={entity={}}
        player_force={name='player'}
        created={}
        removed={}
        teleports={}
        destroyed={}
        can_place_results={}
        can_place_calls={}
        inventory_count=1
        remove_result=1
        tile_blocks_player=false
        blocked_positions={}
        resource_entities={}
        resource_query_area=nil
        ref_entities={}
        area_characters={}
        buildings={}
        placement_diagnostic=nil

        function can_place_entity(params)
            can_place_calls[#can_place_calls+1]={name=params.name,
                position={x=params.position.x,y=params.position.y},
                direction=params.direction,force=params.force,
                build_check_type=params.build_check_type}
            local result=can_place_results[#can_place_calls]
            if result==nil then result=true end
            return result
        end

        function strict_engine_object(class_name, members)
            return setmetatable(members, {__index=function(_, key)
                error(class_name.." doesn't contain key "..tostring(key), 2)
            end})
        end

        function readonly_direction_entity(members)
            local direction_value=members.direction
            members.direction=nil
            return setmetatable(members, {
                __index=function(t,k)
                    if k=='direction' then return direction_value end
                    return rawget(t,k)
                end,
                __newindex=function(t,k,v)
                    if k=='direction' then return end
                    rawset(t,k,v)
                end,
            })
        end

        function position_key(position)
            return string.format('%.2f,%.2f', position.x, position.y)
        end

        surface=strict_engine_object('LuaSurface', {
            can_place_entity=function(params) return can_place_entity(params) end,
            create_entity=function(params)
                local entity={name=params.name,
                    position={x=params.position.x,y=params.position.y},
                    direction=params.direction,force=params.force,valid=true,
                    unit_number=100+#created}
                created[#created+1]=entity
                return entity
            end,
            find_entities_filtered=function(query)
                if query.invert then return ref_entities end
                if query.type=='resource' then
                    resource_query_area=query.area
                    return resource_entities
                end
                if query.type=='character' then return area_characters end
                if query.name and query.area then return buildings end
                if query.position and query.radius then
                    if blocked_positions[position_key(query.position)] then
                        return {{name='tree-04',type='tree',valid=true,
                            position=query.position,unit_number=99}}
                    end
                    return {}
                end
                return {}
            end,
            get_tile=function(x,y)
                return strict_engine_object('LuaTile', {
                    name='grass',
                    collides_with=function(layer) return tile_blocks_player end,
                })
            end,
        })

        function make_character()
            local character={name='character',type='character',valid=true,unit_number=7,
                position={x=0,y=0},force=player_force,surface=surface,reach_distance=10}
            function character.get_main_inventory()
                return {
                    get_item_count=function(name) return inventory_count end,
                    remove=function(stack) removed[#removed+1]=stack; return remove_result end,
                }
            end
            function character.teleport(position)
                teleports[#teleports+1]={x=position.x,y=position.y}
                character.position={x=position.x,y=position.y}
            end
            return character
        end
        character=make_character()
        storage.agent_characters[1]=character
        """,
        "mods/utils.lua",
        "tools/agent/place_entity_next_to/server.lua",
        "tools/agent/rotate_entity/server.lua",
        unpack=True,
    )
    lua.execute("""
        storage.utils.get_entity_direction=function(entity,direction)
            return direction or 0
        end
        helper_calls={}
        storage.utils.inserter_engine_direction=function(entity_name,direction)
            helper_calls[#helper_calls+1]={name=entity_name,direction=direction}
            local prototype=prototypes.entity[entity_name]
            if prototype and prototype.type=='inserter' then
                return (direction+8)%16
            end
            return direction
        end
        storage.utils.inserter_direction_report=function(serialized,direction)
            return serialized
        end
        storage.utils.serialize_entity=function(entity)
            return {name=entity.name,
                position={x=entity.position.x,y=entity.position.y},
                direction=entity.direction,valid=true}
        end
        storage.utils.attach_connection_report=function(serialized, entity, player)
            return serialized
        end
        storage.utils.format_inventory_for_error=function(player) return 'empty' end
    """)
    return lua


def test_missing_inventory_aborts_before_any_world_check():
    lua = runtime()
    lua.execute(
        CHEST
        + """
        inventory_count=0
        storage.utils.can_place_entity=function()
            error('placement must not be checked without an inventory item')
        end
        local ok, err=pcall(storage.actions.place_entity_next_to, 1, 'steel-chest', 0, 0, 4, 0)
        assert(not ok, 'missing inventory must fail')
        assert(string.find(err, 'inventory') ~= nil)
        assert(#created==0)
        assert(#removed==0)
        """
    )


def test_requested_position_direction_and_feedback_are_returned():
    lua = runtime()
    lua.execute(
        CHEST
        + """
        result=storage.actions.place_entity_next_to(1, 'steel-chest', 0, 0, 4, 0)
        assert(result.error==nil)
        assert(result.position.x==1 and result.position.y==0)
        assert(result.direction==4)
        assert(result.placement_feedback~=nil)
        assert(result.placement_feedback.optimal==true)
        assert(result.placement_feedback.auto_oriented==false)
        assert(string.find(result.placement_feedback.reason, 'requested position') ~= nil)
        assert(#created==1)
        assert(#removed==1)
        assert(removed[1].name=='steel-chest' and removed[1].count==1)
        assert(#can_place_calls==1)
        assert(can_place_calls[1].build_check_type==defines.build_check_type.manual)
        assert(can_place_calls[1].force==player_force)
        """
    )


def test_ground_items_at_target_are_not_destroyed():
    lua = runtime()
    lua.execute(
        CHEST
        + """
        ground_destroyed=0
        local ground={name='item-on-ground',valid=true,unit_number=55,
            destroy=function() ground_destroyed=ground_destroyed+1 end}
        ref_entities={}
        result=storage.actions.place_entity_next_to(1, 'steel-chest', 0, 0, 4, 0)
        assert(result.error==nil)
        assert(#created==1)
        assert(ground_destroyed==0)
        """
    )


def test_character_blocker_steps_aside_with_bounded_teleport():
    lua = runtime()
    lua.execute(
        CHEST
        + """
        can_place_results={false, true}
        storage.utils.spatial_diagnostics=function()
            return {overlapping_entities={{prototype='character',type='character',
                    entity_id=7,position={x=0,y=0},distance=0}},
                footprint={left_top={x=0.65,y=-0.35},right_bottom={x=1.35,y=0.35}},
                colliding_tiles={}}
        end
        result=storage.actions.place_entity_next_to(1, 'steel-chest', 0, 0, 4, 0)
        assert(result.error==nil)
        assert(result.placement_feedback.optimal==false)
        assert(string.find(result.placement_feedback.reason, 'stepped aside') ~= nil)
        assert(#teleports==1)
        assert(#created==1)
        assert(#can_place_calls==2)
        """
    )


def test_character_blocker_without_spatial_diagnostics_still_steps_aside():
    lua = runtime()
    lua.execute(
        CHEST
        + """
        can_place_results={false, true}
        storage.utils.spatial_diagnostics=nil
        area_characters={{name='character',type='character',valid=true,
            unit_number=7,position={x=0,y=0}}}
        result=storage.actions.place_entity_next_to(1, 'steel-chest', 0, 0, 4, 0)
        assert(result.error==nil)
        assert(result.placement_feedback.optimal==false)
        assert(#teleports==1)
        assert(#created==1)
        """
    )


def test_blocked_target_reports_diagnostics_without_creating():
    lua = runtime()
    lua.execute(
        CHEST
        + """
        can_place_results={false}
        storage.utils.spatial_diagnostics=function()
            return {overlapping_entities={{prototype='wooden-chest',type='container',
                    entity_id=9,position={x=1,y=0},distance=0}},
                blocked_by={prototype='wooden-chest',type='container',entity_id=9,
                    position={x=1,y=0},distance=0},
                footprint={left_top={x=0.65,y=-0.35},right_bottom={x=1.35,y=0.35}},
                colliding_tiles={}}
        end
        result=storage.actions.place_entity_next_to(1, 'steel-chest', 0, 0, 4, 0)
        assert(result.error==true)
        assert(result.reason=='placement_rejected')
        assert(result.diagnostics.blocked_by.prototype=='wooden-chest')
        assert(result.position.x==1 and result.position.y==0)
        assert(#created==0)
        assert(#removed==0)
        assert(#teleports==0)
        """
    )


def test_character_plus_terrain_blocker_stays_bounded():
    lua = runtime()
    lua.execute(
        CHEST
        + """
        can_place_results={false}
        tile_blocks_player=true
        storage.utils.spatial_diagnostics=function()
            return {overlapping_entities={{prototype='character',type='character',
                    entity_id=7,position={x=0,y=0},distance=0}},
                footprint={left_top={x=0.65,y=-0.35},right_bottom={x=1.35,y=0.35}},
                colliding_tiles={{name='water',position={x=0,y=0}}}}
        end
        result=storage.actions.place_entity_next_to(1, 'steel-chest', 0, 0, 4, 0)
        assert(result.error==true)
        assert(result.reason=='placement_rejected')
        assert(#teleports==0)
        assert(#created==0)
        """
    )


def test_drill_validation_uses_the_engine_mining_radius():
    lua = runtime()
    lua.execute(
        DRILL
        + """
        resource_entities={{name='iron-ore',type='resource',valid=true,position={x=2,y=0}}}
        result=storage.actions.place_entity_next_to(1, 'electric-mining-drill', 0, 0, 4, 0)
        assert(result.error==nil)
        assert(result.position.x==2 and result.position.y==0)
        assert(resource_query_area~=nil)
        assert(math.abs((resource_query_area[2][1]-resource_query_area[1][1])-4.98)<0.001)
        assert(math.abs(resource_query_area[1][1]-(-0.49))<0.001)
        assert(#created==1)
        """
    )


def test_drill_without_resources_is_rejected_before_creation():
    lua = runtime()
    lua.execute(
        DRILL
        + """
        resource_entities={}
        result=storage.actions.place_entity_next_to(1, 'electric-mining-drill', 0, 0, 4, 0)
        assert(result.error==true)
        assert(result.reason=='no_minable_resources')
        assert(#created==0)
        assert(#removed==0)
        """
    )


INSERTER = """
prototypes.entity['burner-inserter']={type='inserter',tile_width=1,tile_height=1,
    collision_box={left_top={x=-0.5,y=-0.5},right_bottom={x=0.5,y=0.5}}}
"""


def test_place_entity_next_to_inverts_inserter_engine_direction():
    lua = runtime()
    lua.execute(
        INSERTER
        + """
        storage.utils.can_place_entity=function() return true end
        result=storage.actions.place_entity_next_to(1, 'burner-inserter', 0, 0, 4, 0)
        assert(result.error==nil)
        assert(#created==1)
        assert(created[1].direction==12)
        assert(created[1].position.x==1 and created[1].position.y==0)
        assert(helper_calls[1].name=='burner-inserter')
        assert(helper_calls[1].direction==4)
        """
    )


def test_rotate_entity_inverts_inserter_engine_direction():
    lua = runtime()
    lua.execute(
        INSERTER
        + """
        building={name='burner-inserter',type='inserter',valid=true,unit_number=8,
            position={x=10.5,y=10.5},direction=0}
        buildings={building}
        result=storage.actions.rotate_entity(1, 10.5, 10.5, 4, 'burner-inserter')
        assert(building.direction==12)
        assert(helper_calls[1].name=='burner-inserter')
        assert(helper_calls[1].direction==4)
        """
    )


def test_non_inserters_keep_engine_direction_at_the_boundary():
    lua = runtime()
    lua.execute(
        """
        building={name='transport-belt',type='transport-belt',valid=true,unit_number=9,
            position={x=10.5,y=10.5},direction=0}
        buildings={building}
        storage.actions.rotate_entity(1, 10.5, 10.5, 8, 'transport-belt')
        assert(building.direction==8)
        assert(helper_calls[1].direction==8)
        """
    )


def test_rotatable_assembler_uses_engine_rotate_without_moving():
    lua = runtime()
    lua.execute("""
        rotations=0
        building={name='assembling-machine-2',type='assembling-machine',valid=true,
            unit_number=42,position={x=10.5,y=10.5},direction=0}
        function building.rotate()
            rotations=rotations+1
            building.direction=(building.direction+4)%16
            return true
        end
        buildings={building}
        result=storage.actions.rotate_entity(1, 10.5, 10.5, 4, 'assembling-machine-2')
        assert(result.direction==4)
        assert(rotations==1)
        assert(#created==0)
        assert(#teleports==0)
        assert(building.position.x==10.5 and building.position.y==10.5)
        """)


def test_unrotatable_assembler_reports_without_destroying():
    lua = runtime()
    lua.execute("""
        building=readonly_direction_entity({name='assembling-machine-2',
            type='assembling-machine',valid=true,unit_number=42,
            position={x=10.5,y=10.5},direction=0})
        function building.rotate() return false end
        function building.destroy() destroyed[#destroyed+1]=building end
        buildings={building}
        local ok, err=pcall(storage.actions.rotate_entity, 1, 10.5, 10.5, 4, 'assembling-machine-2')
        assert(not ok)
        assert(string.find(err, 'fluid recipe') ~= nil)
        assert(building.valid==true)
        assert(#destroyed==0)
        assert(#created==0)
        assert(#teleports==0)
        """)


def test_non_assembler_direction_change_keeps_position():
    lua = runtime()
    lua.execute("""
        building={name='transport-belt',type='transport-belt',valid=true,unit_number=5,
            position={x=10.5,y=10.5},direction=0,
            rotate=function() return false end}
        buildings={building}
        result=storage.actions.rotate_entity(1, 10.5, 10.5, 8, 'transport-belt')
        assert(result.direction==8)
        assert(building.position.x==10.5 and building.position.y==10.5)
        assert(#teleports==0)
        """)


def test_escape_returns_nil_when_every_candidate_is_blocked():
    lua = runtime()
    lua.execute("""
        tile_blocks_player=true
        local escaped=storage.utils.escape_character_to_free_tile(
            storage.agent_characters[1], nil, nil, nil)
        assert(escaped==nil)
        assert(#teleports==0)
        """)


def test_escape_uses_diagonal_candidates_deterministically():
    lua = runtime()
    lua.execute("""
        blocked_positions['1.00,0.00']=true
        blocked_positions['-1.00,0.00']=true
        blocked_positions['0.00,1.00']=true
        blocked_positions['0.00,-1.00']=true
        blocked_positions['2.00,0.00']=true
        blocked_positions['-2.00,0.00']=true
        blocked_positions['0.00,2.00']=true
        blocked_positions['0.00,-2.00']=true
        local first=storage.utils.escape_character_to_free_tile(
            storage.agent_characters[1], nil, nil, nil)
        assert(first~=nil)
        assert(math.abs(teleports[1].x)==1 and math.abs(teleports[1].y)==1)
        local chosen_x, chosen_y=teleports[1].x, teleports[1].y
        character.position={x=0,y=0}
        storage.utils.escape_character_to_free_tile(storage.agent_characters[1], nil, nil, nil)
        assert(teleports[2].x==chosen_x and teleports[2].y==chosen_y)
        assert(#teleports==2)
        """)


def test_escape_never_lands_inside_the_avoid_box():
    lua = runtime()
    lua.execute("""
        local avoid_box={left_top={x=-1.5,y=-1.5},right_bottom={x=1.5,y=1.5}}
        local escaped=storage.utils.escape_character_to_free_tile(
            storage.agent_characters[1], avoid_box, nil, nil)
        assert(escaped~=nil)
        assert(math.abs(teleports[1].x)>1.9 or math.abs(teleports[1].y)>1.9)
        assert(#teleports==1)
        """)
