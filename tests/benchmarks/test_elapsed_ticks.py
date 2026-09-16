import pytest

from fle.env.game_types import Prototype, Resource


@pytest.fixture()
def game(instance):
    instance.initial_inventory = {
        "iron-plate": 400,
        "iron-gear-wheel": 1,
        "electronic-circuit": 3,
        "pipe": 1,
        "copper-plate": 100,
    }

    instance.reset(all_technologies_researched=True)
    instance.set_speed(100)

    yield instance.namespace


def test_crafting_composite_accumulate_ticks(game):
    """
    Test that crafting a composite item (with auto-crafted prerequisites) takes the same
    number of ticks as manually crafting the prerequisites first.
    :param game:
    :return:
    """
    # First approach: craft electronic circuits directly (auto-crafts copper cable)
    game.instance._reset_elapsed_ticks()
    game.craft_item(Prototype.ElectronicCircuit, quantity=10)
    ticks_auto = game.instance.get_elapsed_ticks()

    # Reset game state and elapsed ticks
    game.instance.reset(all_technologies_researched=True)
    game.instance._reset_elapsed_ticks()

    # Second approach: manually craft copper cable first, then electronic circuits
    game.craft_item(Prototype.CopperCable, quantity=10)
    game.craft_item(Prototype.ElectronicCircuit, quantity=10)
    ticks_manual = game.instance.get_elapsed_ticks()

    assert ticks_manual == ticks_auto, (
        f"The tick count should be invariant to whether the prerequisites are intentionally crafted or not. "
        f"Auto: {ticks_auto}, Manual: {ticks_manual}"
    )


def test_harvesting_wood_accumulate_ticks(game):
    wood_pos = game.nearest(Resource.Wood)
    if wood_pos is None:
        pytest.skip("No wood (trees) available in the test environment")

    game.move_to(wood_pos)
    game.instance._reset_elapsed_ticks()

    # Harvest smaller quantities to avoid exhausting a single tree
    game.harvest_resource(game.nearest(Resource.Wood), quantity=5)
    ticks = game.instance.get_elapsed_ticks()

    # Find nearest wood again (may have moved to another tree if first was exhausted)
    wood_pos2 = game.nearest(Resource.Wood)
    if wood_pos2 is None:
        pytest.skip("Insufficient wood resources in the test environment")

    game.harvest_resource(wood_pos2, quantity=5)
    nticks = game.instance.get_elapsed_ticks()

    assert ticks > 25, f"Expected ticks > 25 but got {ticks}"
    assert nticks - ticks == ticks, (
        f"The tick count should be proportional to the amount of wood harvested. "
        f"First harvest: {ticks} ticks, second: {nticks - ticks} ticks"
    )


def test_long_mine(game):
    game.move_to(game.nearest(Resource.Coal))
    game.instance._reset_elapsed_ticks()

    for i in range(100):
        game.harvest_resource(game.nearest(Resource.Coal), quantity=10)

    ticks = game.instance.get_elapsed_ticks()
    assert ticks == 60000
