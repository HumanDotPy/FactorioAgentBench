from pathlib import Path
from unittest.mock import Mock

import pytest
from lupa.lua54 import LuaRuntime

from fle.env.entities import Position
from fle.env.tools.agent.get_entity_ports.client import GetEntityPorts

pytestmark = pytest.mark.no_factorio


def runtime():
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
        game={}
        prototypes={entity={}}
        entities={}
        found={}
        function add_entity(x,y,entity)
            entities[string.format('%.1f,%.1f',x,y)]=entity
        end
        function fluidbox(ports,connections)
            local fb={
                get_pipe_connections=function(index) return ports[index] end,
                get_connections=function(index)
                    if connections==nil then return {} end
                    return connections[index] or {}
                end,
            }
            return setmetatable(fb,{__len=function() return #ports end})
        end
        surface={
            find_entities_filtered=function(query)
                local key=string.format('%.1f,%.1f',query.position.x,query.position.y)
                if found[key] then return found[key] end
                local entity=entities[key]
                if entity then return {entity} end
                return {}
            end,
            can_place_entity=function(params) return true end,
        }
        character={surface=surface,force='player'}
        storage.agent_characters[1]=character
    """)
    root = Path(__file__).parents[2]
    lua.execute((root / "fle/env/mods/utils.lua").read_text())
    lua.execute((root / "fle/env/tools/agent/get_entity_ports/server.lua").read_text())
    return lua


def test_get_entity_ports_splits_boiler_like_ports():
    lua = runtime()
    lua.execute("""
        add_entity(0,0,{
            name='boiler', type='boiler', unit_number=7, position={x=0,y=0},
            fluidbox=fluidbox({
                {
                    {position={x=-0.5,y=-1.0},
                        flow_direction='input-output', connection_type='normal'},
                    {position={x=0.5,y=-1.0},
                        flow_direction='input-output', connection_type='normal'},
                },
                {
                    {position={x=1.0,y=-0.5},
                        flow_direction='output', connection_type='normal'},
                },
            }),
        })
        result=storage.actions.get_entity_ports(1,0,0,'boiler')
        assert(result.entity_id==7 and result.name=='boiler')
        assert(#result.ports==3)
        assert(#result.inputs==0)
        assert(#result.outputs==1)
        assert(result.outputs[1].fluidbox_index==2)
        assert(result.outputs[1].flow_direction=='output')
        assert(result.ports[1].flow_direction=='input-output')
        assert(result.ports[1].connection_type=='normal')
        assert(result.ports[3].x==1.0 and result.ports[3].y==-0.5)
    """)


def test_get_entity_ports_splits_input_and_output_ports():
    lua = runtime()
    lua.execute("""
        add_entity(2,3,{
            name='chemical-plant', type='assembling-machine', unit_number=11,
            position={x=2,y=3},
            fluidbox=fluidbox({
                {{position={x=1.5,y=3.0},
                    flow_direction='input', connection_type='normal'}},
                {{position={x=2.5,y=3.0},
                    flow_direction='output', connection_type='linked'}},
            }),
        })
        result=storage.actions.get_entity_ports(1,2,3,'chemical-plant')
        assert(result.entity_id==11)
        assert(#result.ports==2 and #result.inputs==1 and #result.outputs==1)
        assert(result.inputs[1].fluidbox_index==1)
        assert(result.outputs[1].connection_type=='linked')
    """)


def test_get_entity_ports_prefers_named_entity_and_falls_back():
    lua = runtime()
    lua.execute("""
        found['0.0,0.0']={
            {name='iron-ore', type='resource', unit_number=1,
                position={x=0,y=0}},
            {name='stone-furnace', type='furnace', unit_number=2,
                position={x=0,y=0}},
            {name='boiler', type='boiler', unit_number=3,
                position={x=0,y=0}},
        }
        named=storage.actions.get_entity_ports(1,0,0,'boiler')
        assert(named.entity_id==3 and named.name=='boiler')
        fallback=storage.actions.get_entity_ports(1,0,0,'steam-engine')
        assert(fallback.entity_id==2 and fallback.name=='stone-furnace')
    """)


def test_get_entity_ports_without_fluidbox_returns_empty_lists():
    lua = runtime()
    lua.execute("""
        add_entity(0,0,{name='assembling-machine-1', type='assembling-machine',
            unit_number=3, position={x=0,y=0}})
        result=storage.actions.get_entity_ports(1,0,0,'assembling-machine-1')
        assert(result.entity_id==3)
        assert(#result.inputs==0 and #result.outputs==0 and #result.ports==0)
    """)


def test_get_entity_ports_survives_fluidbox_errors():
    lua = runtime()
    lua.execute("""
        add_entity(0,0,setmetatable(
            {name='pipe', type='pipe', unit_number=4, position={x=0,y=0}},
            {__index=function() error('entity has no fluidbox') end}))
        result=storage.actions.get_entity_ports(1,0,0,'pipe')
        assert(result.entity_id==4)
        assert(#result.ports==0)
    """)


def test_get_entity_ports_reports_missing_entity():
    lua = runtime()
    lua.execute("""
        result=storage.actions.get_entity_ports(1,5,5,'boiler')
        assert(result.error ~= nil)
        assert(result.entity_id == nil)
    """)


def test_get_entity_ports_reports_connection_state_and_attach_tiles():
    lua = runtime()
    lua.execute("""
        add_entity(-15.5,32,{
            name='boiler', type='boiler', unit_number=7, valid=true,
            position={x=-15.5,y=32},
            bounding_box={left_top={x=-17,y=31}, right_bottom={x=-14,y=33}},
            fluidbox=fluidbox({
                {
                    {position={x=-16.5,y=32.5}, direction=12,
                        flow_direction='input-output', connection_type='normal'},
                    {position={x=-14.5,y=32.5}, direction=4,
                        flow_direction='input-output', connection_type='normal'},
                },
                {
                    {position={x=-15.5,y=31.5}, direction=0,
                        flow_direction='output', connection_type='normal'},
                },
            }, {
                [1]={{owner={valid=true, unit_number=99, name='pipe',
                    position={x=-17.5,y=32.5},
                    bounding_box={left_top={x=-18,y=32},
                        right_bottom={x=-17,y=33}}}}},
            }),
        })
        result=storage.actions.get_entity_ports(1,-15.5,32,'boiler')
        assert(result.entity_id==7 and result.name=='boiler')
        assert(#result.ports==3)
        local west=result.ports[1]
        assert(west.x==-16.5 and west.y==32.5)
        assert(west.direction==12)
        assert(west.connected==true)
        assert(west.peers[1].name=='pipe')
        assert(west.peers[1].entity_id==99)
        assert(west.attach_tiles==nil)
        local east=result.ports[2]
        assert(east.connected==false)
        assert(east.attach_tiles[1].x==-13.5)
        assert(east.attach_tiles[1].y==32.5)
        local steam=result.outputs[1]
        assert(steam.connected==false)
        assert(steam.attach_tiles[1].x==-15.5)
        assert(steam.attach_tiles[1].y==30.5)
    """)


def test_get_entity_ports_marks_connection_state_unknown_without_api():
    lua = runtime()
    lua.execute("""
        add_entity(0,0,{
            name='boiler', type='boiler', unit_number=7, valid=true,
            position={x=0,y=0},
            bounding_box={left_top={x=-1.5,y=-1}, right_bottom={x=1.5,y=1}},
            fluidbox=setmetatable(
                {get_pipe_connections=function(index)
                    return {{position={x=0,y=1},
                        flow_direction='output', connection_type='normal'}}
                end},
                {__len=function() return 1 end}),
        })
        result=storage.actions.get_entity_ports(1,0,0,'boiler')
        assert(result.ports[1].connected==nil)
        assert(result.ports[1].attach_tiles==nil)
    """)


def test_attach_connection_report_warns_for_open_machine_ports():
    lua = runtime()
    lua.execute("""
        prototypes.entity.boiler={type='boiler', fluid_boxes={{}, {}}}
        prototypes.entity.pipe={type='pipe', fluid_boxes={{}}}
        local machine={
            name='boiler', type='boiler', unit_number=7, valid=true,
            position={x=-15.5,y=32},
            bounding_box={left_top={x=-17,y=31}, right_bottom={x=-14,y=33}},
            fluidbox=fluidbox({
                {{position={x=-16.5,y=32.5}, direction=12,
                    flow_direction='input-output', connection_type='normal'}},
                {{position={x=-15.5,y=31.5}, direction=0,
                    flow_direction='output', connection_type='normal'}},
            }, {[1]={}, [2]={}}),
        }
        local serialized={warnings={}}
        storage.utils.attach_connection_report(
            serialized, machine, storage.agent_characters[1])
        assert(serialized.fluid ~= nil)
        assert(#serialized.fluid.ports==2)
        assert(#serialized.fluid.ports[1].attach_tiles==1)
        insert_warning=nil
        output_warning=nil
        for _,warning in ipairs(serialized.warnings) do
            if string.find(warning, 'unconnected fluid port') then
                insert_warning=warning
            end
            if string.find(warning, 'unconnected output port') then
                output_warning=warning
            end
        end
        assert(insert_warning ~= nil)
        assert(string.find(insert_warning, '%(-17%.5, 32%.5%)') ~= nil)
        assert(output_warning ~= nil)
        assert(string.find(output_warning, '%(-15%.5, 30%.5%)') ~= nil)

        local pipe={
            name='pipe', type='pipe', unit_number=8, valid=true,
            position={x=0,y=0},
            fluidbox=fluidbox({
                {{position={x=0,y=0}, direction=0,
                    flow_direction='input-output', connection_type='normal'}},
            }, {[1]={}}),
        }
        local serialized_pipe={warnings={}}
        storage.utils.attach_connection_report(
            serialized_pipe, pipe, storage.agent_characters[1])
        assert(serialized_pipe.fluid ~= nil)
        assert(#serialized_pipe.warnings==0)
    """)


def test_attach_connection_report_tolerates_prototypes_without_fluid_boxes():
    lua = runtime()
    lua.execute("""
        prototypes.entity['burner-mining-drill']=setmetatable({}, {
            __index=function()
                error("LuaEntityPrototype doesn't contain key fluid_boxes")
            end,
        })
        local machine={
            name='burner-mining-drill', type='mining-drill', unit_number=7,
            valid=true, position={x=0,y=0},
        }
        local serialized={warnings={}}
        local result=storage.utils.attach_connection_report(
            serialized, machine, storage.agent_characters[1])
        assert(result == serialized)
        assert(result.fluid == nil)
        assert(#result.warnings == 0)
    """)


def test_client_resolves_fresh_entity_and_passes_arguments():
    tool = GetEntityPorts.__new__(GetEntityPorts)
    tool.player_index = 1
    tool.execute = Mock(return_value=({"entity_id": 7, "name": "boiler"}, 0))
    tool.game_state = Mock()
    tool.game_state._program_runtime = None
    tool.name = "get_entity_ports"
    fresh = Mock()
    fresh.name = "boiler"
    fresh.position = Position(x=0.0, y=-0.5)
    tool.game_state.resolve_entity.return_value = fresh
    stale = Mock()
    stale.id = 9

    result = tool(stale)

    tool.game_state.resolve_entity.assert_called_once_with(stale)
    tool.execute.assert_called_once_with(1, 0.0, -0.5, "boiler")
    assert result["entity_id"] == 7


def test_client_uses_passed_entity_when_id_missing():
    tool = GetEntityPorts.__new__(GetEntityPorts)
    tool.player_index = 1
    tool.execute = Mock(return_value=({"entity_id": 1, "name": "pipe"}, 0))
    tool.game_state = Mock()
    tool.game_state._program_runtime = None
    tool.name = "get_entity_ports"
    entity = Mock()
    entity.id = None
    entity.name = "pipe"
    entity.position = Position(x=2, y=3)

    tool(entity)

    tool.game_state.resolve_entity.assert_not_called()
    tool.execute.assert_called_once_with(1, 2, 3, "pipe")


def test_client_raises_on_server_error():
    tool = GetEntityPorts.__new__(GetEntityPorts)
    tool.player_index = 1
    tool.game_state = Mock()
    tool.game_state._program_runtime = None
    tool.name = "get_entity_ports"
    entity = Mock()
    entity.id = None
    entity.name = "boiler"
    entity.position = Position(x=0, y=0)

    tool.execute = Mock(return_value=({"error": "no entity at 0,0"}, 0))
    with pytest.raises(Exception, match="Could not read entity ports for boiler"):
        tool(entity)

    tool.execute = Mock(return_value=(True, 0))
    with pytest.raises(Exception, match="Could not read entity ports"):
        tool(entity)


def test_client_normalizes_port_arrays_to_lists():
    from fle.env.tools.agent.get_entity_ports.client import _normalize_arrays

    response = {
        "entity_id": 7,
        "name": "boiler",
        "inputs": {},
        "outputs": {1: {"x": 1, "y": 2}},
        "ports": {1: {"x": 0, "y": 0}, 2: {"x": 1, "y": 2}},
    }
    normalized = _normalize_arrays(response)
    assert normalized["outputs"] == [{"x": 1, "y": 2}]
    assert normalized["ports"][0] == {"x": 0, "y": 0}
    assert normalized["ports"][1] == {"x": 1, "y": 2}
