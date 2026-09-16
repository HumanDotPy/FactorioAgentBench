import pytest

from fle.env.utils.rcon import (
    LuaConversionError,
    _lua2python,
    _remove_numerical_keys,
)

pytestmark = pytest.mark.no_factorio

# Exactly what the game serializer emits: every quote is backslash-escaped and
# the payload keeps its embedded newline. Build it from character codes so the
# test stays independent of editor/tool escape handling.
QUOTED_DETAIL = '"deliver:' + chr(92) + "n" + chr(92) + '"now' + chr(92) + '""'


def test_lua_2python_reads_the_complete_table():
    response = 'console: { ["a"] = false,["b"] = ["string global"],}'
    output, _ = _lua2python("cmd", response)
    assert output == {"a": False, "b": "string global", 2: "]"}

    response = (
        'console: { ["a"] = true,["b"] = ["line one"]}\n'
        'trace: { ["a"] = false,["b"] = ["stale"]}'
    )
    output, _ = _lua2python("cmd", response)
    assert output == {"a": False, "b": "stale", 2: "]"}


def test_lua_2python_decodes_tables_spanning_multiple_lines():
    response = (
        "\n{\n"
        ' ["a"] = true,\n'
        ' ["b"] = {\n'
        '  ["name"] = "iron-plate",\n'
        '  ["count"] = 2,\n'
        " },\n"
        "}\n"
    )
    output, _ = _lua2python("cmd", response)
    assert output["b"] == {"name": "iron-plate", "count": 2}


def test_lua_2python_keeps_quoted_string_accessors():
    response = 'dump: { ["a"] = true,["b"] = {["detail"] = ' + QUOTED_DETAIL + "} }"
    output, _ = _lua2python("cmd", response)
    detail = output["b"]["detail"]
    assert "deliver:" in detail
    assert '"now"' in detail


def test_lua_2python_raises_on_mixed_positional_and_named_keys():
    with pytest.raises(LuaConversionError, match="mixes positional"):
        _remove_numerical_keys({1: "left", "name": "right"})


def test_lua_2python_returns_none_without_a_payload():
    output, _ = _lua2python("cmd", "not a lua table")
    assert output is None


def test_remove_numerical_keys_recurses_into_named_values():
    value = {
        "entities": {"1": {"name": "burner-inserter"}, "2": {"name": "chest"}},
        "ground_items": [],
        "skipped": 0,
    }
    converted = _remove_numerical_keys(value)
    assert converted["entities"] == [
        {"name": "burner-inserter"},
        {"name": "chest"},
    ]
    assert converted["skipped"] == 0

    int_keyed = {"entities": {1: {"name": "a"}, 2: {"name": "b"}}}
    assert _remove_numerical_keys(int_keyed)["entities"] == [
        {"name": "a"},
        {"name": "b"},
    ]

    nested_list = {"rows": [{"1": "x", "2": "y"}]}
    assert _remove_numerical_keys(nested_list)["rows"] == [["x", "y"]]
