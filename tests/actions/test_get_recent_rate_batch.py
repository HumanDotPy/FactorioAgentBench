from pathlib import Path
from unittest.mock import Mock

from lupa.lua54 import LuaRuntime
import pytest

from fle.env.tools.admin.get_recent_rate.client import GetRecentRate


pytestmark = pytest.mark.no_factorio


SERVER = Path(__file__).parents[2] / "fle/env/tools/admin/get_recent_rate/server.lua"


def runtime():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        storage={actions={},manual_production_events={}}
        game={tick=6000,surfaces={[1]={}},forces={player={
            get_item_production_statistics=function(surface)
                return {get_flow_count=function(request)
                    local totals={["iron-plate"]=300,["copper-plate"]=120}
                    return totals[request.name] or 0
                end}
            end
        }}}
        defines={flow_precision_index={five_seconds=1,one_minute=2,
            ten_minutes=3,one_hour=4}}
    """)
    lua.execute(SERVER.read_text(encoding="utf-8"))
    return lua


def test_single_item_response_shape_and_values_are_unchanged():
    lua = runtime()
    lua.execute("""
        storage.manual_production_events={{tick=5990,outputs={["iron-plate"]=5}}}
        result=storage.actions.get_recent_rate(1,"iron-plate",5)
        assert(result.item_name=="iron-plate")
        assert(result.requested_window_seconds==5)
        assert(result.effective_window_seconds==5)
        assert(result.total_per_minute==300)
        assert(result.manual_per_minute==60)
        assert(result.dynamic_per_minute==240)
        assert(result.observed_at_tick==6000)
        assert(result.error==nil)
    """)


def test_batched_items_and_windows_return_per_window_records():
    lua = runtime()
    lua.execute("""
        storage.manual_production_events={
            {tick=-300000,outputs={["iron-plate"]=999}},
            {tick=5990,outputs={["iron-plate"]=5}},
        }
        result=storage.actions.get_recent_rate(
            1,{"iron-plate","copper-plate"},{5,60,300})
        assert(result.observed_at_tick==6000)
        assert(#storage.manual_production_events==1)
        assert(result.rates["iron-plate"]["5"].dynamic_per_minute==240)
        assert(result.rates["iron-plate"]["5"].manual_per_minute==60)
        assert(result.rates["iron-plate"]["60"].effective_window_seconds==60)
        assert(result.rates["iron-plate"]["60"].manual_per_minute==5)
        assert(result.rates["iron-plate"]["60"].dynamic_per_minute==295)
        assert(result.rates["iron-plate"]["300"].effective_window_seconds==600)
        assert(result.rates["copper-plate"]["5"].dynamic_per_minute==120)
        assert(result.rates["copper-plate"]["5"].manual_per_minute==0)
        assert(result.rates["copper-plate"]["300"].effective_window_seconds==600)
        assert(result.error==nil)
    """)


def test_single_item_can_request_multiple_windows():
    lua = runtime()
    lua.execute("""
        result=storage.actions.get_recent_rate(1,"iron-plate",{5,300})
        assert(result.rates["iron-plate"]["5"].effective_window_seconds==5)
        assert(result.rates["iron-plate"]["300"].effective_window_seconds==600)
    """)


def test_invalid_batched_inputs_return_an_error_without_touching_state():
    lua = runtime()
    lua.execute("""
        assert(storage.actions.get_recent_rate(1,{},5).error=="item_name list must not be empty")
        assert(storage.actions.get_recent_rate(1,{"iron-plate"},{})~=nil)
        assert(storage.actions.get_recent_rate(1,{"iron-plate"},{})["error"]=="window_seconds list must not be empty")
        assert(storage.actions.get_recent_rate(1,{""},5).error~=nil)
        assert(storage.actions.get_recent_rate(1,"",5).error=="item_name must be a non-empty string")
    """)


def test_client_keeps_single_item_protocol_for_existing_callers():
    tool = GetRecentRate.__new__(GetRecentRate)
    tool.player_index = 1
    tool.execute = Mock(return_value=({"dynamic_per_minute": 1.0}, 0))

    assert tool("iron-plate", 5) == {"dynamic_per_minute": 1.0}
    tool.execute.assert_called_once_with(1, "iron-plate", 5)


def test_client_batches_items_and_windows_into_one_call():
    tool = GetRecentRate.__new__(GetRecentRate)
    tool.player_index = 1
    tool.execute = Mock(return_value=({"rates": {}}, 0))

    assert tool(["iron-plate", "copper-plate"], [5, 60]) == {"rates": {}}
    tool.execute.assert_called_once_with(1, ["iron-plate", "copper-plate"], [5, 60])
