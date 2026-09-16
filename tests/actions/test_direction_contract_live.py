"""Live direction-contract check; runs only with ``-m factorio_live``.

Places rotatable prototypes in all four directions and asserts the read-back
geometry matches the agent-facing convention: inserter directions name the
DROP side, drill directions name the drop side, belt directions name the flow.
"""

from fle.env.entities import Direction, Position
from fle.env.game_types import Prototype

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
INSERTERS = (
    Prototype.BurnerInserter,
    Prototype.Inserter,
    Prototype.FastInserter,
    Prototype.LongHandedInserter,
    Prototype.BulkInserter,
)
BELTS = (
    Prototype.TransportBelt,
    Prototype.FastTransportBelt,
    Prototype.ExpressTransportBelt,
)


def _side(origin, point, tolerance=1.0):
    dx = point.x - origin.x
    dy = point.y - origin.y
    if abs(dx) >= abs(dy):
        return Direction.EAST if dx >= 0 else Direction.WEST
    return Direction.SOUTH if dy >= 0 else Direction.NORTH


def test_live_inserter_drop_side_and_rotation(configure_game):
    game = configure_game(
        inventory={
            "burner-inserter": 40,
            "fast-inserter": 40,
            "inserter": 40,
            "long-handed-inserter": 40,
            "bulk-inserter": 40,
        }
    )
    origin = Position(x=200, y=200)
    game.move_to(origin)
    index = 0
    for prototype in INSERTERS:
        for direction in CARDINALS:
            position = Position(x=origin.x + index * 3, y=origin.y)
            game.move_to(position)
            entity = game.place_entity(
                prototype, direction=direction, position=position
            )
            assert _side(entity.position, entity.drop_position) == direction, (
                prototype,
                direction,
                entity,
            )
            opposite = Direction((direction.value + 8) % 16)
            assert _side(entity.position, entity.pickup_position) == opposite
            rotated = game.rotate_entity(entity, opposite)
            assert _side(rotated.position, rotated.drop_position) == opposite
            assert rotated.pickup_position is not None
            index += 1


def test_live_belt_flow_matches_direction(configure_game):
    game = configure_game(
        inventory={
            "transport-belt": 40,
            "fast-transport-belt": 40,
            "express-transport-belt": 40,
        }
    )
    origin = Position(x=200, y=220)
    game.move_to(origin)
    index = 0
    for prototype in BELTS:
        for direction in CARDINALS:
            position = Position(x=origin.x + index * 3, y=origin.y)
            game.move_to(position)
            belt = game.place_entity(prototype, direction=direction, position=position)
            assert belt.direction == direction
            assert _side(belt.position, belt.output_position) == direction
            index += 1
