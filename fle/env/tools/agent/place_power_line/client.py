import math

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools import Tool
from fle.env.tools.agent.place_path.client import _blocked_by_from_message

POLE_PROTOTYPES = frozenset(
    {"small-electric-pole", "medium-electric-pole", "big-electric-pole"}
)
POLE_ENTITY_TYPE = "electric-pole"


def _point(position: Position) -> dict:
    return {"x": position.x, "y": position.y}


def _existing_pole_entry(blocked_by, position: Position) -> dict | None:
    """Promote an exact-placement rejection to ``existing`` when a pole is there.

    An occupied interpolated point is not a failure: the requested spacing
    point already holds a pole, so there is nothing left to build there.  Only
    an electric pole at (or within half a tile of) the requested point
    qualifies; any other entity or terrain remains a blocker.
    """
    if not isinstance(blocked_by, dict):
        return None
    prototype = blocked_by.get("prototype") or blocked_by.get("name")
    if prototype not in POLE_PROTOTYPES and blocked_by.get("type") != POLE_ENTITY_TYPE:
        return None
    blocker_position = blocked_by.get("position")
    if not isinstance(blocker_position, dict):
        return None
    try:
        x = float(blocker_position["x"])
        y = float(blocker_position["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if abs(x - position.x) > 0.5 or abs(y - position.y) > 0.5:
        return None
    return {
        "position": {"x": x, "y": y},
        "prototype": prototype,
        "entity_id": blocked_by.get("entity_id"),
    }


class PlacePowerLine(Tool):
    """Place evenly spaced poles through the caller-specified points.

    The polyline is exact: interpolated points are never routed around terrain
    or entities.  Points that already hold an electric pole are reported under
    ``existing`` and count as satisfied, so a partially built line can be
    resumed by re-issuing the same call with its original points.  Placement
    stops at the first genuinely blocked point and returns a structured
    partial receipt instead of raising.
    """

    def __call__(
        self,
        points: list[Position | tuple[float, float]],
        pole: Prototype,
        spacing: float = 7.0,
    ) -> dict:
        if spacing <= 0:
            raise ValueError("spacing must be positive")
        points = [p if isinstance(p, Position) else Position(*p) for p in points]
        if not points:
            raise ValueError("place_power_line needs at least one point")
        positions = [points[0]]
        for start, end in zip(points, points[1:]):
            dx, dy = end.x - start.x, end.y - start.y
            distance = math.hypot(dx, dy)
            segments = max(1, math.ceil(distance / spacing))
            for index in range(1, segments + 1):
                positions.append(
                    Position(
                        x=start.x + dx * index / segments,
                        y=start.y + dy * index / segments,
                    )
                )
        item = pole.value[0]
        requested = [_point(position) for position in positions]
        before = int(self.game_state.inspect_inventory()[pole])
        placed = []
        existing = []
        blocker = None
        stop_reason = "completed"
        stopped_at = None
        for index, position in enumerate(positions):
            try:
                entity = self.game_state.place_entity(
                    pole, position=position, exact=True
                )
            except Exception as exc:
                message = str(exc)
                blocked_by = _blocked_by_from_message(message)
                existing_entry = _existing_pole_entry(blocked_by, position)
                if existing_entry is not None:
                    existing.append(existing_entry)
                    continue
                stop_reason = (
                    "materials_exhausted"
                    if "inventory" in message.lower()
                    else "collision"
                )
                blocker = {
                    "position": _point(position),
                    "name": (blocked_by or {}).get("prototype"),
                    "reason": stop_reason,
                    "message": message,
                }
                if blocked_by is not None:
                    blocker["blocked_by"] = blocked_by
                stopped_at = index
                break
            placed.append({"position": _point(position), "entity_id": entity.id})
        after = int(self.game_state.inspect_inventory()[pole])
        if stop_reason == "materials_exhausted":
            blocker["inventory"] = {"item": item, "available": after}
        return {
            "status": "completed" if stop_reason == "completed" else "partial",
            "stop_reason": stop_reason,
            "requested": requested,
            "placed": placed,
            "existing": existing,
            "remaining": requested[stopped_at:] if stopped_at is not None else [],
            "blocker": blocker,
            "entity_ids": [entry["entity_id"] for entry in placed],
            "inventory_delta": {item: after - before},
        }
