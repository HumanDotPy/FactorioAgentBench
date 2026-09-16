from typing import List, Optional, Set, Union

from pydantic import BaseModel, ConfigDict

from fle.env.entities import Position, Entity, EntityGroup
from fle.env.game_types import Prototype, prototype_by_name
from fle.env.tools.agent.connect_entities.groupable_entities import (
    agglomerate_groupable_entities,
)
from fle.env.tools import Tool


class GroundItem(BaseModel):
    """An item-entity (item-on-ground) stack inside the queried area."""

    model_config = ConfigDict(extra="allow")
    name: str
    count: int = 0
    position: Optional[Position] = None

    def __repr__(self) -> str:
        return (
            f"GroundItem(name='{self.name}', count={self.count}, "
            f"position={self.position})"
        )


class EntityList(list):
    """Entity query results with the counts of everything that was dropped."""

    def __init__(
        self,
        items=(),
        *,
        other_forces: int = 0,
        other_force_names=None,
        characters_skipped: int = 0,
        server_skipped: int = 0,
        unmatched: int = 0,
        construction_failed: int = 0,
        ground_items=None,
        ground_item_stacks: int = 0,
        ground_item_totals=None,
        ground_items_truncated: bool = False,
        query_radius: float = 0.0,
    ):
        super().__init__(items)
        self.other_forces = int(other_forces)
        self.other_force_names = list(other_force_names or [])
        self.characters_skipped = int(characters_skipped)
        self.server_skipped = int(server_skipped)
        self.unmatched = int(unmatched)
        self.construction_failed = int(construction_failed)
        self.ground_items = list(ground_items or [])
        self.ground_item_stacks = int(ground_item_stacks)
        self.ground_item_totals = {
            str(name): int(count) for name, count in (ground_item_totals or {}).items()
        }
        self.ground_items_truncated = bool(ground_items_truncated)
        self.query_radius = float(query_radius)

    @property
    def skipped(self) -> int:
        return self.server_skipped + self.unmatched + self.construction_failed

    @property
    def ground_item_count(self) -> int:
        return self.ground_item_stacks

    def as_dict(self) -> dict:
        return {
            "entities": list(self),
            "other_forces": self.other_forces,
            "other_force_names": list(self.other_force_names),
            "characters_skipped": self.characters_skipped,
            "skipped": self.skipped,
            "unmatched_prototypes": self.unmatched,
            "construction_failed": self.construction_failed,
            "ground_items": [
                item.model_dump(exclude_none=True) for item in self.ground_items
            ],
            "ground_item_count": self.ground_item_count,
            "ground_item_totals": dict(self.ground_item_totals),
            "ground_items_truncated": self.ground_items_truncated,
            "query_radius": self.query_radius,
        }

    def __repr__(self) -> str:
        base = super().__repr__()
        if not (self.other_forces or self.characters_skipped or self.skipped):
            return base
        return (
            f"{base} [other_forces={self.other_forces}, "
            f"other_force_names={self.other_force_names}, "
            f"characters_skipped={self.characters_skipped}, "
            f"unmatched_prototypes={self.unmatched}, "
            f"server_skipped={self.server_skipped}, "
            f"construction_failed={self.construction_failed}]"
        )


class GetEntities(Tool):
    DEFAULT_RADIUS = 32

    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    # @cached(max_size=16, ttl=0.15)
    def __call__(
        self,
        entities: Union[Set[Prototype], Prototype] = set(),
        position: Position = None,
        radius: float = None,
    ) -> List[Union[Entity, EntityGroup]]:
        """
        Get entities within a radius of a given position.
        :param entities: Set of entity prototypes to filter by. If empty, all entities are returned.
        :param position: Position to search around. Can be a Position object or "player" for player's position.
        :param radius: Radius to search within (default 32; pass a larger value for wider scans).
        :return: Found entities. The returned list also carries other_forces,
            characters_skipped, unmatched_prototypes and skipped counts for
            everything the query dropped.
        """

        try:
            if not isinstance(position, Position) and position is not None:
                raise ValueError("The second argument must be a Position object")

            if radius is None:
                radius = self.DEFAULT_RADIUS
            radius = float(radius)
            if radius < 0:
                raise ValueError("radius must be non-negative")

            if not isinstance(entities, Set):
                entities = set([entities])

            # Handle group prototypes by expanding them to their component types
            expanded_entities = set()
            group_requests = set()

            for entity in entities:
                if entity == Prototype.BeltGroup:
                    # For belt groups, search for all belt types and group them
                    belt_types = {
                        Prototype.TransportBelt,
                        Prototype.FastTransportBelt,
                        Prototype.ExpressTransportBelt,
                        Prototype.UndergroundBelt,
                        Prototype.FastUndergroundBelt,
                        Prototype.ExpressUndergroundBelt,
                    }
                    expanded_entities.update(belt_types)
                    group_requests.add(Prototype.BeltGroup)
                elif entity == Prototype.PipeGroup:
                    # For pipe groups, search for pipe types and group them
                    pipe_types = {Prototype.Pipe, Prototype.UndergroundPipe}
                    expanded_entities.update(pipe_types)
                    group_requests.add(Prototype.PipeGroup)
                elif entity == Prototype.ElectricityGroup:
                    # For electricity groups, search for pole types and group them
                    pole_types = {
                        Prototype.SmallElectricPole,
                        Prototype.MediumElectricPole,
                        Prototype.BigElectricPole,
                    }
                    expanded_entities.update(pole_types)
                    group_requests.add(Prototype.ElectricityGroup)
                else:
                    expanded_entities.add(entity)

            # Use expanded entities for the Lua query
            query_entities = expanded_entities

            # Serialize entity_names as a string
            entity_names = (
                "["
                + ",".join([f'"{entity.value[0]}"' for entity in query_entities])
                + "]"
                if query_entities
                else "[]"
            )

            if position is None:
                response, time_elapsed = self.execute(
                    self.player_index, radius, entity_names
                )
            else:
                response, time_elapsed = self.execute(
                    self.player_index, radius, entity_names, position.x, position.y
                )

            if not response:
                return EntityList(query_radius=radius)

            if isinstance(response, str):
                raise Exception("Could not get entities", response)

            disclosure = {}
            raw_entities = response
            if isinstance(response, dict):
                raw_entities = response.get("entities")
                if raw_entities is None:
                    raise Exception("Could not get entities", response)
                disclosure = response
            if not raw_entities:
                raw_entities = []

            ground_items = self._ground_items_from_response(disclosure)
            ground_item_stacks = len(ground_items)
            ground_item_totals = {}
            ground_items_truncated = False
            if isinstance(disclosure, dict):
                try:
                    ground_item_stacks = int(
                        disclosure.get("ground_item_stacks", ground_item_stacks)
                    )
                except (TypeError, ValueError):
                    ground_item_stacks = len(ground_items)
                raw_totals = disclosure.get("ground_item_totals")
                if isinstance(raw_totals, dict):
                    ground_item_totals = raw_totals
                ground_items_truncated = bool(disclosure.get("ground_items_truncated"))

            unmatched = 0
            construction_failed = 0
            entities_list = []
            for raw_entity_data in raw_entities:
                if isinstance(raw_entity_data, list):
                    continue
                if not isinstance(raw_entity_data, dict):
                    continue

                entity_data = self.clean_response(raw_entity_data)
                # Find the matching Prototype
                matching_prototype = prototype_by_name.get(
                    entity_data["name"].replace("_", "-")
                )

                if matching_prototype is None:
                    unmatched += 1
                    if "name" in entity_data and entity_data["name"] != "entity-ghost":
                        print(
                            f"Warning: No matching Prototype found for {entity_data['name']}"
                        )
                    continue

                # Apply standard filtering - check against expanded entities too
                if (
                    entities
                    and matching_prototype not in entities
                    and matching_prototype not in expanded_entities
                ):
                    continue

                metaclass = matching_prototype.value[1]
                while isinstance(metaclass, tuple):
                    metaclass = metaclass[1]

                # Process nested dictionaries (like inventories)
                for key, value in entity_data.items():
                    if isinstance(value, dict):
                        entity_data[key] = self.process_nested_dict(value)

                entity_data["prototype"] = matching_prototype

                # remove all empty values from the entity_data dictionary
                entity_data = {
                    k: v for k, v in entity_data.items() if v or isinstance(v, int)
                }

                try:
                    if "inventory" in entity_data:
                        if isinstance(entity_data["inventory"], list):
                            merged_inventory = {}
                            for lane in entity_data["inventory"]:
                                if not isinstance(lane, dict):
                                    continue
                                for item, count in lane.items():
                                    merged_inventory[item] = (
                                        merged_inventory.get(item, 0) + count
                                    )
                            entity_data["inventory"] = merged_inventory
                        else:
                            inventory_data = {
                                k: v
                                for k, v in entity_data["inventory"].items()
                                if v or isinstance(v, int)
                            }
                            entity_data["inventory"] = inventory_data

                    entity = metaclass(**entity_data)
                    entities_list.append(entity)
                except Exception as e1:
                    construction_failed += 1
                    print(f"Could not create {entity_data['name']} object: {e1}")

            # Group entities when:
            # 1. User explicitly requests group types, OR
            # 2. User provides a position filter (suggesting they want nearby entities grouped), OR
            # 3. No specific entities requested (get all entities - should be grouped), OR
            # 4. User requests individual pole entities (restore original behavior - poles are always grouped)
            should_group = (
                not entities  # No filter = group everything
                or any(
                    proto
                    in {
                        Prototype.ElectricityGroup,
                        Prototype.PipeGroup,
                        Prototype.BeltGroup,
                    }
                    for proto in entities
                )  # Explicit group request
                or (
                    entities and position is not None
                )  # Individual entities with position filter = group for convenience
            )

            if should_group:
                pipe_types = (Prototype.Pipe, Prototype.UndergroundPipe)
                pole_group_types = (
                    Prototype.SmallElectricPole,
                    Prototype.BigElectricPole,
                    Prototype.MediumElectricPole,
                )
                belt_types = (
                    Prototype.TransportBelt,
                    Prototype.FastTransportBelt,
                    Prototype.ExpressTransportBelt,
                    Prototype.UndergroundBelt,
                    Prototype.FastUndergroundBelt,
                    Prototype.ExpressUndergroundBelt,
                )
                pipes = []
                poles = []
                walls = []
                belts = []
                others = []
                for entity in entities_list:
                    prototype = getattr(entity, "prototype", None)
                    if prototype in pipe_types:
                        pipes.append(entity)
                    elif prototype in pole_group_types:
                        poles.append(entity)
                    elif prototype == Prototype.StoneWall:
                        walls.append(entity)
                    elif prototype in belt_types:
                        belts.append(entity)
                    else:
                        others.append(entity)

                entities_list = others
                entities_list.extend(agglomerate_groupable_entities(pipes))
                entities_list.extend(agglomerate_groupable_entities(poles))
                entities_list.extend(agglomerate_groupable_entities(walls))
                entities_list.extend(agglomerate_groupable_entities(belts))

            # Final filtering after grouping is complete
            if entities:
                filtered_entities = []
                for entity in entities_list:
                    # Check entity prototype or group type
                    if hasattr(entity, "prototype") and (
                        entity.prototype in entities
                        or entity.prototype in expanded_entities
                    ):
                        filtered_entities.append(entity)
                    elif hasattr(entity, "__class__"):
                        # Handle group entities
                        if entity.__class__.__name__ == "ElectricityGroup":
                            pole_types = {
                                Prototype.SmallElectricPole,
                                Prototype.MediumElectricPole,
                                Prototype.BigElectricPole,
                            }
                            if Prototype.ElectricityGroup in group_requests:
                                # Explicit group request - return the group
                                filtered_entities.append(entity)
                            elif (
                                any(pole_type in entities for pole_type in pole_types)
                                and position is not None
                            ):
                                # Individual poles requested with position - return group for convenience
                                filtered_entities.append(entity)
                            elif any(pole_type in entities for pole_type in pole_types):
                                # Individual poles requested - return group (restores original behavior)
                                # Power poles are inherently networked, so groups are more useful than individuals
                                filtered_entities.append(entity)
                        elif entity.__class__.__name__ == "PipeGroup":
                            pipe_types = {Prototype.Pipe, Prototype.UndergroundPipe}
                            if Prototype.PipeGroup in group_requests:
                                # Explicit group request - return the group
                                filtered_entities.append(entity)
                            elif (
                                any(pipe_type in entities for pipe_type in pipe_types)
                                and position is not None
                            ):
                                # Individual pipes requested with position - return group for convenience
                                filtered_entities.append(entity)
                            elif any(pipe_type in entities for pipe_type in pipe_types):
                                # Individual pipes requested - return group (restores original behavior)
                                # Pipes are inherently networked, so groups are more useful than individuals
                                filtered_entities.append(entity)
                        elif entity.__class__.__name__ == "BeltGroup":
                            belt_types = {
                                Prototype.TransportBelt,
                                Prototype.FastTransportBelt,
                                Prototype.ExpressTransportBelt,
                                Prototype.UndergroundBelt,
                                Prototype.FastUndergroundBelt,
                                Prototype.ExpressUndergroundBelt,
                            }
                            if Prototype.BeltGroup in group_requests:
                                # Explicit group request - return the group
                                filtered_entities.append(entity)
                            elif (
                                any(belt_type in entities for belt_type in belt_types)
                                and position is not None
                            ):
                                # Individual belts requested with position - return group for convenience
                                filtered_entities.append(entity)
                            elif (
                                any(belt_type in entities for belt_type in belt_types)
                                and position is None
                            ):
                                # Individual belts requested without position - extract individual belts from group
                                for belt in entity.belts:
                                    if (
                                        hasattr(belt, "prototype")
                                        and belt.prototype in entities
                                    ):
                                        filtered_entities.append(belt)
                        elif entity.__class__.__name__ == "WallGroup":
                            # WallGroup doesn't have a corresponding Prototype, but include if present
                            filtered_entities.append(entity)
                entities_list = filtered_entities

            return EntityList(
                entities_list,
                other_forces=disclosure.get("other_forces", 0),
                other_force_names=disclosure.get("other_force_names", []),
                characters_skipped=disclosure.get("characters_skipped", 0),
                server_skipped=disclosure.get("skipped", 0),
                unmatched=unmatched,
                construction_failed=construction_failed,
                ground_items=ground_items,
                ground_item_stacks=ground_item_stacks,
                ground_item_totals=ground_item_totals,
                ground_items_truncated=ground_items_truncated,
                query_radius=radius,
            )

        except Exception as e:
            # Include more context in error message for debugging
            entity_info = (
                f"entities={[e.value[0] for e in entities] if entities else 'all'}"
            )
            position_info = f"position={position}" if position else "position=player"
            raise Exception(
                f"Error in GetEntities ({entity_info}, {position_info}, radius={radius}): {e}"
            )

    def _ground_items_from_response(self, disclosure) -> List[GroundItem]:
        if not isinstance(disclosure, dict):
            return []
        raw_items = disclosure.get("ground_items")
        if not isinstance(raw_items, list):
            return []
        ground_items = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            try:
                ground_items.append(GroundItem(**self.clean_response(raw_item)))
            except Exception:
                continue
        return ground_items

    def process_nested_dict(self, nested_dict):
        """Helper method to process nested dictionaries"""
        if isinstance(nested_dict, dict):
            if all(isinstance(key, int) for key in nested_dict.keys()):
                return [
                    self.process_nested_dict(value) for value in nested_dict.values()
                ]
            else:
                return {
                    key: self.process_nested_dict(value)
                    for key, value in nested_dict.items()
                }
        return nested_dict
