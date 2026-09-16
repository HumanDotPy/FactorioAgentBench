import json
import math

from fle.env.entities import Position, Entity
from fle.env import DirectionInternal, Direction
from fle.env.game_types import Prototype
from fle.env.tools.agent.get_entity.client import GetEntity
from fle.env.tools.agent.pickup_entity.client import PickupEntity
from fle.env.tools import Tool
from fle.env.tools.spatial import normalize_spatial

BELT_INSERTER_TYPES = frozenset(
    {
        "transport-belt",
        "underground-belt",
        "splitter",
        "inserter",
        "loader",
        "linked-belt",
    }
)


def _tile_corner(value: float) -> float:
    return float(math.floor(value))


def _tile_center(value: float) -> float:
    return float(math.floor(value)) + 0.5


def _is_receiver(entry: dict) -> bool:
    if entry.get("input_inventory"):
        return True
    return entry.get("type") in BELT_INSERTER_TYPES


def _drop_diagnostics(response: dict) -> dict:
    drop_position = response.get("drop_position")
    if not isinstance(drop_position, dict):
        return {}
    try:
        drop_x = float(drop_position.get("x"))
        drop_y = float(drop_position.get("y"))
    except (TypeError, ValueError):
        return {}
    drop_tile = {"x": _tile_corner(drop_x), "y": _tile_corner(drop_y)}
    catch_tile = {"x": _tile_center(drop_x), "y": _tile_center(drop_y)}
    diagnostics = {"drop_tile": drop_tile, "catch_tile": catch_tile}
    report = response.get("drop_report")
    if not isinstance(report, dict):
        return diagnostics
    candidates = report.get("entities")
    candidates = candidates if isinstance(candidates, list) else []
    diagnostics["drop_receivers"] = [
        {
            "name": entry.get("name"),
            "position": entry.get("position"),
            "entity_id": entry.get("entity_id"),
        }
        for entry in candidates
        if isinstance(entry, dict) and _is_receiver(entry)
    ]
    ground_items = report.get("ground_items")
    ground_items = int(ground_items) if isinstance(ground_items, (int, float)) else 0
    diagnostics["drop_ground_items"] = ground_items
    diagnostics["drop_by_item"] = report.get("ground_by_item") or {}
    if ground_items > 0:
        diagnostics["drop_warning"] = (
            "items are accumulating on the ground at the catch tile "
            f"({catch_tile['x']}, {catch_tile['y']}); place a receiving entity there"
        )
    elif not diagnostics["drop_receivers"]:
        diagnostics["drop_warning"] = (
            "no receiving entity at the catch tile "
            f"({catch_tile['x']}, {catch_tile['y']}); the drop at "
            f"({drop_tile['x']}, {drop_tile['y']}) has no sink"
        )
    return diagnostics


def _resource_warning(response: dict) -> dict | None:
    resources = response.get("resources")
    if not isinstance(resources, list):
        return None
    counts: dict[str, int] = {}
    for entry in resources:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        name = str(entry["name"])
        try:
            count = int(entry.get("count"))
        except (TypeError, ValueError):
            count = 0
        counts[name] = counts.get(name, 0) + count
    if len(counts) < 2:
        return None
    dominant = max(counts, key=counts.get)
    return {
        "resources": counts,
        "dominant": dominant,
        "total": sum(counts.values()),
        "message": (
            "drill area has multiple resources ("
            + ", ".join(f"{name}={count}" for name, count in counts.items())
            + f"); dominant {dominant}"
        ),
    }


class PlaceObject(Tool):
    def __init__(self, *args):
        super().__init__(*args)
        self.name = "place_entity"
        self.load()
        self.get_entity = GetEntity(*args)
        self.pickup_entity = PickupEntity(*args)

    def __call__(
        self,
        entity: Prototype,
        direction: Direction = Direction.UP,
        position: Position = Position(x=0, y=0),
        exact: bool = True,
        # relative=False
    ) -> Entity:
        """
        Places an entity e at local position (x, y) if you have it in inventory.
        :param entity: Entity to place
        :param direction: Cardinal direction to place
        :param position: Position to place entity
        :param exact: If True, place entity at exact position, else place entity at nearest possible position
        :return: Entity object
        """

        # if not isinstance(entity, Prototype):
        #    raise ValueError("The first argument must be a Prototype object")

        # If position is a tuple, cast it to a Position object:
        if isinstance(position, tuple):
            position = Position(x=position[0], y=position[1])

        if not isinstance(position, Position):
            raise ValueError("The position argument must be a Position object")

        if not isinstance(direction, (DirectionInternal, Direction)):
            raise ValueError("The second argument must be a Direction object")

        x, y = self.get_position(position)
        self.ensure_reachable(position)
        try:
            name, metaclass = entity.value
            while isinstance(metaclass, tuple):
                metaclass = metaclass[1]
        except Exception as e:
            raise Exception(f"Passed in {entity} argument is not a valid Prototype", e)

        factorio_direction = DirectionInternal.to_factorio_direction(direction)

        try:
            # If we are in `fast` mode, this is synchronous
            response, elapsed = self.execute(
                self.player_index, name, factorio_direction, x, y, exact
            )
        except Exception as error:
            raise RuntimeError(
                f"Could not place {name} at ({x}, {y}): {error}"
            ) from error

        if not isinstance(response, dict):
            raise RuntimeError(f"Could not place {name} at ({x}, {y}): {response}")
        if response.get("error"):
            raise RuntimeError(json.dumps(normalize_spatial(response), sort_keys=True))
        cleaned_response = self.clean_response(response)
        cleaned_response.update(_drop_diagnostics(cleaned_response))
        resource_warning = _resource_warning(cleaned_response)
        if resource_warning is not None:
            cleaned_response["resource_warning"] = resource_warning
        return metaclass(
            prototype=entity.name, game=self.connection, **cleaned_response
        )
