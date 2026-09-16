import math

from fle.env.entities import Position, Entity
from fle.env.game_types import Prototype
from fle.env.tools.agent.get_entities.client import GetEntities
from fle.env.tools import Tool


GROUP_RADIUS = 1


class GetEntity(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)
        self.get_entities = GetEntities(connection, game_state)

    def __call__(self, entity: Prototype, position: Position) -> Entity:
        """
        Retrieve a given entity object at position (x, y) if it exists on the world.
        :param entity: Entity prototype to get, e.g Prototype.StoneFurnace
        :param position: Position where to look
        :return: Entity object
        """
        assert isinstance(entity, Prototype)
        assert isinstance(position, Position)
        if entity in (
            Prototype.BeltGroup,
            Prototype.PipeGroup,
            Prototype.ElectricityGroup,
        ):
            return self._get_group(entity, position)
        try:
            x, y = self.get_position(position)
            name, metaclass = entity.value
            while isinstance(metaclass, tuple):
                metaclass = metaclass[1]

            response, elapsed = self.execute(self.player_index, name, x, y)

            if response is None or response == {} or isinstance(response, str):
                # No entity found at position - return None instead of raising
                return None

            cleaned_response = self.clean_response(response)
            try:
                object = metaclass(prototype=entity.name, **cleaned_response)
            except Exception as e:
                raise Exception(
                    f"Could not create {name} object from response (get entity): {cleaned_response}",
                    e,
                )

            return object
        except Exception as e:
            raise Exception(f"Could not get {entity} at position {position}", e)

    def _get_group(self, entity: Prototype, position: Position) -> Entity:
        if entity == Prototype.BeltGroup:
            types = {
                Prototype.TransportBelt,
                Prototype.FastTransportBelt,
                Prototype.ExpressTransportBelt,
                Prototype.UndergroundBelt,
                Prototype.FastUndergroundBelt,
                Prototype.ExpressUndergroundBelt,
            }
        elif entity == Prototype.PipeGroup:
            types = {Prototype.Pipe, Prototype.UndergroundPipe}
        else:
            types = {
                Prototype.SmallElectricPole,
                Prototype.MediumElectricPole,
                Prototype.BigElectricPole,
            }
        found = self.get_entities(types, position=position, radius=GROUP_RADIUS)
        if not found:
            return None
        groups = [item for item in found if getattr(item, "id", None) is not None]
        if not groups:
            print(
                f"Info: get_entity({entity.name}) at {position} found individual "
                f"entities, not a {entity.name}"
            )
            return found[0]
        group = min(groups, key=lambda item: self._distance(item, position))
        member_count = len(self._group_members(group))
        print(
            f"Info: get_entity({entity.name}) at {position} returned "
            f"{type(group).__name__} (id={group.id}) with {member_count} members "
            f"and status={group.status}; this is a connected network near the "
            f"position, not a single entity."
        )
        return group

    @staticmethod
    def _group_members(group):
        for attribute in ("belts", "pipes", "poles", "entities"):
            members = getattr(group, attribute, None)
            if members:
                return members
        return []

    @classmethod
    def _distance(cls, group, position: Position) -> float:
        members = cls._group_members(group)
        if members:
            return min(
                math.hypot(member.position.x - position.x, member.position.y - position.y)
                for member in members
            )
        return math.hypot(group.position.x - position.x, group.position.y - position.y)
