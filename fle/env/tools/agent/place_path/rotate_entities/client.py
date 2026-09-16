import os

from fle.env import DirectionInternal
from fle.env.entities import Direction as DirectionA
from fle.env.entities import Entity, Position
from fle.env.tools import Tool


class RotateEntities(Tool):
    """Rotate a list of existing entities to one direction in a single call."""

    def load(self):
        self.lua_script_manager.load_tool_into_game(f"place_path{os.sep}{self.name}")

    def __call__(self, entities, direction: DirectionInternal = DirectionInternal.UP):
        if not isinstance(entities, (list, tuple)) or not entities:
            raise ValueError("entities must be a non-empty list")
        if not isinstance(direction, (DirectionInternal, DirectionA)) and not (
            hasattr(direction, "name") and hasattr(direction, "value")
        ):
            raise ValueError("direction must be a Direction")
        entries = [self._entry(entity) for entity in entities]
        response, _ = self.execute(
            self.player_index,
            entries,
            DirectionInternal.to_factorio_direction(direction),
        )
        if not isinstance(response, dict) or response.get("error"):
            message = (
                response.get("error") if isinstance(response, dict) else str(response)
            )
            raise RuntimeError(f"Could not rotate entities: {message}")
        response["requested_direction"] = direction.name
        return response

    @staticmethod
    def _entry(entity):
        if isinstance(entity, Entity):
            return {
                "x": entity.position.x,
                "y": entity.position.y,
                "name": entity.name,
            }
        if isinstance(entity, Position):
            return {"x": entity.x, "y": entity.y}
        if isinstance(entity, (tuple, list)) and len(entity) == 2:
            return {"x": float(entity[0]), "y": float(entity[1])}
        if isinstance(entity, dict) and "x" in entity and "y" in entity:
            entry = {"x": float(entity["x"]), "y": float(entity["y"])}
            if entity.get("name"):
                entry["name"] = entity["name"]
            return entry
        raise ValueError(
            "entities must contain Entity, Position, (x, y), or {x, y} items"
        )
