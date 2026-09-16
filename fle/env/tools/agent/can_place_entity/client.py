from fle.env import entities as ent
from fle.env.game_types import Prototype
from fle.env.tools import Tool


class CanPlaceEntity(Tool):
    def __init__(self, *args):
        super().__init__(*args)

    def __call__(
        self,
        entity: Prototype,
        direction: ent.Direction = ent.Direction.UP,
        position: ent.Position = ent.Position(x=0, y=0),
    ) -> bool:
        """
        Tests to see if an entity can be placed at a given position
        :param entity: Entity to place from inventory
        :param direction: Cardinal direction to place entity
        :param position: Position to place entity
        :return: True if entity can be placed at position, else False
        """

        if not isinstance(entity, Prototype):
            raise ValueError("entity must be a Prototype")
        if not isinstance(direction, ent.Direction):
            raise ValueError("direction must be a Direction")

        # If position is a tuple, cast it to a Position object:
        if isinstance(position, tuple):
            position = ent.Position(x=position[0], y=position[1])

        if not isinstance(position, ent.Position):
            raise ValueError("position must be a Position or (x, y) tuple")

        x, y = self.get_position(position)
        name, metaclass = entity.value

        response, elapsed = self.execute(self.player_index, name, direction.value, x, y)

        if isinstance(response, bool):
            return response
        if isinstance(response, dict):
            if response.get("error"):
                raise ValueError(str(response.get("message") or response.get("error")))
            if "placeable" in response:
                return bool(response["placeable"])
            return False
        if isinstance(response, str):
            raise ValueError(response.strip() or "placement probe failed")
        return False
