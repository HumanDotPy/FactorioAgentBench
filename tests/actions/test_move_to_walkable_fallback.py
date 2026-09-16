import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from lupa.lua54 import LuaRuntime

from fle.env.entities import Position
from fle.env.tools.agent.move_to.client import MoveTo

pytestmark = pytest.mark.no_factorio


def belt_runtime():
    lua = LuaRuntime()
    lua.execute("""
        storage={actions={},agent_characters={},utils={},fast=false}
        script={on_event=function()end,on_nth_tick=function()end}
        defines={events={on_tick=1},
            direction={north=0,east=4,south=8,west=12},
            inventory={character_main=1},
            build_check_type={manual=0}}
        game={tick=0,surfaces={}}
        entities={}
        tile_blocks_player=false
        function add_entity(name, etype, x, y, layers)
            entities[#entities+1]={name=name,type=etype,valid=true,
                position={x=x,y=y},layers=layers}
        end
        local function mask_matches(mask, layers)
            if type(mask)=='table' then
                for _, layer in ipairs(mask) do
                    if layers[layer] then return true end
                end
                return false
            end
            return layers[mask]==true
        end
        local function inside_area(area, position)
            return position.x>=area[1][1] and position.x<=area[2][1]
                and position.y>=area[1][2] and position.y<=area[2][2]
        end
        surface={
            find_entities_filtered=function(query)
                local found={}
                for _, entity in ipairs(entities) do
                    local located=false
                    if query.area and inside_area(query.area, entity.position) then
                        located=true
                    end
                    if query.position and query.radius then
                        local dx=query.position.x-entity.position.x
                        local dy=query.position.y-entity.position.y
                        if math.sqrt(dx*dx+dy*dy)<=query.radius then
                            located=true
                        end
                    end
                    if located and mask_matches(query.collision_mask, entity.layers) then
                        found[#found+1]=entity
                        if query.limit and #found>=query.limit then break end
                    end
                end
                return found
            end,
            get_tile=function(x,y)
                return {name='grass',valid=true,
                    collides_with=function(layer) return tile_blocks_player end}
            end,
        }
        character={valid=true,unit_number=1,position={x=0.5,y=0.5},
            layers={player=true,is_object=true,train=true},
            prototype={collision_box={left_top={x=-0.35,y=-0.35},
                right_bottom={x=0.35,y=0.35}}}}
        character.surface=surface
        entities[#entities+1]=character
        storage.agent_characters[1]=character
        storage.utils.ensure_valid_character=function() return character end
        storage.utils.escape_character_to_free_tile=function(player)
            player.position={x=player.position.x+1,y=player.position.y}
            return player.position
        end
    """)
    root = Path(__file__).parents[2]
    lua.execute(
        (root / "fle/env/tools/agent/move_to/server.lua").read_text(encoding="utf-8")
    )
    return lua


def test_unstick_does_not_step_off_a_walkable_belt_start():
    lua = belt_runtime()
    lua.execute("""
        add_entity('transport-belt','transport-belt',0.5,0.5,
            {object=true,transport_belt=true})
        result=storage.actions.move_to(1,'__unstick__','nil','nil',2)
        assert(result.moved==false)
        assert(result.reason=='start_free')
        assert(result.steps==0)
        assert(character.position.x==0.5 and character.position.y==0.5)
    """)


def test_move_to_lays_belts_on_the_acting_force():
    lua = belt_runtime()
    lua.execute("""
        storage.fast=true
        storage.elapsed_ticks=0
        character.force={name='custom-force'}
        character.position={x=0.5,y=0.5}
        character.get_item_count=function() return 1 end
        character.remove_item=function() end
        character.teleport=function(pos) character.position=pos end
        storage.paths={h={{position={x=1.5,y=0.5}}}}
        storage.utils.calculate_movement_ticks=function() return 0 end
        storage.utils.get_direction=function() return 4 end
        storage.utils.can_place_entity=function() return true end
        surface.can_fast_replace=function() return false end
        surface.create_entity=function(params) created=params; return {valid=true} end
        prototypes={entity={["transport-belt"]={}}}
        result=storage.actions.move_to(1,'h','transport-belt',1,0)
        assert(created.force==character.force)
        assert(created.force.name=='custom-force')
    """)


def test_unstick_still_steps_off_a_non_walkable_blocker():
    lua = belt_runtime()
    lua.execute("""
        add_entity('tree-04','tree',0.5,0.5,{player=true,object=true})
        result=storage.actions.move_to(1,'__unstick__','nil','nil',2)
        assert(result.moved==true)
        assert(result.reason=='start_free')
        assert(character.position.x==1.5 and character.position.y==0.5)
    """)


def test_nearest_walkable_treats_belt_tiles_as_walkable():
    lua = belt_runtime()
    lua.execute("""
        add_entity('transport-belt','transport-belt',10.5,10.5,
            {object=true,transport_belt=true})
        result=storage.actions.move_to(1,'__nearest_walkable__',10.5,10.5,4)
        assert(result.status=='ok')
        assert(result.candidates[1].x==10.5 and result.candidates[1].y==10.5)
        assert(result.candidates[1].distance==0)
    """)


def test_nearest_walkable_skips_player_blocking_tiles_in_deterministic_order():
    lua = belt_runtime()
    lua.execute("""
        add_entity('iron-chest','container',10.5,10.5,
            {object=true,player=true,is_object=true})
        add_entity('transport-belt','transport-belt',10.5,11.5,
            {object=true,transport_belt=true})
        result=storage.actions.move_to(1,'__nearest_walkable__',10.5,10.5,4)
        assert(result.status=='ok')
        assert(result.candidates[1].x==9.5 and result.candidates[1].y==10.5)
        local belt_found=false
        for _, candidate in ipairs(result.candidates) do
            assert(not (candidate.x==10.5 and candidate.y==10.5))
            if candidate.x==10.5 and candidate.y==11.5 then belt_found=true end
        end
        assert(belt_found==true)
    """)


def test_nearest_walkable_reports_none_when_every_tile_is_blocked():
    lua = belt_runtime()
    lua.execute("""
        tile_blocks_player=true
        result=storage.actions.move_to(1,'__nearest_walkable__',10.5,10.5,4)
        assert(result.status=='none')
        assert(result.scanned_radius==4)
        assert(result.candidates==nil)
    """)


def walk_client():
    tool = MoveTo.__new__(MoveTo)
    tool.player_index = 1
    tool.game_state = Mock()
    tool.game_state.player_location = Position(x=0.0, y=0.0)
    tool.game_state.instance.fast = False
    tool.game_state._program_runtime = None
    tool.refresh_player_location = Mock(return_value=Position(x=0.0, y=0.0))
    tool._game_tick = Mock(return_value=100)
    tool.self_unstick = Mock(return_value=None)
    return tool


def occupied_diagnostic(start_entities, goal_entities):
    return RuntimeError(
        json.dumps(
            {
                "status": "not_found",
                "diagnostics": {
                    "start": {
                        "reason": "occupied",
                        "overlapping_entities": start_entities,
                    },
                    "goal": {
                        "reason": "occupied",
                        "overlapping_entities": goal_entities,
                    },
                },
            }
        )
    )


def move_one(tool, goal):
    return tool._move_one(
        goal,
        laying=None,
        leading=None,
        stop_distance=0,
        interrupt_on=set(),
        timeout_ticks=100,
    )


def test_belt_start_skips_unstick_and_reports_nearest_walkable_fallback():
    tool = walk_client()
    belt = {
        "prototype": "transport-belt",
        "type": "transport-belt",
        "position": {"x": 0.5, "y": 0.5},
    }
    boiler = {"prototype": "boiler", "type": "boiler", "position": {"x": 5.0, "y": 0.0}}
    failure = occupied_diagnostic([belt], [boiler])
    tool.request_path = Mock(side_effect=[f"path-{index}" for index in range(8)])
    tool.get_path = Mock(
        side_effect=[failure, failure, failure, failure, ["waypoint"]]
        + [["waypoint"]] * 4
    )
    tool.execute = Mock(
        side_effect=[
            (
                {
                    "status": "ok",
                    "scanned_radius": 8,
                    "candidates": [{"x": 4.5, "y": 0.5, "distance": 1.118}],
                },
                0,
            ),
            ({"x": 4.5, "y": 0.5}, 0),
            ({"active": False, "x": 4.5, "y": 0.5, "stop_reason": "arrived"}, 0),
        ]
    )

    final, receipt = move_one(tool, Position(x=5.0, y=0.0))

    assert (final.x, final.y) == (4.5, 0.5)
    assert receipt["status"] == "completed"
    assert receipt["stop_reason"] == "arrived"
    assert receipt["fallback"]["kind"] == "nearest_walkable"
    assert receipt["fallback"]["position"] == {"x": 4.5, "y": 0.5}
    assert receipt["fallback"]["distance"] == pytest.approx(0.707, abs=0.001)
    assert receipt["fallback"]["radius"] == 8
    assert receipt["requested"] == {"x": 5.0, "y": 0.0}
    assert receipt["distance_to_requested"] == pytest.approx(0.707, abs=0.001)
    tool.self_unstick.assert_not_called()
    assert tool.request_path.call_args_list[-1].kwargs["finish"] == Position(
        x=4.5, y=0.5
    )


def test_occupied_target_fails_only_when_no_walkable_tile_is_in_range():
    tool = walk_client()
    tool.request_path = Mock(return_value="handle")
    tool.get_path = Mock(side_effect=RuntimeError('{"status": "not_found"}'))
    tool.self_unstick = Mock(
        return_value={
            "moved": False,
            "steps": 0,
            "reason": "start_free",
            "position": {"x": 0.0, "y": 0.0},
        }
    )
    tool.execute = Mock(return_value=({"status": "none", "scanned_radius": 8}, 0))

    with pytest.raises(RuntimeError, match="no reachable walkable tile"):
        move_one(tool, Position(x=5.0, y=0.0))

    assert tool.execute.call_count == 1


def test_genuinely_blocked_start_still_reports_the_blocking_reason():
    tool = walk_client()
    tool.request_path = Mock(return_value="handle")
    tool.get_path = Mock(side_effect=RuntimeError('{"status": "not_found"}'))
    tool.self_unstick = Mock(
        return_value={
            "moved": False,
            "steps": 0,
            "reason": "tree-04",
            "position": {"x": 0.0, "y": 0.0},
        }
    )
    tool.execute = Mock()

    with pytest.raises(RuntimeError, match="blocking reason: tree-04"):
        move_one(tool, Position(x=5.0, y=0.0))

    tool.execute.assert_not_called()


def _move_tool():
    tool = MoveTo.__new__(MoveTo)
    tool.game_state = SimpleNamespace(player_location=Position(x=1.0, y=1.0))
    return tool


def test_request_path_handle_passes_allow_own_entities():
    tool = _move_tool()
    seen = []

    def request_path(**kwargs):
        seen.append(kwargs["allow_paths_through_own_entities"])
        return 5

    tool.request_path = Mock(side_effect=request_path)
    tool.get_path = Mock(return_value=[Position(x=2.0, y=2.0)])
    assert tool._request_path_handle(Position(x=9.0, y=9.0), 0, True) == 5
    assert seen == [True]


def test_request_path_raises_when_all_attempts_fail():
    tool = _move_tool()
    tool.request_path = Mock(side_effect=RuntimeError('{"status": "not_found"}'))
    tool.get_path = Mock(return_value=[Position(x=2.0, y=2.0)])
    with pytest.raises(RuntimeError, match="not_found"):
        tool._request_path_handle(Position(x=9.0, y=9.0), 0)


def test_move_to_retries_permissive_before_walkable_fallback():
    tool = walk_client()
    failure = RuntimeError('{"status": "not_found"}')

    def request_path(**kwargs):
        if not kwargs["allow_paths_through_own_entities"]:
            raise failure
        return "permissive"

    tool.request_path = Mock(side_effect=request_path)
    tool.get_path = Mock(return_value=[Position(x=2.0, y=2.0)])
    tool.execute = Mock(
        side_effect=[
            ({"x": 4.5, "y": 0.5}, 0),
            ({"active": False, "x": 4.5, "y": 0.5, "stop_reason": "arrived"}, 0),
        ]
    )

    final, receipt = move_one(tool, Position(x=5.0, y=0.0))

    assert (final.x, final.y) == (4.5, 0.5)
    assert receipt["status"] == "completed"
    assert receipt["fallback"] is None
