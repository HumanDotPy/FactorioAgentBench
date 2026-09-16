from typing import Union

from fle.env.entities import Entity, EntityGroup, Position, BeltGroup, PipeGroup
from fle.env.game_types import Prototype
from fle.env.tools.agent.get_entities.client import GetEntities
from fle.env.tools import Tool


class InsertItem(Tool):
    def __init__(self, connection, game_state):
        self.get_entities = GetEntities(connection, game_state)
        super().__init__(connection, game_state)

    @staticmethod
    def _apply_receipt(target, response, requested_fallback):
        inserted = int(response.get("inserted") or 0)
        requested = int(response.get("requested") or requested_fallback)
        target.inserted = inserted
        target.requested = requested
        target.insert_status = response.get("insert_status") or (
            "completed" if inserted >= requested else "partial"
        )
        remaining_capacity = response.get("remaining_capacity")
        if remaining_capacity is not None:
            target.remaining_capacity = int(remaining_capacity)
        response_warnings = response.get("warnings") or []
        if response_warnings:
            merged = list(getattr(target, "warnings", None) or [])
            for warning in response_warnings:
                if warning not in merged:
                    merged.append(warning)
            target.warnings = merged
        return target

    def _belt_entity(self, target):
        group = self.get_entities(
            {
                Prototype.TransportBelt,
                Prototype.FastTransportBelt,
                Prototype.ExpressTransportBelt,
            },
            position=target.position,
        )
        if not group:
            raise Exception(
                f"Could not find transport belt at position: {target.position}"
            )
        return group[0]

    def __call__(
        self,
        entity: Prototype,
        target: Union[Entity, EntityGroup],
        quantity=5,
        replace: bool = False,
    ) -> Entity:
        """
        Insert an item into a target entity's inventory
        :param entity: Type to insert from inventory
        :param target: Entity to insert into
        :param quantity: Quantity to insert
        :param replace: For burner fuel slots holding a different item, swap
            the old fuel back into your inventory before inserting. Without
            it the call fails and names the blocking item.
        :return: The target entity inserted into. The receipt records
            `inserted`, `requested`, `insert_status` ("completed" or
            "partial") and, when the target exposes an item inventory,
            `remaining_capacity`, the number of further items the target can
            still take. A partial insert also appears in the entity warnings;
            nothing at all is accepted only when the target inventory, the
            player stock, or the target's accepted item type allows zero.
        """
        assert quantity is not None, "Quantity cannot be None"
        assert isinstance(entity, Prototype), "The first argument must be a Prototype"
        assert isinstance(target, Entity) or isinstance(target, EntityGroup), (
            "The second argument must be an Entity or EntityGroup, you passed in a {0}".format(
                type(target)
            )
        )

        if isinstance(target, Position):
            x, y = target.x, target.y
        else:
            x, y = self.get_position(target.position)

        name, _ = entity.value
        target_name = target.name
        self.ensure_reachable(target)

        if isinstance(target, BeltGroup):
            position = None
            if len(target.inputs) > 0:
                position = target.inputs[0].position
            elif len(target.outputs) > 0:
                position = target.outputs[0].position
            if position is None:
                position = target.belts[0].position
            x, y = position.x, position.y
            if x is None or y is None:
                x, y = target.belts[0].position.x, target.belts[0].position.y

            response, elapsed = self.execute(
                self.player_index,
                name,
                quantity,
                x,
                y,
                None,
                False,
            )

            if isinstance(response, str):
                raise Exception(f"Could not insert: {response.split(':')[-1].strip()}")
            if not isinstance(response, dict) or "inserted" not in response:
                raise Exception(
                    "Could not insert: the game did not report how many items "
                    "were inserted"
                )

            inserted = int(response.get("inserted") or 0)
            if inserted <= 0:
                raise Exception(f"Could not insert {name} onto the belt")
            return self._apply_receipt(self._belt_entity(target), response, quantity)

        response, elapsed = self.execute(
            self.player_index, name, quantity, x, y, target_name, replace
        )

        if isinstance(response, str):
            raise Exception(f"Could not insert: {response.split(':')[-1].strip()}")

        cleaned_response = self.clean_response(response)
        if isinstance(cleaned_response, dict):
            if "inserted" not in cleaned_response:
                raise Exception(
                    "Could not insert: the game did not report how many items "
                    "were inserted"
                )
            if not isinstance(target, (BeltGroup, PipeGroup)):
                _type = type(target)
                prototype = Prototype._value2member_map_[(target.name, type(target))]
                target = _type(prototype=prototype, **cleaned_response)
            elif isinstance(target, BeltGroup):
                return self._apply_receipt(
                    self._belt_entity(target), cleaned_response, quantity
                )
            elif isinstance(target, PipeGroup):
                group = self.get_entities({Prototype.Pipe}, position=target.position)
                if not group:
                    raise Exception(
                        f"Could not find pipes at position: {target.position}"
                    )
                return self._apply_receipt(group[0], cleaned_response, quantity)
            else:
                raise Exception("Unknown Entity Group type")
        return target
