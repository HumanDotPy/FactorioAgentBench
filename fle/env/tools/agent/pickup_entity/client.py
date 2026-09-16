from typing import Union, Optional

from fle.env import entities as ent
from fle.env.game_types import Prototype
from fle.env.tools import Tool


class PickupEntity(Tool):
    def __init__(self, *args):
        super().__init__(*args)

    def _pickup_group(self, members):
        partial = None
        for member in members:
            resp = self.__call__(member)
            if not resp:
                return False
            if isinstance(resp, dict):
                leftovers = resp.get("leftovers")
                if isinstance(leftovers, dict):
                    leftovers = list(leftovers.values())
                if leftovers:
                    partial = resp
        return partial or True

    def _validate_response(self, response):
        if isinstance(response, str):
            raise Exception(f"Could not pickup: {self.get_error_message(response)}")
        if isinstance(response, dict):
            if response.get("error"):
                raise Exception(
                    f"Could not pickup: {self.get_error_message(response['error'])}"
                )
            leftovers = response.get("leftovers")
            if isinstance(leftovers, dict):
                leftovers = list(leftovers.values())
            if leftovers and not response.get("picked_up"):
                remaining = sum(
                    int(entry.get("count", 0))
                    for entry in leftovers
                    if isinstance(entry, dict)
                )
                raise Exception(
                    "Could not pickup: inventory is full; "
                    f"{remaining} items left on the ground"
                )
            return response
        if response != 1 and response != {}:
            raise Exception(f"Could not pickup: {self.get_error_message(response)}")
        return True

    def __call__(
        self,
        entity: Optional[Union[ent.Entity, Prototype, ent.EntityGroup]] = None,
        position: Optional[ent.Position] = None,
    ) -> Union[bool, dict]:
        """
        Pick up an entity, an entity group, or stacks lying on the ground.
        :param entity: Entity/Prototype to pick up, e.g Prototype.IronPlate.
            Ground stacks are filtered by this name and, when the entity
            carries one, by quality. Pass None with a position to pick up
            every ground stack at that position instead.
        :param position: Position to pick up from (required for Prototypes and
            for an empty-hand ground sweep)
        :return: A receipt ({status, requested, picked_up, leftovers}) when the
            game reports one, True for legacy success, False otherwise. A
            partial pickup keeps status="partial" and lists what stayed behind
            in leftovers instead of destroying the whole stack.
        """
        if entity is None:
            if not isinstance(position, ent.Position):
                raise ValueError(
                    "pickup_entity without an entity target requires a "
                    "position: pickup_entity(position=Position(x, y)) picks up "
                    "every ground stack at that position"
                )
            self.ensure_reachable(position)
            response, elapsed = self.execute(
                self.player_index, position.x, position.y, None, None
            )
            return self._validate_response(response)

        if not isinstance(entity, (Prototype, ent.Entity, ent.EntityGroup)):
            raise ValueError("The first argument must be an Entity or Prototype object")
        if isinstance(entity, ent.Entity) and isinstance(position, ent.Position):
            raise ValueError(
                "If the first argument is an Entity object, the second argument must be None"
            )
        if position is not None and not isinstance(position, ent.Position):
            raise ValueError("The second argument must be a Position object")

        quality = getattr(entity, "quality", None)
        if isinstance(quality, dict):
            quality = quality.get("name")
        if quality is not None:
            quality = str(quality)

        if isinstance(entity, Prototype):
            name, _ = entity.value
        else:
            name = entity.name
            if isinstance(entity, ent.BeltGroup):
                return self._pickup_group(entity.belts)
            elif isinstance(entity, ent.PipeGroup):
                return self._pickup_group(entity.pipes)
            elif isinstance(entity, ent.ElectricityGroup):
                return self._pickup_group(entity.poles)

        if position is not None:
            x, y = position.x, position.y
            self.ensure_reachable(position)
            response, elapsed = self.execute(self.player_index, x, y, name, quality)
        elif isinstance(entity, ent.UndergroundBelt):
            self.ensure_reachable(entity)
            x, y = entity.position.x, entity.position.y
            response, elapsed = self.execute(self.player_index, x, y, name, quality)
            self._validate_response(response)

            x, y = entity.output_position.x, entity.output_position.y
            response, elapsed = self.execute(self.player_index, x, y, name, quality)
        elif isinstance(entity, ent.Entity):
            x, y = entity.position.x, entity.position.y
            self.ensure_reachable(entity)
            response, elapsed = self.execute(self.player_index, x, y, name, quality)
        else:
            raise ValueError("The second argument must be a Position object")

        return self._validate_response(response)
