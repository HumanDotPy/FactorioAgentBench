from pathlib import Path
from unittest.mock import Mock

import pytest
from lupa.lua54 import LuaRuntime

from fle.env.entities import Position
from fle.env.tools.agent.get_power_network.client import GetPowerNetwork

pytestmark = pytest.mark.no_factorio


def runtime():
    lua = LuaRuntime()
    lua.execute("""
        storage={actions={},agent_characters={[1]={surface=nil}}}
        entities={}
        poles={}
        defines={flow_precision_index={
            five_seconds=0, one_minute=1, ten_minutes=2, one_hour=3}}
        function add_entity(x,y,entity)
            entities[string.format('%d,%d',x,y)]=entity
        end
        function add_pole(entity)
            poles[#poles+1]=entity
        end
        function in_area(entity,area)
            local p=entity.position
            return p.x>=area[1][1] and p.x<=area[2][1]
                and p.y>=area[1][2] and p.y<=area[2][2]
        end
        function make_stats(input_counts,output_counts,storage_counts)
            local st={
                input_counts=input_counts or {},
                output_counts=output_counts or {},
                storage_counts=storage_counts or {},
            }
            st.get_flow_count=function(query)
                local source
                if query.category=='input' then source=st.input_counts
                elseif query.category=='output' then source=st.output_counts
                else source=st.storage_counts end
                local record=source and source[query.name]
                if record==nil then return 0 end
                if query.count then return record.count or 1 end
                if record.flows then
                    return record.flows[query.precision_index] or record.value or 0
                end
                return record.value or 0
            end
            return st
        end
        surface={
            find_entities_filtered=function(query)
                local out={}
                if query.position then
                    local key=string.format('%d,%d',
                        math.floor(query.position.x),math.floor(query.position.y))
                    local entity=entities[key]
                    if entity then out[#out+1]=entity end
                    return out
                end
                for _,entity in ipairs(poles) do
                    if entity.type==query.type and in_area(entity,query.area) then
                        out[#out+1]=entity
                        if query.limit and #out>=query.limit then break end
                    end
                end
                return out
            end,
        }
        storage.agent_characters[1].surface=surface
    """)
    lua.execute(
        (
            Path(__file__).parents[2]
            / "fle/env/tools/agent/get_power_network/server.lua"
        ).read_text()
    )
    return lua


def test_power_network_returns_watts_and_counts():
    lua = runtime()
    lua.execute("""
        st=make_stats(
            {lab={flows={[0]=2.5},count=3}},
            {['steam-engine']={flows={[0]=7},count=1}},
            {['accumulator']={value=40,count=2}})
        add_entity(0,0,{name='small-electric-pole',type='electric-pole',
            position={x=0,y=0},unit_number=42,electric_network_id=7,
            electric_network_statistics=st})
        result=storage.actions.get_power_network(1,0,0,5,false)
        assert(result.statistics_available==true)
        assert(result.network_id==7)
        assert(result.window_seconds==5)
        assert(result.production_w==420)
        assert(result.consumption_w==150)
        assert(#result.by_producer==1)
        assert(result.by_producer[1].prototype=='steam-engine')
        assert(result.by_producer[1].watts==420)
        assert(result.by_producer[1].count==1)
        assert(#result.by_consumer==1)
        assert(result.by_consumer[1].prototype=='lab')
        assert(result.by_consumer[1].watts==150)
        assert(result.by_consumer[1].count==3)
        assert(#result.storage==1 and result.storage[1].prototype=='accumulator')
        assert(result.storage[1].charge==40 and result.storage[1].count==2)
        assert(result.generator_count==1)
        assert(result.consumer_count==3)
        assert(result.entity.name=='small-electric-pole')
        assert(result.entity.entity_id==42)
        assert(result.entity.position.x==0)
        assert(result.truncated==false)
    """)


def test_power_network_resolves_pole_from_machine():
    lua = runtime()
    lua.execute("""
        st=make_stats({inserter={flows={[0]=2},count=1}},{},{})
        add_entity(0,0,{name='assembling-machine-1',type='assembling-machine',
            position={x=0,y=0},unit_number=9,electric_network_id=7})
        add_pole({name='small-electric-pole',type='electric-pole',
            position={x=3,y=0},unit_number=42,electric_network_id=7,
            electric_network_statistics=st})
        result=storage.actions.get_power_network(1,0,0,5,false)
        assert(result.statistics_available==true)
        assert(result.entity.entity_id==42)
        assert(result.network_id==7)
        assert(result.consumption_w==120)
    """)


def test_power_network_maps_window_to_precision():
    lua = runtime()
    lua.execute("""
        st=make_stats({lab={flows={[0]=1,[1]=60,[2]=600,[3]=3600},count=1}},{},{})
        add_entity(0,0,{name='small-electric-pole',type='electric-pole',
            position={x=0,y=0},unit_number=42,electric_network_id=7,
            electric_network_statistics=st})
        five=storage.actions.get_power_network(1,0,0,5,false)
        minute=storage.actions.get_power_network(1,0,0,60,false)
        ten=storage.actions.get_power_network(1,0,0,600,false)
        hour=storage.actions.get_power_network(1,0,0,3600,false)
        other=storage.actions.get_power_network(1,0,0,7,false)
        assert(five.consumption_w==60)
        assert(minute.consumption_w==3600)
        assert(ten.consumption_w==36000)
        assert(hour.consumption_w==216000)
        assert(minute.window_seconds==60)
        assert(other.window_seconds==5 and other.consumption_w==60)
    """)


def test_power_network_reports_missing_network():
    lua = runtime()
    lua.execute("""
        result=storage.actions.get_power_network(1,5,5,5,false)
        assert(result.error~=nil)
        assert(result.error:find('no electric network')~=nil)
        assert(result.statistics_available==nil)
    """)


def test_power_network_members_are_optional_and_network_scoped():
    lua = runtime()
    lua.execute("""
        st=make_stats({lab={flows={[0]=1},count=1}},{},{})
        center={name='small-electric-pole',type='electric-pole',
            position={x=0,y=0},unit_number=42,electric_network_id=7,
            electric_network_statistics=st}
        add_entity(0,0,center)
        add_pole(center)
        add_pole({name='small-electric-pole',type='electric-pole',
            position={x=4,y=0},unit_number=43,electric_network_id=7})
        add_pole({name='small-electric-pole',type='electric-pole',
            position={x=8,y=0},unit_number=44,electric_network_id=99})
        without=storage.actions.get_power_network(1,0,0,5,false)
        assert(without.pole_count==nil and without.members==nil)
        with_members=storage.actions.get_power_network(1,0,0,5,true)
        assert(with_members.pole_count==2)
        assert(#with_members.members.poles==2)
        assert(with_members.members.poles[1].entity_id==42)
        assert(with_members.members.poles[2].entity_id==43)
        assert(with_members.members.poles[2].position.x==4)
    """)


def test_power_network_truncates_large_lists():
    lua = runtime()
    lua.execute("""
        local inputs={}
        local outputs={}
        local storage_counts={}
        for i=1,70 do
            local name=string.format('%02d',i)
            inputs['consumer-'..name]={flows={[0]=i},count=1}
            outputs['producer-'..name]={flows={[0]=i},count=1}
            storage_counts['accumulator-'..name]={value=i,count=1}
        end
        st=make_stats(inputs,outputs,storage_counts)
        add_entity(0,0,{name='small-electric-pole',type='electric-pole',
            position={x=0,y=0},unit_number=42,electric_network_id=7,
            electric_network_statistics=st})
        result=storage.actions.get_power_network(1,0,0,5,false)
        assert(#result.by_consumer==64)
        assert(#result.by_producer==64)
        assert(#result.storage==64)
        assert(result.truncated==true)
        assert(result.consumer_count==70)
        assert(result.generator_count==70)
        assert(result.by_consumer[1].prototype=='consumer-70')
        assert(result.by_consumer[1].watts==70*60)
        assert(result.by_producer[1].prototype=='producer-70')
        assert(result.storage[1].prototype=='accumulator-70')
        assert(result.storage[1].charge==70)
    """)


def test_power_network_without_network_id_reports_unavailable():
    lua = runtime()
    lua.execute("""
        st=make_stats({lab={flows={[0]=1},count=1}},{},{})
        add_entity(0,0,{name='small-electric-pole',type='electric-pole',
            position={x=0,y=0},unit_number=42,
            electric_network_statistics=st})
        result=storage.actions.get_power_network(1,0,0,5,false)
        assert(result.statistics_available==false)
        assert(result.network_id~=nil)
        assert(result.consumption_w==0)
        assert(result.production_w==0)
        assert(#result.by_consumer==0 and #result.by_producer==0)
        assert(#result.storage==0)
    """)


def test_client_validates_arguments():
    tool = GetPowerNetwork.__new__(GetPowerNetwork)
    tool.player_index = 1
    tool.execute = Mock(return_value=({"network_id": 1}, 0))
    with pytest.raises(ValueError, match="position must be a Position"):
        tool((0, 0))
    with pytest.raises(ValueError, match="window_seconds"):
        tool(Position(x=0, y=0), window_seconds=7)
    with pytest.raises(ValueError, match="include_members"):
        tool(Position(x=0, y=0), include_members="yes")


def test_client_passes_through_and_normalizes():
    tool = GetPowerNetwork.__new__(GetPowerNetwork)
    tool.player_index = 1
    response = {
        "network_id": 1,
        "by_consumer": {1: {"prototype": "lab", "watts": 60}},
        "members": {"poles": {1: {"entity_id": 42}}},
    }
    tool.execute = Mock(return_value=(response, 0))
    result = tool(Position(x=4, y=5), window_seconds=60, include_members=True)
    tool.execute.assert_called_once_with(1, 4, 5, 60, True)
    assert result["by_consumer"] == [{"prototype": "lab", "watts": 60}]
    assert result["members"] == {"poles": [{"entity_id": 42}]}


def test_client_raises_on_error_response():
    tool = GetPowerNetwork.__new__(GetPowerNetwork)
    tool.player_index = 1
    tool.execute = Mock(return_value=({"error": "no electric network at (0, 0)"}, 0))
    with pytest.raises(Exception, match="Could not read power network"):
        tool(Position(x=0, y=0))
    tool.execute = Mock(return_value=("no electric network", 0))
    with pytest.raises(Exception, match="Could not read power network"):
        tool(Position(x=0, y=0))


def test_client_normalizes_lua_arrays_to_lists():
    from fle.env.tools.agent.get_power_network.client import _normalize_arrays

    assert _normalize_arrays({1: "a", 2: "b"}) == ["a", "b"]
    assert _normalize_arrays(
        {"by_consumer": {1: {"prototype": "lab", "position": {1: 3, 2: 4}}}}
    ) == {"by_consumer": [{"prototype": "lab", "position": [3, 4]}]}
