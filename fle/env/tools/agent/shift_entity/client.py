from typing import NoReturn

from fle.env import DirectionInternal as DirectionA
from fle.env.entities import Direction, Entity, Position
from fle.env.game_types import prototype_by_name
from fle.env.tools import Tool
from fle.env.tools.agent.can_place_entity.client import CanPlaceEntity
from fle.env.tools.agent.pickup_entity.client import PickupEntity
from fle.env.tools.agent.place_entity.client import PlaceObject as PlaceEntity

CARDINAL_OFFSETS = {
    Direction.NORTH.value: (0.0, -1.0),
    Direction.EAST.value: (1.0, 0.0),
    Direction.SOUTH.value: (0.0, 1.0),
    Direction.WEST.value: (-1.0, 0.0),
}


class ShiftEntity(Tool):
    def __init__(self, connection, game_state):
        self.game_state = game_state
        super().__init__(connection, game_state)
        self.can_place_entity = CanPlaceEntity(connection, game_state)
        self.place_entity = PlaceEntity(connection, game_state)
        self.pickup_entity = PickupEntity(connection, game_state)

    def __call__(
        self, entity: Entity, direction: Direction | DirectionA, distance: int = 1
    ) -> Entity:
        """
        Move a placed entity by a whole number of tiles in one cardinal direction.
        :param entity: Entity to move
        :param direction: Cardinal direction to move the entity
        :param distance: Number of tiles to move
        :return: The moved entity
        """
        assert isinstance(entity, Entity), "First argument must be an entity object"
        if not isinstance(direction, (Direction, DirectionA)):
            raise ValueError("Second argument must be a direction")
        if isinstance(distance, bool) or not isinstance(distance, int) or distance < 1:
            raise ValueError("distance must be a positive integer")

        offset = CARDINAL_OFFSETS.get(direction.value)
        if offset is None:
            raise ValueError(
                f"direction must be cardinal (UP/RIGHT/DOWN/LEFT); got {direction}"
            )

        original_position = Position(x=entity.position.x, y=entity.position.y)
        target_position = Position(
            x=original_position.x + offset[0] * distance,
            y=original_position.y + offset[1] * distance,
        )

        if original_position == target_position:
            return entity

        prototype = prototype_by_name.get(entity.name)
        if prototype is None:
            raise ValueError(f"Unknown prototype for entity {entity.name!r}")

        try:
            picked_up = self.pickup_entity(entity)
        except Exception as error:
            raise Exception(
                f"Could not shift {entity.name}: initial pickup failed: {error}"
            ) from error
        if not picked_up:
            raise Exception(f"Could not shift {entity.name}: initial pickup failed")

        if not self.can_place_entity(prototype, entity.direction, target_position):
            return self._restore(
                prototype,
                entity,
                original_position,
                target_position,
                "destination is blocked",
            )

        try:
            return self.place_entity(prototype, entity.direction, target_position)
        except Exception as placement_error:
            return self._restore(
                prototype,
                entity,
                original_position,
                target_position,
                str(placement_error),
            )

    def _restore(
        self,
        prototype,
        entity: Entity,
        original_position: Position,
        target_position: Position,
        failure: str,
    ) -> NoReturn:
        try:
            self.place_entity(prototype, entity.direction, original_position)
        except Exception as restore_error:
            raise Exception(
                f"Could not shift {entity.name} to {target_position} ({failure}); "
                f"restoring it at {original_position} also failed ({restore_error}). "
                f"The {entity.name} remains in the inventory as an item at the agent's position; "
                "place it manually."
            ) from restore_error
        raise Exception(
            f"Could not shift {entity.name} to {target_position} ({failure}); "
            f"it was restored at {original_position}."
        )
