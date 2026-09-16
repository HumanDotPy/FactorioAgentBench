import json
import math
from typing import Union

from fle.env.entities import Entity, Position
from fle.env.game_types import Prototype
from fle.env.tools import Tool
from fle.env.tools.agent.get_entities.client import GetEntities

DROP_POSITION_TYPES = (
    "mining drills (burner-mining-drill, electric-mining-drill)",
    "inserters (burner-inserter, inserter, fast-inserter, stack-inserter, "
    "filter-inserter)",
)
SOURCE_SEARCH_RADIUS = 1.5


def _catch_tile(drop_position: Position) -> Position:
    return Position(
        x=float(math.floor(drop_position.x)) + 0.5,
        y=float(math.floor(drop_position.y)) + 0.5,
    )


def _position_dict(position) -> dict | None:
    if position is None:
        return None
    return {"x": position.x, "y": position.y}


def _tile_size(entity) -> tuple[float, float] | None:
    tile_dimensions = getattr(entity, "tile_dimensions", None)
    width = getattr(tile_dimensions, "tile_width", None)
    height = getattr(tile_dimensions, "tile_height", None)
    if width is None or height is None:
        return None
    try:
        return float(width), float(height)
    except (TypeError, ValueError):
        return None


def _parity(width: float, height: float) -> str:
    if width % 2 == 0 and height % 2 == 0:
        return "corner"
    if width % 2 == 1 and height % 2 == 1:
        return "center"
    return "mixed"


def _source_summary(entity, drop_position: Position) -> dict:
    summary = {
        "entity_id": getattr(entity, "id", None),
        "name": getattr(entity, "name", None),
        "position": _position_dict(getattr(entity, "position", None)),
        "drop_position": _position_dict(drop_position),
    }
    size = _tile_size(entity)
    if size is None:
        summary["parity"] = "unknown"
        return summary
    width, height = size
    summary["tile_size"] = {"width": width, "height": height}
    summary["parity"] = _parity(width, height)
    position = getattr(entity, "position", None)
    if position is not None:
        left = position.x - width / 2
        top = position.y - height / 2
        summary["footprint"] = {
            "left_top": {"x": left, "y": top},
            "right_bottom": {"x": left + width, "y": top + height},
        }
    return summary


class CatchOutput(Tool):
    def __init__(self, *args):
        super().__init__(*args)
        self.get_entities = GetEntities(*args)

    def __call__(
        self,
        source: Union[Entity, Position],
        prototype: Prototype = Prototype.IronChest,
        path: bool = True,
    ) -> dict:
        """Place a receiver on a machine's authoritative output tile.

        ``source`` is an Entity with a ``drop_position`` (mining drills,
        inserters) or its live Position. The catch tile is
        ``floor(drop_position) + 0.5``. The live check and the exact manual
        build check run server-side through the shared place_entity action.
        ``path=True`` walks to the catch tile before the check; ``path=False``
        never pre-approaches. The receipt reports status, source,
        drop_position, catch_tile, placed, item_on_ground_before and warnings.
        """
        if not isinstance(prototype, Prototype):
            raise ValueError(
                "prototype must be a Prototype (the receiver entity to place)"
            )
        if not isinstance(path, bool):
            raise ValueError("path must be a bool")

        entity = self._resolve_entity(source)
        drop_position = getattr(entity, "drop_position", None)
        if drop_position is None:
            raise ValueError(
                f"{getattr(entity, 'name', 'source')!r} has no drop_position; "
                "catch_output needs a machine that produces an output tile. "
                "Entities with a drop_position: " + "; ".join(DROP_POSITION_TYPES)
            )
        catch_tile = _catch_tile(drop_position)
        if path:
            self.ensure_reachable(catch_tile)

        entity_position = getattr(entity, "position", None)
        name, _ = prototype.value
        response, _ = self.execute(
            self.player_index,
            getattr(entity, "id", None),
            name,
            entity_position.x if entity_position is not None else drop_position.x,
            entity_position.y if entity_position is not None else drop_position.y,
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"Could not catch output at {catch_tile}: {response}")
        if response.get("status") in {"source_missing", "no_drop_position"}:
            raise RuntimeError(json.dumps(response, sort_keys=True, default=str))

        receipt = dict(response)
        receipt["status"] = str(response.get("status") or "unknown")
        live_source = response.get("source")
        summary = _source_summary(entity, drop_position)
        if isinstance(live_source, dict):
            summary.update(live_source)
        receipt["source"] = summary
        receipt["drop_position"] = _position_dict(drop_position)
        receipt["catch_tile"] = _position_dict(catch_tile)
        receipt.setdefault("placed", None)
        receipt.setdefault("item_on_ground_before", 0)
        receipt.setdefault("warnings", [])
        return receipt

    def _resolve_entity(self, source) -> Entity:
        if isinstance(source, Entity):
            return source
        if not isinstance(source, Position):
            raise ValueError(
                "source must be an Entity (or its live Position) whose output to catch"
            )
        candidates = self.get_entities(position=source, radius=SOURCE_SEARCH_RADIUS)
        machines = [
            candidate
            for candidate in candidates
            if getattr(candidate, "drop_position", None) is not None
        ]
        if not machines:
            raise ValueError(
                f"no machine with a drop_position found at {source}; "
                "entities with a drop_position: " + "; ".join(DROP_POSITION_TYPES)
            )

        def distance(candidate):
            position = getattr(candidate, "position", None)
            if position is None:
                return 0.0
            return math.hypot(position.x - source.x, position.y - source.y)

        return min(machines, key=distance)
