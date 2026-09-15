import pytest

from fle.env.game_types import Prototype, Resource
from fle.env import Direction
from fle.commons.models.game_state import GameState


@pytest.fixture()
def game(instance):
    instance.initial_inventory = {
        "burner-mining-drill": 1,
        "iron-chest": 1,
        "wooden-chest": 1,
        "coal": 2000,
    }
    instance.reset()
    yield instance.namespace


def test_drop_box_chest(game):
    game.move_to(game.nearest(Resource.IronOre))
    drill = game.place_entity(
        Prototype.BurnerMiningDrill,
        Direction.UP,
        game.nearest(Resource.IronOre),
    )
    game.place_entity(Prototype.IronChest, Direction.UP, drill.drop_position)
    game.insert_item(Prototype.Coal, drill, 10)

    game.sleep(10)

    drill = game.get_entities({Prototype.BurnerMiningDrill})[0]

    state = GameState.from_instance(game.instance)

    game.instance.reset(state)

    drill = game.get_entities({Prototype.BurnerMiningDrill})[0]

    assert not drill.warnings


def test_full_chest(game):
    chest = game.place_entity(Prototype.WoodenChest, Direction.UP)
    for i in range(16):
        game.insert_item(Prototype.Coal, chest, 50)

    state = GameState.from_instance(game.instance)

    game.instance.reset(state)

    chest = game.get_entities({Prototype.WoodenChest})[0]

    assert chest.warnings[0] == "chest is full"
