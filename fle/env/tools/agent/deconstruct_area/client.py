import math

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools import Tool


def _normalize_arrays(value):
    """Convert integer-keyed mappings into lists, recursively.

    Lua array tables arrive through the RCON result parser as dicts keyed by
    rank (``{1: ..., 2: ...}``); callers expect plain lists.
    """

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


class DeconstructArea(Tool):
    def __call__(
        self,
        top_left: Position,
        bottom_right: Position,
        prototype: Prototype | str | None = None,
        include_neutral: bool = True,
        max_entities: int = 512,
    ) -> dict:
        """Deconstruct everything inside an axis-aligned rectangle.

        Removes player-force entities and returns their items (including
        inventory and belt-lane contents) to the player. Neutral trees and
        rocks are included when ``include_neutral`` is set and yield their
        mineable products. Resources, ghosts, corpses, cliffs, item stacks on
        the ground and characters are never touched.

        :param top_left: One corner of the rectangle as a Position
        :param bottom_right: Opposite corner of the rectangle as a Position
        :param prototype: Optional Prototype or name limiting what is removed
        :param include_neutral: Also remove neutral trees and rocks
        :param max_entities: Maximum entities to remove in one call (1-2048)
        :example deconstruct_area(Position(x=0, y=0), Position(x=8, y=8))
        :return: {status, area, removed, requested, items_returned, skipped,
                  truncated, inventory_full, tick}
        """
        if not isinstance(top_left, Position):
            raise ValueError("top_left must be a Position")  # noqa: TRY004
        if not isinstance(bottom_right, Position):
            raise ValueError("bottom_right must be a Position")  # noqa: TRY004
        if prototype is not None:
            if isinstance(prototype, Prototype):
                prototype = prototype.value[0]
            elif not isinstance(prototype, str) or not prototype:
                raise ValueError(
                    "prototype must be a Prototype, a nonempty string, or None"
                )
        if not isinstance(include_neutral, bool):
            raise ValueError("include_neutral must be a bool")  # noqa: TRY004
        if isinstance(max_entities, bool) or not isinstance(max_entities, int):
            raise ValueError(  # noqa: TRY004
                "max_entities must be an int between 1 and 2048"
            )
        if not 1 <= max_entities <= 2048:
            raise ValueError("max_entities must be between 1 and 2048")

        min_x = min(math.floor(top_left.x), math.floor(bottom_right.x))
        max_x = max(math.floor(top_left.x), math.floor(bottom_right.x))
        min_y = min(math.floor(top_left.y), math.floor(bottom_right.y))
        max_y = max(math.floor(top_left.y), math.floor(bottom_right.y))
        if max_x - min_x + 1 > 64 or max_y - min_y + 1 > 64:
            raise ValueError("area must be at most 64x64 tiles")

        self.ensure_reachable(Position(x=(min_x + max_x) / 2, y=(min_y + max_y) / 2))
        response, _ = self.execute(
            self.player_index,
            top_left.x,
            top_left.y,
            bottom_right.x,
            bottom_right.y,
            prototype,
            include_neutral,
            max_entities,
        )
        if (
            not isinstance(response, dict)
            or "status" not in response
            or "error" in response
        ):
            message = str(response).split(":")[-1].strip()
            raise Exception(  # noqa: TRY002 - matches the tool error convention
                f"Could not deconstruct area {top_left}-{bottom_right}: {message}"
            )
        return _normalize_arrays(response)
