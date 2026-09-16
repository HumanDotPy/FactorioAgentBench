import pytest
from lupa.lua54 import LuaError

from fle.env.game_types import Prototype
from tests.actions.lua_stub_helpers import load_env, lua_stub

CRAFT_STUB = """
    game = {tick = 0, surfaces = {}}
    storage = {
        actions = {},
        utils = {},
        agent_characters = {},
        elapsed_ticks = 0,
        crafted_items = {},
    }
    prototypes = {item = {}}
    inventory = {}
    for i = 1, 40 do
        inventory[i] = {valid_for_read = false}
    end
    local function recipe(name, product_amount, ingredients)
        return {
            name = name,
            enabled = true,
            category = "crafting",
            energy = 0.5,
            products = {{name = name, type = "item", amount = product_amount}},
            ingredients = ingredients,
        }
    end
    recipes = {
        ["iron-chest"] = recipe("iron-chest", 1, {{name = "iron-plate", type = "item", amount = 8}}),
        ["iron-gear-wheel"] = recipe("iron-gear-wheel", 1, {{name = "iron-plate", type = "item", amount = 2}}),
        ["copper-cable"] = recipe("copper-cable", 2, {{name = "copper-plate", type = "item", amount = 1}}),
        ["gear-case"] = recipe("gear-case", 1, {{name = "iron-gear-wheel", type = "item", amount = 1}}),
    }
    for name in pairs(recipes) do
        prototypes.item[name] = {stack_size = 100}
    end
    prototypes.item["iron-plate"] = {stack_size = 100}
    prototypes.item["copper-plate"] = {stack_size = 100}
    character = {
        valid = true,
        position = {x = 0, y = 0},
        prototype = {crafting_categories = {crafting = true}},
        force = {
            recipes = recipes,
            technologies = {},
            get_item_production_statistics = function(surface)
                return {on_flow = function() end}
            end,
        },
        get_item_count = function(name) return counts[name] or 0 end,
        get_main_inventory = function() return inventory end,
        remove_item = function(item)
            counts[item.name] = math.max(0, (counts[item.name] or 0) - item.count)
        end,
        insert = function(item) return item.count end,
    }
    character.surface = {spill_item_stack = function() end}
    storage.agent_characters[1] = character
    storage.utils.ensure_valid_character = function() return character end
    storage.utils.begin_native_crafting = function(_, name, count) return queued end
"""


def craft_runtime(*, counts=None, fast=True, queued=None):
    lua = lua_stub(CRAFT_STUB, unpack=True)
    lua.globals().counts = lua.table_from(counts or {})
    lua.globals().storage.fast = fast
    lua.globals().queued = queued
    load_env(lua, "tools/agent/craft_item/server.lua")
    return lua


@pytest.fixture()
def game(configure_game):
    return configure_game(
        inventory={
            "iron-plate": 40,
            "iron-gear-wheel": 1,
            "electronic-circuit": 3,
            "pipe": 1,
            "copper-plate": 10,
        }
    )


def test_fail_to_craft_item(game):
    """
    Attempt to craft an iron chest with insufficient resources and assert that no items are crafted.
    :param game:
    :return:
    """
    with pytest.raises(Exception):
        game.craft_item(Prototype.IronChest, quantity=100)


def test_craft_with_full_inventory(game):
    """
    Test crafting when inventory is full
    """
    game._set_inventory({"iron-plate": 100, "coal": 10000})
    with pytest.raises(Exception):
        game.craft_item(Prototype.IronGearWheel, 1)


def test_craft_item(game):
    """
    Craft an iron chest and assert that the iron plate has been deducted and the iron chest has been added.
    :param game:
    :return:
    """
    quantity = 5
    iron_cost = 8
    # Check initial inventory
    initial_iron_plate = game.inspect_inventory()[Prototype.IronPlate]
    initial_iron_chest = game.inspect_inventory()[Prototype.IronChest]

    # Craft an iron chest
    game.craft_item(Prototype.IronChest, quantity=quantity)

    # Check the inventory after crafting
    final_iron_plate = game.inspect_inventory()[Prototype.IronPlate]
    final_iron_chest = game.inspect_inventory()[Prototype.IronChest]

    # Assert that the iron plate has been deducted and the iron chest has been added
    assert initial_iron_plate - final_iron_plate == iron_cost * quantity
    assert initial_iron_chest + quantity == final_iron_chest


def test_recursive_crafting(game):
    crafted_circuits = game.craft_item(Prototype.ElectronicCircuit, quantity=4)
    assert crafted_circuits


def test_craft_copper_coil(game):
    """
    Craft 20 copper cable and verify that only 10 copper plates have been deducted.
    :param game:
    :return:
    """

    # Craft an iron chest with insufficient resources
    # Check initial inventory
    initial_copper_plate = game.inspect_inventory()[Prototype.CopperPlate]
    initial_copper_coil = game.inspect_inventory()[Prototype.CopperCable]

    # Craft 20 copper coil
    game.craft_item(Prototype.CopperCable, quantity=20)

    # Check the inventory after crafting
    final_copper_plate = game.inspect_inventory()[Prototype.CopperPlate]
    final_copper_coil = game.inspect_inventory()[Prototype.CopperCable]

    # Assert that only 10 copper plates have been deducted
    assert initial_copper_plate - 10 == final_copper_plate
    assert initial_copper_coil + 20 == final_copper_coil


def test_craft_entity_with_missing_intermediate_resources(game):
    """
    Some entities like offshore pumps require intermediate resources, which we may also need to craft.
    :param game:
    :return:
    """
    # Craft 20 copper coil
    crafted = game.craft_item(Prototype.ElectronicCircuit, quantity=1)

    assert crafted == 1


def test_craft_no_technology(game):
    game.instance.reset(all_technologies_researched=False)
    try:
        game.craft_item(Prototype.AssemblingMachine1, quantity=1)
    except:
        assert True
        return
    assert False, "Should not be able to craft without technology."


@pytest.mark.no_factorio
def test_non_fast_craft_failure_names_missing_ingredients():
    lua = craft_runtime(counts={"iron-plate": 25}, fast=False, queued=0)
    with pytest.raises(LuaError) as error:
        lua.execute("storage.actions.craft_item(1, 'iron-chest', 5)")
    message = str(error.value)
    assert "Unable to begin crafting" in message
    assert "inspect ingredients and inventory space" in message
    assert "iron-plate" in message


@pytest.mark.no_factorio
def test_fast_sub_ingredient_failure_names_parent_and_child_missing():
    lua = craft_runtime(counts={}, fast=True)
    with pytest.raises(LuaError) as error:
        lua.execute("storage.actions.craft_item(1, 'gear-case', 1)")
    message = str(error.value)
    assert "couldn't craft a required sub-ingredient" in message
    assert "iron-gear-wheel" in message
    assert "iron-plate" in message


@pytest.mark.no_factorio
def test_fast_still_missing_names_parent_and_child_missing():
    lua = craft_runtime(counts={"iron-plate": 2}, fast=True)
    with pytest.raises(LuaError) as error:
        lua.execute("storage.actions.craft_item(1, 'gear-case', 1)")
    message = str(error.value)
    assert "still missing ingredients" in message
    assert "iron-gear-wheel" in message
    assert "iron-plate" in message
