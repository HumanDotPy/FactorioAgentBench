from typing import Union

from fle.env.entities import Entity, Position
from fle.env.tools import Tool


class Refuel(Tool):
    def __call__(self, entity: Union[Entity, Position]) -> dict:
        """
        Top up a burner entity's fuel slot from the player's inventory.

        The fuel is chosen from the player's inventory by the highest
        `fuel_value`, then by the largest available quantity when values are
        equal. When the fuel slot already holds a fuel type, only that type is
        used, so the slot is never mixed. The call fills at most the space
        left in the slot and leaves your inventory shortfall untouched.
        Fuelable entities are burner machines and vehicles: burner inserter,
        burner mining drill, stone/steel furnace, boiler, burner generator,
        car, tank and locomotive; anything else raises with that list.

        :param entity: Entity or Position of the burner to refuel
        :return: {status, entity, fuel, inserted, remaining_fuel, available}.
            `status` is "refueled", "fuel_full", "fuel_mismatch" (slot holds
            a fuel type you do not carry), "no_fuel" (no fuel in inventory) or
            "blocked" (the slot refused the insert). `fuel` is the chosen or
            blocking fuel name, `inserted` how many units moved, `remaining_fuel`
            the units the slot can still take and `available` the units of
            `fuel` that were in your inventory before the call.
        :example refuel(burner_mining_drill)
        :example refuel(furnace.position)
        """
        if not isinstance(entity, (Entity, Position)):
            raise Exception(
                "The argument must be an Entity or Position, you passed in a {0}".format(
                    type(entity)
                )
            )

        if isinstance(entity, Position):
            x, y = self.get_position(entity)
            entity_name = None
        else:
            x, y = self.get_position(entity.position)
            entity_name = entity.name

        self.ensure_reachable(entity)

        response, elapsed = self.execute(self.player_index, x, y, entity_name)
        if isinstance(response, str):
            raise Exception(f"Could not refuel: {self.get_error_message(response)}")
        if not isinstance(response, dict) or "status" not in response:
            raise Exception("Could not refuel: the game did not report a fuel status")

        receipt = self.clean_response(response)
        for key in ("entity", "fuel", "inserted", "remaining_fuel", "available"):
            receipt.setdefault(key, None)
        return receipt
