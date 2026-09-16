from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from lupa.lua54 import LuaRuntime
import pytest

from fle.env.entities import Direction, Furnace, Position
from fle.env.game_types import Prototype, RecipeName
from fle.env.tools.agent.inspect_inventory.client import (
    CrafterInventory,
    InspectInventory,
)


@pytest.fixture()
def game(configure_game):
    return configure_game(
        inventory={
            "coal": 50,
            "iron-chest": 1,
            "iron-plate": 5,
        },
        merge=True,
        all_technologies_researched=False,
    )


def test_inspect_inventory(game):
    assert game.inspect_inventory().get(Prototype.Coal, 0) == 50
    inventory = game.inspect_inventory()
    coal_count = inventory[Prototype.Coal]
    assert coal_count != 0
    chest = game.place_entity(Prototype.IronChest, position=Position(x=0, y=0))
    chest = game.insert_item(Prototype.Coal, chest, quantity=5)

    chest_inventory = game.inspect_inventory(entity=chest)
    chest_coal_count = chest_inventory[Prototype.Coal]
    assert chest_coal_count == 5


@pytest.mark.no_factorio
def test_crafter_input_and_output_stacks_stay_separate():
    lua = LuaRuntime()
    lua.execute("""
        storage={actions={},utils={},agent_characters={}}
        defines={inventory={crafter_input=1,crafter_output=2,lab_input=3,chest=4}}
        storage.utils.get_contents_compat=function(inventory)
            return inventory.contents
        end
        storage.utils.ensure_valid_character=function() return player end
        player={get_main_inventory=function() return {valid=true} end}
        surface={find_entities_filtered=function(query)
            return {machine}
        end}
        player.surface=surface
        machine={name='stone-furnace', type='furnace', valid=true,
            position={x=1,y=1},
            get_inventory=function(kind)
                if kind==1 then return {contents={['iron-ore']=5}} end
                if kind==2 then return {contents={['iron-plate']=2}} end
                return nil
            end}
        storage.agent_characters[1]=player
    """)
    lua.execute(
        (
            Path(__file__).parents[2]
            / "fle/env/tools/agent/inspect_inventory/server.lua"
        ).read_text()
    )
    result = lua.execute("""
        local result=storage.actions.inspect_inventory(1,false,1,1,'stone-furnace')
        assert(result.items['iron-ore']==5 and result.items['iron-plate']==2)
        assert(result.input_inventory['iron-ore']==5)
        assert(result.input_inventory['iron-plate']==nil)
        assert(result.output_inventory['iron-plate']==2)
        assert(result.output_inventory['iron-ore']==nil)
        return 'ok'
    """)
    assert result == "ok"


@pytest.mark.no_factorio
def test_client_returns_labeled_crafter_inventory():
    tool = InspectInventory.__new__(InspectInventory)
    tool.player_index = 1
    tool.name = "inspect_inventory"
    tool.game_state = SimpleNamespace(_program_runtime=None)
    tool.execute = Mock(
        return_value=(
            {
                "items": {"iron-ore": 5, "iron-plate": 2},
                "input_inventory": {"iron-ore": 5},
                "output_inventory": {"iron-plate": 2},
            },
            0,
        )
    )
    furnace = Furnace(
        name="stone-furnace",
        direction=Direction.NORTH,
        position=Position(x=1, y=1),
        energy=0.0,
        health=100.0,
        dimensions={"width": 2, "height": 2},
        tile_dimensions={"tile_width": 2, "tile_height": 2},
    )
    result = tool(entity=furnace)
    assert isinstance(result, CrafterInventory)
    assert result[Prototype.IronOre] == 5
    assert result[Prototype.IronPlate] == 2
    assert result.input_inventory[Prototype.IronOre] == 5
    assert result.input_inventory[Prototype.IronPlate] == 0
    assert result.output_inventory[Prototype.IronPlate] == 2
    assert result.output_inventory[Prototype.IronOre] == 0


@pytest.mark.no_factorio
def test_client_raises_instead_of_returning_empty_inventory_on_failure():
    tool = InspectInventory.__new__(InspectInventory)
    tool.player_index = 1
    tool.name = "inspect_inventory"
    tool.game_state = SimpleNamespace(_program_runtime=None)
    tool.execute = Mock(return_value=("Error: no player", 0))
    with pytest.raises(Exception, match="Could not inspect player inventory"):
        tool()


def test_inspect_assembling_machine_inventory(game):
    machine = game.place_entity(
        Prototype.AssemblingMachine1, position=Position(x=0, y=0)
    )
    game.set_entity_recipe(machine, RecipeName.IronGearWheel)
    game.insert_item(Prototype.IronPlate, machine, quantity=5)
    chest_inventory = game.inspect_inventory(entity=machine)
    iron_count = chest_inventory[Prototype.IronPlate]
    assert iron_count == 5
