from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fle.env.tools.agent.blueprint.client import Blueprint
from fle.envd.blueprint_exchange import decode_exchange, encode_exchange
from fle.envd.blueprints import BlueprintStore

pytestmark = pytest.mark.no_factorio

DOCUMENT = {
    "blueprint": {
        "item": "blueprint",
        "version": 562949958467584,
        "entities": [
            {
                "entity_number": 1,
                "name": "transport-belt",
                "position": {"x": 0.5, "y": 0.5},
                "direction": 4,
            }
        ],
    }
}
PLANNER = {
    "deconstruction_planner": {
        "item": "deconstruction-planner",
        "version": 562949958467584,
        "settings": {"trees_and_rocks_only": True},
    }
}
BOOK = {
    "blueprint_book": {
        "item": "blueprint-book",
        "version": 562949958467584,
        "blueprints": [
            {"index": 0, **DOCUMENT},
            {"index": 3, **PLANNER},
        ],
    }
}
CAPTURE = {
    "blueprint": '"0captured"',
    "entity_count": 2,
    "tile_count": 7,
    "bytes": 42,
    "center_x": 1.0,
    "center_y": -2.0,
}


def make_tool(store=None, response=None):
    tool = Blueprint.__new__(Blueprint)
    tool.name = "blueprint"
    tool.player_index = 1
    tool.connection = Mock()
    tool.game_state = SimpleNamespace(
        instance=SimpleNamespace(get_elapsed_ticks=Mock(return_value=123)),
        _ephemeral_blueprints=store or BlueprintStore(scope=None),
    )
    tool.execute = Mock(return_value=(response, None))
    return tool


def test_save_receipt_includes_tile_count_bytes_and_tick():
    tool = make_tool(response=CAPTURE)
    receipt = tool.save("line", 0, 0, 16)
    assert receipt["saved"] == "line"
    assert receipt["tile_count"] == 7
    assert receipt["bytes"] == 42
    assert receipt["created_tick"] == 123
    tool.execute.assert_called_once_with(
        1, "capture", 0, 0, 16, {"include_tiles": True}
    )


def test_save_can_omit_tiles():
    tool = make_tool(response=CAPTURE)
    tool.save("outpost", 0, 0, 100, include_tiles=False)
    tool.execute.assert_called_once_with(
        1, "capture", 0, 0, 100, {"include_tiles": False}
    )


def test_place_unknown_name_reports_not_found():
    tool = make_tool(response={"status": "ghosts_created"})
    result = tool.place("ghost-name", 0, 0)
    assert "No blueprint named" in result["error"]
    tool.execute.assert_not_called()


def test_place_inline_exchange_string_still_works():
    tool = make_tool(response={"status": "ghosts_created", "created_ghosts": 1})
    result = tool.place(encode_exchange(DOCUMENT), 4, 5, direction=4)
    assert result["source"] == "inline"
    tool.execute.assert_called_once()


def test_place_rejects_a_planner_leaf():
    tool = make_tool(response={"status": "ghosts_created"})
    result = tool.place(encode_exchange(PLANNER), 0, 0)
    assert "not a blueprint" in result["error"]
    tool.execute.assert_not_called()


def test_apply_selects_planner_from_book():
    tool = make_tool(response={"status": "orders_requested"})
    result = tool.apply(encode_exchange(BOOK), 0, 0, radius=8, book_path=[3])
    assert result["status"] == "orders_requested"
    sent = tool.execute.call_args.args[2]
    assert decode_exchange(sent) == PLANNER


def test_apply_unknown_name_reports_not_found():
    tool = make_tool(response={"status": "orders_requested"})
    result = tool.apply("missing-planner", 0, 0)
    assert "No blueprint named" in result["error"]
    tool.execute.assert_not_called()


def test_stored_blueprint_records_use_on_place():
    store = BlueprintStore(scope=None)
    store.save("line", encode_exchange(DOCUMENT))
    tool = make_tool(
        store=store, response={"status": "ghosts_created", "created_ghosts": 1}
    )
    result = tool.place("line", 0, 0)
    assert result["source"] == "library"
    assert store.get("line").times_placed == 1
