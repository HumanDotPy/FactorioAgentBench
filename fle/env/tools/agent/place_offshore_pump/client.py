import json

from fle.env import DirectionInternal, Direction
from fle.env.entities import Position, Entity
from fle.env.game_types import Prototype
from fle.env.tools import Tool
from fle.env.tools.spatial import normalize_spatial


class PlaceOffshorePump(Tool):
    def __init__(self, *args):
        super().__init__(*args)
        self.name = "place_offshore_pump"
        self.load()

    def __call__(
        self,
        preferred_position: Position,
        direction: Direction = Direction.UP,
    ) -> Entity:
        """
        Snap an offshore pump to the nearest shoreline within reach and place it
        facing the water. The returned entity reports the placed position and
        the engine direction (toward the intake).

        :param preferred_position: Position to search outward from
        :param direction: Optional preferred water side; the engine direction is
            always derived from where the water actually is
        :return: Entity object
        """
        if isinstance(preferred_position, tuple):
            preferred_position = Position(
                x=preferred_position[0], y=preferred_position[1]
            )
        if not isinstance(preferred_position, Position):
            raise ValueError("The position argument must be a Position object")
        if not isinstance(direction, (DirectionInternal, Direction)):
            raise ValueError("The second argument must be a Direction object")

        x, y = self.get_position(preferred_position)
        self.ensure_reachable(preferred_position)

        name, metaclass = Prototype.OffshorePump.value
        factorio_direction = DirectionInternal.to_factorio_direction(direction)

        try:
            response, elapsed = self.execute(
                self.player_index, x, y, factorio_direction
            )
        except Exception as error:
            raise RuntimeError(
                f"Could not place {name} near ({x}, {y}): {error}"
            ) from error

        if not isinstance(response, dict):
            raise RuntimeError(f"Could not place {name} near ({x}, {y}): {response}")
        if response.get("error"):
            raise RuntimeError(json.dumps(normalize_spatial(response), sort_keys=True))
        cleaned_response = self.clean_response(response)
        return metaclass(prototype=name, game=self.connection, **cleaned_response)
