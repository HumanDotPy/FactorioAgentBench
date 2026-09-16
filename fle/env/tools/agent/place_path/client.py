import json
import math

from fle.env import Direction
from fle.env.entities import Position
from fle.env.game_types import Prototype, prototype_by_name
from fle.env.tools import Tool

MAX_CLEARED_ENTITIES = 64
MAX_STALLED_CLEARS = 16


def _blocked_by_from_message(message: str) -> dict | None:
    """Extract the promoted ``blocked_by`` entity from a placement failure.

    Placement failures raise with a diagnostics payload embedded in the
    exception text.  Different call layers wrap it differently, so scan for
    the first JSON object and look for ``blocked_by`` (preferred) or fall back
    to the nearest ``overlapping_entities`` entry.
    """

    start = message.find("{")
    if start == -1:
        return None
    try:
        payload, _ = json.JSONDecoder().raw_decode(message[start:])
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    diagnostics = payload.get("diagnostics")
    if isinstance(diagnostics, dict):
        payload = diagnostics
    blocked_by = payload.get("blocked_by")
    if isinstance(blocked_by, dict):
        return blocked_by
    overlapping = payload.get("overlapping_entities")
    if isinstance(overlapping, list) and overlapping:
        nearest = overlapping[0]
        if isinstance(nearest, dict):
            return nearest
    return None


class PlacePath(Tool):
    """Place the caller-specified polyline; never route around blockers."""

    def __call__(
        self,
        prototype: Prototype,
        points: list[Position | tuple[float, float]],
        routing: str = "polyline",
        on_collision: str = "stop",
        on_insufficient_materials: str = "stop",
        on_obstacle: str = "stop",
    ) -> dict:
        if routing != "polyline":
            raise ValueError("routing must be 'polyline'")
        if on_collision not in {"stop", "raise"} or on_insufficient_materials not in {
            "stop",
            "raise",
        }:
            raise ValueError("stop policies must be 'stop' or 'raise'")
        if on_obstacle not in {"stop", "clear"}:
            raise ValueError("on_obstacle must be 'stop' or 'clear'")
        route = self._rasterize(points)
        directions = [self._direction(route, index) for index in range(len(route))]
        before_tick = self._tick()
        before = self.game_state.inspect_inventory()[prototype]
        placed = []
        cleared = []
        blocker = None
        reason = "completed"
        stalled = 0
        index = 0
        while index < len(route):
            position = route[index]
            direction = directions[index]
            try:
                placed.append(
                    self.game_state.place_entity(prototype, direction, position, True)
                )
            except Exception as exc:
                message = str(exc)
                reason = (
                    "materials_exhausted"
                    if "inventory" in message.lower()
                    else "collision"
                )
                policy = (
                    on_insufficient_materials
                    if reason == "materials_exhausted"
                    else on_collision
                )
                if policy == "raise":
                    raise
                blocked_by = _blocked_by_from_message(message)
                if reason == "collision" and on_obstacle == "clear":
                    if len(cleared) >= MAX_CLEARED_ENTITIES:
                        reason = "clear_budget_exhausted"
                    else:
                        entry = self._clear_obstacle(blocked_by, position)
                        if entry is None:
                            reason = "clear_failed"
                        else:
                            cleared.append(entry)
                            stalled += 1
                            if stalled <= MAX_STALLED_CLEARS:
                                continue
                            reason = "clear_no_progress"
                blocker = {
                    "position": {"x": position.x, "y": position.y},
                    "message": message,
                }
                if blocked_by is not None:
                    blocker["blocked_by"] = blocked_by
                if reason.startswith("clear_") and cleared:
                    blocker["last_cleared"] = cleared[-1]
                break
            index += 1
            stalled = 0
        self.refresh_player_location()
        after = self.game_state.inspect_inventory()[prototype]
        remaining = [{"x": point.x, "y": point.y} for point in route[len(placed) :]]
        resume_from = remaining[0] if remaining else None
        receipt = {
            "status": "completed" if len(placed) == len(route) else "partial",
            "placed": len(placed),
            "requested": len(route),
            "last_position": (
                {"x": placed[-1].position.x, "y": placed[-1].position.y}
                if placed
                else None
            ),
            "ticks_elapsed": max(self._tick() - before_tick, 0),
            "inventory_delta": {prototype.value[0]: int(after) - int(before)},
            "stop_reason": reason,
            "blocker": blocker,
            "entity_ids": [entity.id for entity in placed],
            "directions": [
                {"x": point.x, "y": point.y, "direction": direction.name}
                for point, direction in zip(route, directions)
            ],
            "resume_from": resume_from,
            "remaining": remaining,
            "cleared": cleared,
        }
        if receipt["status"] == "partial" and resume_from is not None:
            anchor = receipt["last_position"] or resume_from
            retry = (
                "restock the prototype and resume"
                if reason == "materials_exhausted"
                else "clear the blocker and resume"
            )
            receipt["next_step"] = (
                f"{retry} from resume_from ({resume_from['x']}, "
                f"{resume_from['y']}); audit the built line with "
                f"trace_belt(Position(x={anchor['x']}, y={anchor['y']}))"
            )
        return receipt

    def _clear_obstacle(self, blocked_by, fallback: Position) -> dict | None:
        position = None
        prototype_name = None
        if isinstance(blocked_by, dict):
            raw = blocked_by.get("position")
            if isinstance(raw, dict):
                try:
                    position = Position(x=float(raw["x"]), y=float(raw["y"]))
                except (KeyError, TypeError, ValueError):
                    position = None
            name = blocked_by.get("prototype") or blocked_by.get("name")
            if isinstance(name, str) and name:
                prototype_name = name
        if prototype_name == "character":
            return None
        if position is None:
            position = fallback
        attempts = []
        mine = getattr(self.game_state, "mine_entity", None)
        if callable(mine):
            try:
                result = mine(position)
                return self._cleared_entry(
                    "mine_entity", prototype_name, position, result, attempts
                )
            except Exception as exc:
                attempts.append({"tool": "mine_entity", "error": str(exc)[:240]})
        prototype = (
            prototype_by_name.get(prototype_name)
            if prototype_name is not None
            else None
        )
        pickup = getattr(self.game_state, "pickup_entity", None)
        if prototype is not None and callable(pickup):
            try:
                result = pickup(prototype, position)
                if result:
                    return self._cleared_entry(
                        "pickup_entity", prototype_name, position, result, attempts
                    )
                attempts.append({"tool": "pickup_entity", "error": "nothing picked up"})
            except Exception as exc:
                attempts.append({"tool": "pickup_entity", "error": str(exc)[:240]})
        deconstruct = getattr(self.game_state, "deconstruct_area", None)
        if prototype_name is not None and callable(deconstruct):
            try:
                result = deconstruct(
                    Position(x=position.x - 4, y=position.y - 4),
                    Position(x=position.x + 4, y=position.y + 4),
                    prototype=prototype_name,
                    include_neutral=True,
                    max_entities=64,
                )
                if isinstance(result, dict) and result.get("removed"):
                    return self._cleared_entry(
                        "deconstruct_area", prototype_name, position, result, attempts
                    )
                attempts.append(
                    {"tool": "deconstruct_area", "error": "nothing removed"}
                )
            except Exception as exc:
                attempts.append({"tool": "deconstruct_area", "error": str(exc)[:240]})
        return None

    @staticmethod
    def _cleared_entry(tool, prototype_name, position, result, attempts):
        entry = {
            "tool": tool,
            "prototype": prototype_name,
            "position": {"x": position.x, "y": position.y},
            "result": json.loads(json.dumps(result, default=str)),
        }
        if attempts:
            entry["failed_attempts"] = attempts
        return entry

    @staticmethod
    def _coerce(value):
        return (
            value if isinstance(value, Position) else Position(x=value[0], y=value[1])
        )

    @classmethod
    def _rasterize(cls, points):
        points = [cls._coerce(value) for value in points]
        if len(points) < 2:
            raise ValueError("place_path needs at least two points")
        route = []
        for start, end in zip(points, points[1:]):
            dx, dy = end.x - start.x, end.y - start.y
            if dx and dy:
                raise ValueError(
                    "polyline segments must be axis-aligned; provide the corner explicitly"
                )
            length = int(round(abs(dx or dy)))
            if not math.isclose(abs(dx or dy), length):
                raise ValueError("path endpoints must lie on the same unit grid")
            sx = 0 if dx == 0 else (1 if dx > 0 else -1)
            sy = 0 if dy == 0 else (1 if dy > 0 else -1)
            for step in range(length + 1):
                point = Position(x=start.x + sx * step, y=start.y + sy * step)
                if not route or point != route[-1]:
                    route.append(point)
        return route

    @staticmethod
    def _direction(route, index):
        current = route[index]
        if index + 1 < len(route):
            dx, dy = route[index + 1].x - current.x, route[index + 1].y - current.y
        else:
            dx, dy = current.x - route[index - 1].x, current.y - route[index - 1].y
        if dx > 0:
            return Direction.RIGHT
        if dx < 0:
            return Direction.LEFT
        if dy > 0:
            return Direction.DOWN
        return Direction.UP

    def _tick(self):
        return int(
            self.connection.rcon_client.send_command("/sc rcon.print(game.tick)") or 0
        )
