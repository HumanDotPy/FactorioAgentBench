from pathlib import Path
from unittest.mock import Mock, call

import pytest
from lupa.lua54 import LuaError, LuaRuntime

from fle.env.entities import Position
from fle.env.instance import NONE
from fle.env.tools.agent.move_to.client import MoveTo

pytestmark = pytest.mark.no_factorio

CHEST_PROTOTYPE = """
        prototypes.entity['steel-chest']={
            type='container',
            collision_box={left_top={x=-0.35,y=-0.35},right_bottom={x=0.35,y=0.35}},
            collision_mask={layers={player=true}}}
"""


def runtime():
    # Engine-fidelity mocks: real LuaObjects raise when a member does not exist
    # ("LuaTile doesn't contain key walkable." on 2.0.77), while plain Lua
    # tables silently return nil. The old permissive mock supplied `walkable`
    # and `collides_with` keys on the tile, which masked the crash that the
    # walking-queue nth-tick handler hit in the escape helper.
    lua = LuaRuntime()
    lua.execute("""
        storage={actions={},agent_characters={},utils={}}
        script={on_event=function()end,on_nth_tick=function()end}
        defines={
            events={on_tick=1},
            direction={north=0,east=4,south=8,west=12},
            inventory={character_main=1},
            build_check_type={manual=0},
        }
        game={tick=0,surfaces={}}
        prototypes={entity={}}
        placeable=nil
        placeable_calls=0
        blocker_entities={}
        blocked_positions={}
        tile_blocks_player=false
        teleports={}
        created_params=nil
        removed_item=nil
        function strict_engine_object(class_name, members)
            return setmetatable(members, {__index=function(_, key)
                error(class_name.." doesn't contain key "..tostring(key), 2)
            end})
        end
        character={valid=true,unit_number=14,position={x=0,y=0},force='player',
            reach_distance=10,walking_state={walking=false},
            prototype={collision_box={left_top={x=-0.35,y=-0.35},
                right_bottom={x=0.35,y=0.35}}}}
        function character.get_item_count(name) return 5 end
        function character.remove_item(params) removed_item=params end
        function character.teleport(position)
            teleports[#teleports+1]={from={x=character.position.x,y=character.position.y},
                to={x=position.x,y=position.y}}
            character.position={x=position.x,y=position.y}
        end
        function can_place_now()
            placeable_calls=placeable_calls+1
            if placeable~=nil then return placeable end
            return character.position.x~=0 or character.position.y~=0
        end
        function probe_blocked(position)
            return blocked_positions[string.format('%.2f,%.2f',position.x,position.y)]==true
        end
        surface=strict_engine_object('LuaSurface', {
            can_place_entity=function(params) return can_place_now() end,
            create_entity=function(params)
                created_params=params
                return {name=params.name,position=params.position,
                    direction=params.direction,unit_number=1,valid=true}
            end,
            find_entities_filtered=function(query)
                if query.area~=nil then
                    if #blocker_entities>0 then return blocker_entities end
                    local cx=(query.area[1][1]+query.area[2][1])/2
                    local cy=(query.area[1][2]+query.area[2][2])/2
                    if probe_blocked({x=cx,y=cy}) then
                        return {{name='tree-04',type='tree',valid=true,
                            position={x=cx,y=cy},unit_number=99}}
                    end
                    return {}
                end
                if query.position~=nil and query.radius~=nil then
                    if probe_blocked(query.position) then
                        return {{name='tree-04',type='tree',valid=true,
                            position=query.position,unit_number=99}}
                    end
                    return {}
                end
                return {}
            end,
            count_tiles_filtered=function(query)
                assert(query.area~=nil,'count_tiles_filtered requires an area')
                assert(query.collision_mask=='player',
                    'walkability must query the player collision layer')
                if tile_blocks_player then return 1 end
                return 0
            end,
            get_tile=function(x,y)
                return strict_engine_object('LuaTile', {
                    name='grass',
                    position={x=0,y=0},
                    prototype={name='grass'},
                    valid=true,
                    to_be_deconstructed=false,
                    collides_with=function(layer)
                        assert(layer=='player',
                            'collides_with takes a 2.0 collision layer name')
                        return tile_blocks_player
                    end,
                })
            end,
        })
        character.surface=surface
        storage.agent_characters[1]=character
        storage.utils.get_entity_direction=function(entity,direction)
            return direction or 0
        end
        storage.utils.inserter_engine_direction=function(entity,direction)
            return direction or 0
        end
        storage.utils.inserter_direction_report=function(serialized)
            return serialized
        end
        storage.utils.serialize_entity=function(entity)
            return {name=entity.name,position={x=entity.position.x,y=entity.position.y},
                direction=entity.direction,warnings={}}
        end
    """)
    root = Path(__file__).parents[2]
    for relative in (
        "fle/env/mods/utils.lua",
        "fle/env/mods/spatial_diagnostics.lua",
        "fle/env/tools/agent/place_entity/server.lua",
        "fle/env/tools/agent/move_to/server.lua",
    ):
        lua.execute((root / relative).read_text(encoding="utf-8"))
    return lua


def test_place_entity_character_blocker_steps_once_and_discloses_recovery():
    lua = runtime()
    lua.execute(
        CHEST_PROTOTYPE
        + """
        blocker_entities={{name='character',type='character',valid=true,
            position={x=0,y=0},unit_number=14}}
        result=storage.actions.place_entity(1,'steel-chest',0,0,0,true)
        assert(result.error==nil)
        assert(result.recovered=='character_moved')
        assert(result.character_position~=nil)
        assert(created_params.name=='steel-chest')
        assert(created_params.position.x==0 and created_params.position.y==0)
        assert(created_params.direction==0)
        assert(removed_item.name=='steel-chest')
        assert(#teleports==1)
        assert(placeable_calls==2)
        assert(teleports[1].to.x~=0 or teleports[1].to.y~=0)
        """
    )
    char_x = lua.eval("result.character_position.x")
    char_y = lua.eval("result.character_position.y")
    assert (char_x, char_y) != (0, 0)


def test_place_entity_non_character_blocker_does_not_step_character():
    lua = runtime()
    lua.execute(
        CHEST_PROTOTYPE
        + """
        placeable=false
        blocker_entities={{name='small-electric-pole',type='electric-pole',valid=true,
            position={x=0.35,y=0.35},unit_number=1019}}
        result=storage.actions.place_entity(1,'steel-chest',0,0,0,true)
        assert(result.error==true)
        assert(result.reason=='placement_rejected')
        assert(result.blocked_by==nil)
        assert(result.diagnostics.blocked_by.prototype=='small-electric-pole')
        assert(result.position.x==0 and result.position.y==0)
        assert(result.direction==0)
        assert(#teleports==0)
        assert(character.position.x==0 and character.position.y==0)
        assert(placeable_calls==1)
        """
    )


def test_place_entity_character_plus_other_blocker_does_not_step():
    lua = runtime()
    lua.execute(
        CHEST_PROTOTYPE
        + """
        placeable=false
        blocker_entities={
            {name='character',type='character',valid=true,
                position={x=0,y=0},unit_number=14},
            {name='small-electric-pole',type='electric-pole',valid=true,
                position={x=1,y=1},unit_number=1019}}
        result=storage.actions.place_entity(1,'steel-chest',0,0,0,true)
        assert(result.error==true)
        assert(result.diagnostics.blocked_by.prototype=='character')
        assert(#result.diagnostics.overlapping_entities==2)
        assert(#teleports==0)
        assert(character.position.x==0 and character.position.y==0)
        """
    )


def test_place_entity_failed_retry_returns_original_error_shape():
    lua = runtime()
    lua.execute(
        CHEST_PROTOTYPE
        + """
        placeable=false
        blocker_entities={{name='character',type='character',valid=true,
            position={x=0,y=0},unit_number=14}}
        result=storage.actions.place_entity(1,'steel-chest',0,0,0,true)
        assert(result.error==true)
        assert(result.reason=='placement_rejected')
        assert(result.prototype=='steel-chest')
        assert(result.position.x==0 and result.position.y==0)
        assert(result.direction==0)
        assert(result.diagnostics~=nil)
        assert(result.diagnostics.reason=='occupied')
        assert(result.diagnostics.blocked_by.prototype=='character')
        assert(result.recovered==nil)
        assert(result.character_position==nil)
        assert(#teleports==1)
        assert(placeable_calls==2)
        """
    )


def test_move_to_escape_takes_a_validated_free_step():
    lua = runtime()
    lua.execute("""
        storage.fast=false
        game.tick=300
        character.position={x=1,y=0}
        blocked_positions['3.00,0.00']=true
        blocked_positions['2.00,0.00']=true
        storage.walking_queues={[1]={positions={{x=5,y=0}},current_target={x=5,y=0},
            final_target={x=10,y=0},last_progress_tick=0,best_distance=4,
            stop_distance=0}}
        storage.actions.update_walking_queues()
        assert(storage.walking_queues[1].stop_reason=='escaped')
        assert(storage.walking_queues[1].current_target==nil)
        assert(#storage.walking_queues[1].positions==0)
        assert(character.walking_state.walking==false)
        assert(#teleports==1)
        assert(teleports[1].to.x==character.position.x)
        assert(teleports[1].to.y==character.position.y)
        assert(math.abs(teleports[1].to.x-1)<=2 and math.abs(teleports[1].to.y)<=2)
        assert(not probe_blocked(teleports[1].to))
        """)


def test_move_to_escape_fails_cleanly_when_boxed_in():
    lua = runtime()
    lua.execute("""
        storage.fast=false
        game.tick=300
        character.position={x=1,y=0}
        tile_blocks_player=true
        storage.walking_queues={[1]={positions={{x=5,y=0}},current_target={x=5,y=0},
            final_target={x=10,y=0},last_progress_tick=0,best_distance=4,
            stop_distance=0}}
        storage.actions.update_walking_queues()
        assert(storage.walking_queues[1].stop_reason=='blocked_no_progress')
        assert(storage.walking_queues[1].current_target==nil)
        assert(#teleports==0)
        assert(character.position.x==1 and character.position.y==0)
        """)


def test_move_to_unstick_steps_to_nearest_free_tile():
    lua = runtime()
    lua.execute("""
        blocked_positions['0.00,0.00']=true
        result=storage.actions.move_to(1,'__unstick__','nil','nil',2)
        assert(result.moved==true)
        assert(result.steps==1)
        assert(result.reason=='start_free')
        assert(result.position.x==1 and result.position.y==0)
        assert(#teleports==1)
        assert(teleports[1].to.x==1 and teleports[1].to.y==0)
        assert(character.position.x==1 and character.position.y==0)
        """)


def test_move_to_unstick_reports_failure_when_boxed_in():
    lua = runtime()
    lua.execute("""
        blocked_positions['0.00,0.00']=true
        tile_blocks_player=true
        result=storage.actions.move_to(1,'__unstick__','nil','nil',2)
        assert(result.moved==false)
        assert(result.steps==0)
        assert(result.reason=='tree-04')
        assert(result.position.x==0 and result.position.y==0)
        assert(#teleports==0)
        assert(character.position.x==0 and character.position.y==0)
        """)


def test_engine_mocks_reject_members_absent_from_luatile():
    # Canary for the mock contract: `tile.walkable` (and other 1.1-era members)
    # must fail here exactly like the live engine, so production Lua that reads
    # them cannot pass this suite.
    lua = runtime()
    for member in ("walkable", "collision_mask", "mineable", "hidden"):
        with pytest.raises(LuaError, match=f"LuaTile doesn't contain key {member}"):
            lua.execute(f"local tile = surface.get_tile(0, 0); return tile.{member}")


def test_engine_mock_tile_collision_contract_matches_2_0():
    lua = runtime()
    assert lua.eval("surface.get_tile(0, 0).collides_with('player')") is False
    lua.execute("tile_blocks_player = true")
    assert lua.eval("surface.get_tile(0, 0).collides_with('player')") is True


def _move_client(status: dict) -> MoveTo:
    tool = MoveTo.__new__(MoveTo)
    tool.player_index = 1
    tool.game_state = Mock()
    tool.game_state.player_location = Position(x=0.0, y=0.0)
    tool.game_state.instance.fast = False
    tool.game_state._program_runtime = None
    tool.refresh_player_location = Mock(return_value=Position(x=0.0, y=0.0))
    tool.request_path = Mock(return_value="handle")
    tool.get_path = Mock()
    tool.execute = Mock(side_effect=[({"ok": True}, 0), (status, 0)])
    tool._game_tick = Mock(return_value=100)
    return tool


def test_move_to_client_returns_escaped_position_without_raising():
    tool = _move_client({"active": False, "x": 1.0, "y": 0.0, "stop_reason": "escaped"})
    final, receipt = tool._move_one(
        Position(x=10.0, y=0.0),
        laying=None,
        leading=None,
        stop_distance=0,
        interrupt_on=set(),
        timeout_ticks=100,
    )
    assert (final.x, final.y) == (1.0, 0.0)
    assert receipt["stop_reason"] == "escaped"
    assert receipt["status"] == "partial"


def test_move_to_client_blocked_reports_current_and_destination():
    tool = _move_client(
        {"active": False, "x": 1.0, "y": 0.5, "stop_reason": "blocked_no_progress"}
    )
    with pytest.raises(RuntimeError) as error:
        tool._move_one(
            Position(x=10.0, y=0.0),
            laying=None,
            leading=None,
            stop_distance=0,
            interrupt_on=set(),
            timeout_ticks=100,
        )
    message = str(error.value)
    assert "Movement blocked near (1.00, 0.50)" in message
    assert "could not escape toward (10.00, 0.00)" in message
    assert "requested destination may be occupied" in message


def _unstick_client() -> MoveTo:
    tool = MoveTo.__new__(MoveTo)
    tool.player_index = 1
    tool.game_state = Mock()
    tool.game_state.player_location = Position(x=0.0, y=0.0)
    tool.game_state.instance.fast = False
    tool.game_state._program_runtime = None
    tool.refresh_player_location = Mock(return_value=Position(x=0.0, y=0.0))
    tool._game_tick = Mock(return_value=100)
    return tool


def _move_one(tool, goal):
    return tool._move_one(
        goal,
        laying=None,
        leading=None,
        stop_distance=0,
        interrupt_on=set(),
        timeout_ticks=100,
    )


def test_move_to_client_unsticks_occupied_start_and_retries_once():
    tool = _unstick_client()
    tool.request_path = Mock(side_effect=["first", "second", "third"])
    not_found = RuntimeError(
        '{"status": "not_found", "diagnostics": {"start": {"reason": "occupied"}}}'
    )
    tool.get_path = Mock(side_effect=[not_found, [], ["waypoint"]])
    tool.execute = Mock(
        side_effect=[
            (
                {
                    "moved": True,
                    "steps": 1,
                    "reason": "small-electric-pole",
                    "position": {"x": 1.0, "y": 0.0},
                },
                0,
            ),
            ({"x": 1.0, "y": 0.0}, 0),
            ({"active": False, "x": 5.0, "y": 0.0, "stop_reason": "arrived"}, 0),
        ]
    )
    final, receipt = _move_one(tool, Position(x=5.0, y=0.0))
    assert (final.x, final.y) == (5.0, 0.0)
    assert receipt["status"] == "completed"
    assert tool.get_path.call_count == 3
    assert tool.execute.call_args_list[0] == call(1, "__unstick__", NONE, NONE, 2)


def test_move_to_client_bounded_unstick_failure_reports_position_and_reason():
    tool = _unstick_client()
    tool.request_path = Mock(return_value="handle")
    tool.get_path = Mock(side_effect=RuntimeError('{"status": "not_found"}'))
    tool.execute = Mock(
        side_effect=[
            (
                {
                    "moved": True,
                    "steps": 1,
                    "reason": "terrain",
                    "position": {"x": 1.0, "y": 0.0},
                },
                0,
            ),
            (
                {
                    "moved": True,
                    "steps": 1,
                    "reason": "terrain",
                    "position": {"x": 2.0, "y": 0.0},
                },
                0,
            ),
        ]
    )
    with pytest.raises(RuntimeError) as error:
        _move_one(tool, Position(x=5.0, y=0.0))
    assert tool.execute.call_count == 2
    message = str(error.value)
    assert "blocking reason: terrain" in message
    assert "(2.00, 0.00)" in message


def test_move_to_client_target_on_own_tile_is_already_reached():
    tool = _unstick_client()
    tool.request_path = Mock()
    tool.get_path = Mock()
    tool.execute = Mock()
    final, receipt = _move_one(tool, Position(x=0.4, y=0.2))
    assert (final.x, final.y) == (0.0, 0.0)
    assert receipt["stop_reason"] == "already_in_range"
    tool.request_path.assert_not_called()
    tool.execute.assert_not_called()
