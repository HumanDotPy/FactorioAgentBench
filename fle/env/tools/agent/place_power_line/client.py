import math

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools import Tool
from fle.env.tools.agent.place_path.client import _blocked_by_from_message

POLE_PROTOTYPES = frozenset(
    {"small-electric-pole", "medium-electric-pole", "big-electric-pole"}
)
POLE_ENTITY_TYPE = "electric-pole"
POLE_TILE_SIZE = {
    "small-electric-pole": 1,
    "medium-electric-pole": 1,
    "big-electric-pole": 2,
}
MAX_WIRE_STEP = 7.0
WIRE_REACH = 7.5


def _point(position: Position) -> dict:
    return {"x": position.x, "y": position.y}


def _even_sized(pole: Prototype) -> bool:
    return POLE_TILE_SIZE.get(pole.value[0], 1) % 2 == 0


def _snap_axis(value: float, even: bool) -> float:
    if even:
        return float(math.floor(value + 0.5))
    return float(math.floor(value) + 0.5)


def _lattice_point(column: int, row: int, even: bool) -> Position:
    offset = 0.0 if even else 0.5
    return Position(x=column + offset, y=row + offset)


def _snap(position: Position, even: bool) -> Position:
    return Position(
        x=_snap_axis(position.x, even),
        y=_snap_axis(position.y, even),
    )


def _choose_point(anchor: Position, ideal: Position, step: float, even: bool):
    column = math.floor(ideal.x)
    row = math.floor(ideal.y)
    candidates = []
    for candidate_column in range(column - 1, column + 3):
        for candidate_row in range(row - 1, row + 3):
            point = _lattice_point(candidate_column, candidate_row, even)
            gap = math.hypot(point.x - anchor.x, point.y - anchor.y)
            candidates.append((gap, point))
    feasible = [entry for entry in candidates if 1e-9 < entry[0] <= step + 1e-9]
    if feasible:
        return max(
            feasible,
            key=lambda entry: (
                (entry[1].x - anchor.x) * (ideal.x - anchor.x)
                + (entry[1].y - anchor.y) * (ideal.y - anchor.y),
                -entry[0],
            ),
        )[1]
    forward = [entry for entry in candidates if entry[0] > 1e-9]
    if not forward:
        return None
    return min(
        forward,
        key=lambda entry: math.hypot(entry[1].x - ideal.x, entry[1].y - ideal.y),
    )[1]


def _segment_points(
    start: Position, end: Position, step: float, even: bool
) -> list[Position]:
    target = _snap(end, even)
    points = [_snap(start, even)]
    while True:
        dx = target.x - points[-1].x
        dy = target.y - points[-1].y
        distance = math.hypot(dx, dy)
        if distance <= step + 1e-9:
            break
        ideal = Position(
            x=points[-1].x + dx / distance * step,
            y=points[-1].y + dy / distance * step,
        )
        chosen = _choose_point(points[-1], ideal, step, even)
        if chosen is None:
            break
        points.append(chosen)
    if points[-1] != target:
        points.append(target)
    return points


def _plan(points: list[Position], step: float, even: bool) -> list[Position]:
    if len(points) == 1:
        return [_snap(points[0], even)]
    planned: list[Position] = []
    for start, end in zip(points, points[1:]):
        segment = _segment_points(start, end, step, even)
        if planned and segment and segment[0] == planned[-1]:
            segment = segment[1:]
        planned.extend(segment)
    return planned


def _span(chain, index, gap=None):
    first = chain[index]
    second = chain[index + 1]
    if gap is None:
        gap = math.hypot(
            second["position"]["x"] - first["position"]["x"],
            second["position"]["y"] - first["position"]["y"],
        )
    return {
        "from_index": index,
        "to_index": index + 1,
        "poles": [first.get("prototype"), second.get("prototype")],
        "positions": [first["position"], second["position"]],
        "gap": round(float(gap), 3),
    }


def _geometric_spans(chain):
    spans = []
    for index in range(len(chain) - 1):
        first = chain[index]["position"]
        second = chain[index + 1]["position"]
        gap = math.hypot(second["x"] - first["x"], second["y"] - first["y"])
        if gap > WIRE_REACH + 1e-9:
            spans.append(_span(chain, index, gap))
    return spans


def _existing_pole_entry(blocked_by, position: Position) -> dict | None:
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
    or entities.  Points snap to the pole's engine placement lattice and the
    step never exceeds the small-pole wire reach, so consecutive poles always
    land within connecting distance.  Points that already hold an electric pole
    are reported under ``existing`` and count as satisfied, so a partially
    built line can be resumed by re-issuing the same call with its original
    points.  Placement stops at the first genuinely blocked point and returns a
    structured partial receipt instead of raising.
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
        even = _even_sized(pole)
        step = min(float(spacing), MAX_WIRE_STEP)
        positions = _plan(points, step, even)
        item = pole.value[0]
        requested = [_point(position) for position in positions]
        before = int(self.game_state.inspect_inventory()[pole])
        placed = []
        existing = []
        chain = []
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
                    chain.append(
                        {
                            "position": existing_entry["position"],
                            "entity_id": existing_entry.get("entity_id"),
                            "prototype": existing_entry.get("prototype"),
                        }
                    )
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
            actual = _point(entity.position)
            placed.append({"position": actual, "entity_id": entity.id})
            chain.append(
                {"position": actual, "entity_id": entity.id, "prototype": item}
            )
        after = int(self.game_state.inspect_inventory()[pole])
        if stop_reason == "materials_exhausted":
            blocker["inventory"] = {"item": item, "available": after}
        unreachable = self._unreachable_spans(chain)
        if unreachable and stop_reason == "completed":
            stop_reason = "unreachable_spans"
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
            "unreachable_spans": unreachable,
        }

    def _unreachable_spans(self, chain):
        if len(chain) < 2:
            return []
        engine = self._engine_spans(chain)
        if engine is not None:
            return engine
        return _geometric_spans(chain)

    def _engine_spans(self, chain):
        execute = getattr(self, "execute", None)
        if execute is None:
            return None
        nodes = [
            {"x": node["position"]["x"], "y": node["position"]["y"]} for node in chain
        ]
        try:
            response, _ = execute(self.player_index, nodes)
        except Exception:
            return None
        if not isinstance(response, dict):
            return None
        unreachable = response.get("unreachable")
        if unreachable is None:
            return None
        if isinstance(unreachable, dict):
            unreachable = [unreachable[key] for key in sorted(unreachable)]
        if not isinstance(unreachable, list):
            return None
        spans = []
        for raw in unreachable:
            if not isinstance(raw, dict):
                continue
            index = raw.get("from_index")
            if not isinstance(index, int) or not 0 <= index < len(chain) - 1:
                continue
            spans.append(_span(chain, index, raw.get("gap")))
        return spans
