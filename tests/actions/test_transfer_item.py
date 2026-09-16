from pathlib import Path
from unittest.mock import Mock

import pytest
from lupa.lua54 import LuaRuntime

from fle.env.entities import Chest, Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.transfer_item.client import TransferItem

pytestmark = pytest.mark.no_factorio

root = Path(__file__).parents[2]


def runtime():
    lua = LuaRuntime()
    lua.execute("""
        storage={actions={},utils={}}
        game={tick=55}
        calls={}
        extract_result=0
        extract_error=nil
        insert_queue={}

        storage.actions.extract_item=function(player_index,item,count,sx,sy,source_name)
            calls[#calls+1]={action='extract',player_index=player_index,item=item,
                count=count,sx=sx,sy=sy,source_name=source_name}
            if extract_error~=nil then error(extract_error) end
            return extract_result
        end

        storage.actions.insert_item=function(player_index,item,count,x,y,target_name,replace)
            calls[#calls+1]={action='insert',player_index=player_index,item=item,
                count=count,x=x,y=y,target_name=target_name,replace=replace}
            if #insert_queue>0 then
                local entry=table.remove(insert_queue,1)
                if entry.error~=nil then error(entry.error) end
                return {inserted=entry.inserted}
            end
            return {inserted=count}
        end
    """)
    lua.execute((root / "fle/env/tools/agent/transfer_item/server.lua").read_text())
    return lua


def test_server_completed_transfer_receipt():
    lua = runtime()
    lua.execute("""
        extract_result=5
        local receipt=storage.actions.transfer_item(1,'coal',
            1,1,'wooden-chest',3,3,'stone-furnace',5)
        assert(receipt.status=='completed')
        assert(receipt.extracted==5)
        assert(receipt.inserted==5)
        assert(receipt.returned==0)
        assert(receipt.leftover==0)
        assert(receipt.tick==55)
        assert(#calls==2)
        assert(calls[1].action=='extract' and calls[1].count==5)
        assert(calls[2].action=='insert' and calls[2].count==5)
        assert(calls[2].x==3 and calls[2].y==3)
    """)


def test_server_partial_transfer_returns_leftovers_to_source():
    lua = runtime()
    lua.execute("""
        extract_result=5
        insert_queue={{inserted=2},{inserted=3}}
        local receipt=storage.actions.transfer_item(1,'coal',
            1,1,'wooden-chest',3,3,'stone-furnace',5)
        assert(receipt.status=='partial')
        assert(receipt.extracted==5)
        assert(receipt.inserted==2)
        assert(receipt.returned==3)
        assert(receipt.leftover==0)
        assert(#calls==3)
        assert(calls[3].action=='insert' and calls[3].count==3)
        assert(calls[3].x==1 and calls[3].y==1)
        assert(calls[3].target_name=='wooden-chest')
    """)


def test_server_partial_transfer_reports_unreturned_leftovers():
    lua = runtime()
    lua.execute("""
        extract_result=5
        insert_queue={{inserted=1},{inserted=0}}
        local receipt=storage.actions.transfer_item(1,'coal',
            1,1,'wooden-chest',3,3,'stone-furnace',5)
        assert(receipt.status=='partial')
        assert(receipt.inserted==1)
        assert(receipt.returned==0)
        assert(receipt.leftover==4)
    """)


def test_server_failed_target_insert_is_reported_and_rolled_back():
    lua = runtime()
    lua.execute("""
        extract_result=5
        insert_queue={{error='target refused'},{inserted=5}}
        local receipt=storage.actions.transfer_item(1,'coal',
            1,1,'wooden-chest',3,3,'stone-furnace',5)
        assert(receipt.status=='failed')
        assert(receipt.inserted==0)
        assert(receipt.returned==5)
        assert(receipt.leftover==0)
        assert(string.find(tostring(receipt.error),'target refused')~=nil)
    """)


def test_server_extract_failure_and_zero_quantity():
    lua = runtime()
    lua.execute("""
        extract_error='no source items'
        local receipt=storage.actions.transfer_item(1,'coal',
            1,1,'wooden-chest',3,3,'stone-furnace',5)
        assert(receipt.status=='failed')
        assert(receipt.extracted==0)
        assert(string.find(tostring(receipt.error),'no source items')~=nil)

        local zero=storage.actions.transfer_item(1,'coal',
            1,1,'wooden-chest',3,3,'stone-furnace',0)
        assert(zero.status=='failed')
        assert(string.find(tostring(zero.error),'quantity')~=nil)
    """)


def test_client_partial_transfer_reports_returned_leftover():
    tool = TransferItem.__new__(TransferItem)
    tool.game_state = Mock()
    tool.game_state.extract_item.return_value = 5
    target_entity = Mock()
    target_entity.inserted = 2
    restore_entity = Mock()
    restore_entity.inserted = 3
    tool.game_state.insert_item.side_effect = [target_entity, restore_entity]
    source = Chest.model_construct(name="wooden-chest", position=Position(x=0, y=0))
    target = Chest.model_construct(name="iron-chest", position=Position(x=1, y=1))

    receipt = tool(Prototype.Coal, source, target, quantity=5)

    tool.game_state.extract_item.assert_called_once_with(Prototype.Coal, source, 5)
    assert tool.game_state.insert_item.call_count == 2
    tool.game_state.insert_item.assert_any_call(Prototype.Coal, source, 3)
    assert receipt["status"] == "partial"
    assert receipt["extracted"] == 5
    assert receipt["inserted"] == 2
    assert receipt["returned"] == 3
    assert receipt["leftover"] == 0


def test_client_without_entity_source_keeps_leftover_in_inventory():
    tool = TransferItem.__new__(TransferItem)
    tool.game_state = Mock()
    tool.game_state.extract_item.return_value = 5
    target_entity = Mock()
    target_entity.inserted = 2
    tool.game_state.insert_item.return_value = target_entity
    target = Chest.model_construct(name="iron-chest", position=Position(x=1, y=1))

    receipt = tool(Prototype.Coal, Position(x=0, y=0), target, 5)

    assert tool.game_state.insert_item.call_count == 1
    assert receipt["status"] == "partial"
    assert receipt["returned"] == 0
    assert receipt["leftover"] == 3


def test_client_target_failure_is_rolled_back_into_receipt():
    tool = TransferItem.__new__(TransferItem)
    tool.game_state = Mock()
    tool.game_state.extract_item.return_value = 4
    restore_entity = Mock()
    restore_entity.inserted = 1
    tool.game_state.insert_item.side_effect = [
        Exception("target refused"),
        restore_entity,
    ]
    source = Chest.model_construct(name="wooden-chest", position=Position(x=0, y=0))
    target = Chest.model_construct(name="iron-chest", position=Position(x=1, y=1))

    receipt = tool(Prototype.Coal, source, target, 4)

    assert receipt["status"] == "failed"
    assert receipt["inserted"] == 0
    assert receipt["returned"] == 1
    assert receipt["leftover"] == 3
    assert "target refused" in receipt["error"]


def test_client_raises_when_nothing_extracted():
    tool = TransferItem.__new__(TransferItem)
    tool.game_state = Mock()
    tool.game_state.extract_item.return_value = 0
    target = Chest.model_construct(name="iron-chest", position=Position(x=1, y=1))

    with pytest.raises(Exception, match="nothing extracted"):
        tool(Prototype.Coal, Position(x=0, y=0), target, 5)


def test_client_validates_arguments():
    tool = TransferItem.__new__(TransferItem)
    tool.game_state = Mock()
    target = Chest.model_construct(name="iron-chest", position=Position(x=1, y=1))
    with pytest.raises(AssertionError, match="Prototype"):
        tool("coal", Position(x=0, y=0), target, 5)
    with pytest.raises(AssertionError, match="quantity"):
        tool(Prototype.Coal, Position(x=0, y=0), target, 0)
    with pytest.raises(ValueError, match="source"):
        tool(Prototype.Coal, (0, 0), target, 5)
    with pytest.raises(ValueError, match="target"):
        tool(Prototype.Coal, Position(x=0, y=0), (1, 1), 5)
