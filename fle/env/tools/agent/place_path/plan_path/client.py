from fle.env import Direction
from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools import Tool
from fle.env.tools.agent.place_path.client import PlacePath

MAX_PLAN_TILES = 256
MAX_WIDTH = 8


def _normalize_arrays(value):
    if isinstance(value, dict):
        keys = list(value.keys())
        if keys and all(
            isinstance(key, (int, str)) and str(key).lstrip("-").isdigit()
            for key in keys
        ):
            return [
                _normalize_arrays(value[key])
                for key in sorted(keys, key=lambda key: int(key))
            ]
        return {key: _normalize_arrays(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_arrays(item) for item in value]
    return value


class PlanPath(Tool):
    def load(self):
        self.lua_script_manager.load_tool_into_game("place_path")

    def __call__(
        self,
        start: Position | tuple[float, float],
        end: Position | tuple[float, float],
        width: int = 1,
        prototype: Prototype = Prototype.TransportBelt,
    ) -> dict:
        start = self._coerce(start)
        end = self._coerce(end)
        if (
            isinstance(width, bool)
            or not isinstance(width, int)
            or not 1 <= width <= MAX_WIDTH
        ):
            raise ValueError(f"width must be an integer between 1 and {MAX_WIDTH}")
        if not isinstance(prototype, Prototype):
            raise ValueError("prototype must be a Prototype")
        route = PlacePath._rasterize([start, end])
        directions = [PlacePath._direction(route, index) for index in range(len(route))]
        tiles = []
        seen = set()
        for point, direction in zip(route, directions):
            offsets = [(0, 0)]
            if width > 1:
                offsets += [
                    self._lateral(direction, offset) for offset in range(1, width)
                ]
            for dx, dy in offsets:
                key = (point.x + dx, point.y + dy)
                if key in seen:
                    continue
                seen.add(key)
                tiles.append({"x": key[0], "y": key[1], "direction": direction.value})
        if len(tiles) > MAX_PLAN_TILES:
            raise ValueError(
                f"planned corridor exceeds {MAX_PLAN_TILES} tiles; shorten it or "
                "split it into segments"
            )
        response, _ = self.execute(self.player_index, prototype.value[0], tiles)
        if not isinstance(response, dict) or "tiles" not in response:
            if isinstance(response, str):
                raise ValueError(response.strip() or "plan_path failed")
            raise RuntimeError(f"Could not plan path: {response}")
        response = _normalize_arrays(response)
        response["start"] = {"x": start.x, "y": start.y}
        response["end"] = {"x": end.x, "y": end.y}
        response["width"] = width
        response["status"] = "clear" if response.get("placeable") else "blocked"
        response["blockers"] = [
            entry for entry in response["tiles"] if not entry.get("placeable")
        ]
        return response

    @staticmethod
    def _lateral(direction, offset):
        if direction == Direction.RIGHT:
            return (0, offset)
        if direction == Direction.LEFT:
            return (0, -offset)
        if direction == Direction.DOWN:
            return (-offset, 0)
        return (offset, 0)

    @staticmethod
    def _coerce(value):
        if isinstance(value, Position):
            return value
        if isinstance(value, (tuple, list)) and len(value) == 2:
            return Position(x=float(value[0]), y=float(value[1]))
        raise ValueError("start and end must be Position or (x, y) pairs")
