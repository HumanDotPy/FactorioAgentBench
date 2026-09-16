import math
from typing import List, Optional

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools import Tool
from fle.env.tools.agent.deconstruct_area.client import _normalize_arrays

MAX_WALKS = 64


class ExtractArea(Tool):
    def __call__(
        self,
        top_left: Position,
        bottom_right: Position,
        items: Optional[List[Prototype]] = None,
        path: bool = True,
        interaction_radius: float = 10.0,
        max_entities: int = 512,
        max_items: int = 4096,
        include_inputs: bool = False,
    ) -> dict:
        """Batch-extract items from machine inventories inside a rectangle.

        Only item stacks move; no entity is ever destroyed. By default only
        product/storage slots are scanned (furnace, assembler and silo outputs,
        chests, vehicle trunks); fuel, machine inputs, modules, ammo and robot
        slots are scanned only when ``include_inputs=True``. ``items=None``
        takes every stack found in the scanned slots, otherwise only the named
        prototypes are taken. ``path=True`` walks to machines reported out of
        reach and retries; ``path=False`` performs a single reachable-only call.
        In fast mode the runtime ignores reach checks, so a single call always
        covers the rectangle.

        :param top_left: One corner of the rectangle as a Position
        :param bottom_right: Opposite corner of the rectangle as a Position
        :param items: Optional Prototypes or names limiting what is taken
        :param path: Whether the character may walk to out-of-reach machines
        :param interaction_radius: Reach in tiles before an entity is skipped
        :param max_entities: Maximum entities scanned in one call
        :param max_items: Maximum items extracted in one call
        :param include_inputs: Also scan fuel/input/module/ammo/robot slots
        :example extract_area(Position(x1,y1), Position(x2,y2), items=[Prototype.IronPlate])
        :return: {status, area, scanned, extracted, out_of_reach, inventory_full,
                  truncated, tick}
        """
        if not isinstance(top_left, Position):
            raise ValueError("top_left must be a Position")
        if not isinstance(bottom_right, Position):
            raise ValueError("bottom_right must be a Position")
        item_names = None
        if items is not None:
            if not isinstance(items, (list, tuple)) or not items:
                raise ValueError(
                    "items must be a nonempty list of Prototype or string names, "
                    "or None"
                )
            item_names = []
            for item in items:
                if isinstance(item, Prototype):
                    name, _ = item.value
                elif isinstance(item, str) and item:
                    name = item
                else:
                    raise ValueError(
                        "items must contain only Prototype or nonempty string names"
                    )
                item_names.append(name)
        if not isinstance(path, bool):
            raise ValueError("path must be a bool")
        if (
            isinstance(interaction_radius, bool)
            or not isinstance(interaction_radius, (int, float))
            or interaction_radius <= 0
        ):
            raise ValueError("interaction_radius must be a positive number")
        if (
            isinstance(max_entities, bool)
            or not isinstance(max_entities, int)
            or max_entities < 1
        ):
            raise ValueError("max_entities must be a positive int")
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items < 1
        ):
            raise ValueError("max_items must be a positive int")
        if not isinstance(include_inputs, bool):
            raise ValueError("include_inputs must be a bool")

        min_x = min(math.floor(top_left.x), math.floor(bottom_right.x))
        max_x = max(math.floor(top_left.x), math.floor(bottom_right.x))
        min_y = min(math.floor(top_left.y), math.floor(bottom_right.y))
        max_y = max(math.floor(top_left.y), math.floor(bottom_right.y))
        if max_x - min_x + 1 > 64 or max_y - min_y + 1 > 64:
            raise ValueError("area must be at most 64x64 tiles")

        args = (
            self.player_index,
            top_left.x,
            top_left.y,
            bottom_right.x,
            bottom_right.y,
            item_names,
            interaction_radius,
            max_entities,
            max_items,
            include_inputs,
        )
        response = self._checked(self.execute(*args)[0], top_left, bottom_right)
        if not path:
            return response

        extracted = dict(response.get("extracted") or {})
        location = getattr(getattr(self, "game_state", None), "player_location", None)
        walks = 0
        while (
            response.get("out_of_reach")
            and response.get("inventory_full") is None
            and walks < MAX_WALKS
        ):
            target = _nearest(response["out_of_reach"], location)
            before = _reach_positions(response["out_of_reach"])
            reached = self.ensure_reachable(
                Position(x=target["position"]["x"], y=target["position"]["y"])
            )
            if isinstance(reached, Position):
                location = reached
            response = self._checked(self.execute(*args)[0], top_left, bottom_right)
            for name, count in (response.get("extracted") or {}).items():
                extracted[name] = extracted.get(name, 0) + count
            walks += 1
            if _reach_positions(response.get("out_of_reach") or []) == before:
                break
        response["extracted"] = extracted
        return response

    def _checked(self, response, top_left, bottom_right):
        if (
            not isinstance(response, dict)
            or "status" not in response
            or "error" in response
        ):
            message = str(response).split(":")[-1].strip()
            raise Exception(
                f"Could not extract area {top_left}-{bottom_right}: {message}"
            )
        response = _normalize_arrays(response)
        if isinstance(response.get("out_of_reach"), dict):
            response["out_of_reach"] = []
        response.setdefault("inventory_full", None)
        return response


def _nearest(entries, location):
    if location is None:
        return entries[0]

    def distance(entry):
        position = entry.get("position") or {}
        return math.hypot(
            float(position.get("x", 0)) - location.x,
            float(position.get("y", 0)) - location.y,
        )

    return min(entries, key=distance)


def _reach_positions(entries):
    return frozenset(
        (float(entry["position"]["x"]), float(entry["position"]["y"]))
        for entry in entries
    )
