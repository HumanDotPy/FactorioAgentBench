from pathlib import Path
from unittest.mock import Mock

import pytest
from lupa.lua54 import LuaRuntime

from fle.env.entities import Position
from fle.env.tools.agent.get_fluid_network.client import GetFluidNetwork

pytestmark = pytest.mark.no_factorio


def runtime():
    lua = LuaRuntime()
    lua.execute("""
        storage={actions={},agent_characters={[1]={surface=nil}}}
        entities={}
        function add_entity(x,y,entity)
            entities[string.format('%d,%d',x,y)]=entity
        end
        function make_box(opts)
            return {
                [1]={amount=opts.amount or 0},
                get_fluid_segment_id=function(i) return opts.sid end,
                get_fluid_segment_contents=function(i) return opts.contents end,
                get_capacity=function(i) return opts.capacity end,
                get_connections=function(i) return opts.connections or {} end,
            }
        end
        function make_entity(opts)
            return {
                name=opts.name,
                type=opts.type,
                position={x=opts.x,y=opts.y},
                unit_number=opts.id,
                fluidbox=opts.fb,
            }
        end
        surface={
            find_entities_filtered=function(query)
                local e=entities[string.format('%d,%d',query.position.x,query.position.y)]
                if e then return {e} end
                return {}
            end,
        }
        storage.agent_characters[1].surface=surface
    """)
    lua.execute(
        (
            Path(__file__).parents[2]
            / "fle/env/tools/agent/get_fluid_network/server.lua"
        ).read_text()
    )
    return lua


def test_pipe_segment_reports_fluid_amount_capacity_and_counts():
    lua = runtime()
    lua.execute("""
        pipe1_box=make_box{sid=7,contents={steam=100},capacity=300,amount=100}
        pipe1=make_entity{name='pipe',type='pipe',x=0,y=0,id=1,fb=pipe1_box}
        pipe2_box=make_box{sid=7,contents={steam=100},capacity=300,amount=100}
        pipe2=make_entity{name='pipe',type='pipe',x=1,y=0,id=2,fb=pipe2_box}
        pump_box=make_box{sid=7,contents={steam=100},capacity=300,amount=100}
        pump=make_entity{name='pump',type='pump',x=0,y=1,id=3,fb=pump_box}
        tank_box=make_box{sid=7,contents={steam=100},capacity=300,amount=100}
        tank=make_entity{name='storage-tank',type='storage-tank',x=-1,y=0,id=4,fb=tank_box}
        foreign_box=make_box{sid=8,contents={water=5},capacity=100,amount=5}
        foreign=make_entity{name='pipe',type='pipe',x=2,y=0,id=5,fb=foreign_box}
        pipe1_box.get_connections=function(i) return {{owner=pipe2},{owner=pump},{owner=tank},{owner=foreign}} end
        pipe2_box.get_connections=function(i) return {{owner=pipe1}} end
        pump_box.get_connections=function(i) return {{owner=pipe1}} end
        tank_box.get_connections=function(i) return {{owner=pipe1}} end
        foreign_box.get_connections=function(i) return {{owner=pipe1}} end
        add_entity(0,0,pipe1)
        add_entity(1,0,pipe2)
        add_entity(0,1,pump)
        add_entity(-1,0,tank)
        add_entity(2,0,foreign)
        result=storage.actions.get_fluid_network(1,0,0,false,512)
        assert(result.entity.name=='pipe')
        assert(result.entity.entity_id==1)
        assert(result.entity.position.x==0 and result.entity.position.y==0)
        assert(result.segment_id==7)
        assert(result.fluid=='steam')
        assert(result.amount==100)
        assert(result.capacity==300)
        assert(math.abs(result.fill_ratio-100/300) < 1e-9)
        assert(result.entity_count==4)
        assert(result.pipe_count==2)
        assert(result.tank_count==1)
        assert(result.pump_count==1)
        assert(result.machine_count==0)
        assert(result.entities_truncated==false)
        assert(result.members==nil)
    """)


def test_traversal_respects_max_entities():
    lua = runtime()
    lua.execute("""
        boxes={}
        pipes={}
        for i=1,4 do
            boxes[i]=make_box{sid=3,contents={water=10},capacity=400,amount=10}
            pipes[i]=make_entity{name='pipe',type='pipe',x=i-1,y=0,id=i,fb=boxes[i]}
        end
        for i=1,4 do
            local conns={}
            if pipes[i-1] then conns[#conns+1]={owner=pipes[i-1]} end
            if pipes[i+1] then conns[#conns+1]={owner=pipes[i+1]} end
            boxes[i].get_connections=function(j) return conns end
        end
        for i=1,4 do add_entity(i-1,0,pipes[i]) end
        result=storage.actions.get_fluid_network(1,0,0,false,2)
        assert(result.entity_count==2)
        assert(result.entities_truncated==true)
        assert(result.pipe_count==2)
    """)


def test_machine_without_segment_falls_back_to_own_box():
    lua = runtime()
    lua.execute("""
        box=make_box{sid=nil,contents=nil,capacity=250,amount=40}
        box[2]={amount=10}
        box.get_capacity=function(i)
            if i==1 then return 250 end
            return 50
        end
        machine=make_entity{name='stone-furnace',type='furnace',x=2,y=2,id=9,fb=box}
        add_entity(2,2,machine)
        result=storage.actions.get_fluid_network(1,2,2,false,512)
        assert(result.segment_id==nil)
        assert(result.fluid==nil)
        assert(result.amount==50)
        assert(result.capacity==300)
        assert(math.abs(result.fill_ratio-50/300) < 1e-9)
        assert(result.entity_count==1)
        assert(result.machine_count==1)
        assert(result.pipe_count==0 and result.tank_count==0 and result.pump_count==0)
    """)


def test_missing_fluidbox_returns_error():
    lua = runtime()
    lua.execute("""
        add_entity(3,3,{name='transport-belt',type='transport-belt',
            position={x=3,y=3},unit_number=1})
        result=storage.actions.get_fluid_network(1,3,3,false,512)
        assert(result.error~=nil)
        assert(result.error:find('no fluid connection')~=nil)
        missing=storage.actions.get_fluid_network(1,50,50,false,512)
        assert(missing.error~=nil)
        assert(missing.entity==nil)
    """)


def test_include_members_controls_member_list():
    lua = runtime()
    lua.execute("""
        box=make_box{sid=5,contents={crudeoil=25},capacity=100,amount=25}
        pipe=make_entity{name='pipe',type='pipe',x=4,y=4,id=1,fb=box}
        add_entity(4,4,pipe)
        without=storage.actions.get_fluid_network(1,4,4,false,512)
        assert(without.members==nil)
        with_members=storage.actions.get_fluid_network(1,4,4,true,512)
        assert(#with_members.members==1)
        assert(with_members.members[1].name=='pipe')
        assert(with_members.members[1].type=='pipe')
        assert(with_members.members[1].entity_id==1)
        assert(with_members.members[1].position.x==4)
        assert(with_members.members[1].position.y==4)
    """)


def test_client_validates_arguments_before_executing():
    tool = GetFluidNetwork.__new__(GetFluidNetwork)
    tool.player_index = 1
    tool.execute = Mock()
    with pytest.raises(ValueError, match="position must be a Position"):
        tool((0, 0))
    with pytest.raises(ValueError, match="include_members"):
        tool(Position(x=0, y=0), include_members=1)
    with pytest.raises(ValueError, match="max_entities"):
        tool(Position(x=0, y=0), max_entities=True)
    with pytest.raises(ValueError, match="max_entities"):
        tool(Position(x=0, y=0), max_entities=0)
    with pytest.raises(ValueError, match="max_entities"):
        tool(Position(x=0, y=0), max_entities=4097)
    tool.execute.assert_not_called()


def test_client_passes_through_segment_state_and_normalizes_arrays():
    tool = GetFluidNetwork.__new__(GetFluidNetwork)
    tool.player_index = 1
    tool.execute = Mock(
        return_value=(
            {
                "entity": {
                    "name": "pipe",
                    "entity_id": 1,
                    "position": {"x": 0, "y": 0},
                },
                "segment_id": 7,
                "fluid": "steam",
                "amount": 100,
                "capacity": 300,
                "fill_ratio": 100 / 300,
                "entity_count": 1,
                "pipe_count": 1,
                "tank_count": 0,
                "pump_count": 0,
                "machine_count": 0,
                "entities_truncated": False,
                "members": {1: {"name": "pipe", "position": {1: 0, 2: 0}}},
            },
            0,
        )
    )
    result = tool(Position(x=0, y=0))
    assert result["segment_id"] == 7
    assert result["fluid"] == "steam"
    assert result["amount"] == 100
    assert result["members"] == [{"name": "pipe", "position": [0, 0]}]
    tool.execute.assert_called_once_with(1, 0, 0, False, 512)


def test_client_raises_on_error_dict_and_string():
    tool = GetFluidNetwork.__new__(GetFluidNetwork)
    tool.player_index = 1
    tool.execute = Mock(return_value=({"error": "no fluid connection at (0, 0)"}, 0))
    with pytest.raises(Exception, match="Could not read fluid network"):
        tool(Position(x=0, y=0))
    tool.execute = Mock(return_value=("no fluid connection at (0, 0)", 0))
    with pytest.raises(Exception, match="Could not read fluid network"):
        tool(Position(x=0, y=0))


def test_client_accepts_own_box_response_without_segment_id():
    tool = GetFluidNetwork.__new__(GetFluidNetwork)
    tool.player_index = 1
    tool.execute = Mock(
        return_value=(
            {
                "entity": {
                    "name": "stone-furnace",
                    "entity_id": 9,
                    "position": {"x": 2, "y": 2},
                },
                "segment_id": None,
                "fluid": None,
                "amount": 40,
                "capacity": 250,
                "fill_ratio": 0.16,
                "entity_count": 1,
                "machine_count": 1,
                "entities_truncated": False,
            },
            0,
        )
    )
    result = tool(Position(x=2, y=2))
    assert result["amount"] == 40
    assert result["segment_id"] is None
