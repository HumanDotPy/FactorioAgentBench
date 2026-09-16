from fle.env import Direction, DirectionInternal
from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools import Tool


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


class PlanPlacement(Tool):
    def load(self):
        self.lua_script_manager.load_tool_into_game("can_place_entity")

    def __call__(
        self,
        entity: Prototype,
        position: Position | tuple[float, float],
        direction: Direction = Direction.UP,
    ) -> dict:
        if not isinstance(entity, Prototype):
            raise ValueError("entity must be a Prototype")
        if isinstance(position, tuple):
            position = Position(x=position[0], y=position[1])
        if not isinstance(position, Position):
            raise ValueError("position must be a Position or (x, y) tuple")
        if not isinstance(direction, (Direction, DirectionInternal)):
            raise ValueError("direction must be a Direction")
        name, _ = entity.value
        response, _ = self.execute(
            self.player_index, name, direction.value, position.x, position.y
        )
        if not isinstance(response, dict) or "placeable" not in response:
            if isinstance(response, str):
                raise ValueError(response.strip() or "plan_placement failed")
            if isinstance(response, dict) and response.get("error"):
                raise ValueError(str(response.get("message") or response.get("error")))
            raise RuntimeError(f"Could not plan placement: {response}")
        return _normalize_arrays(response)
