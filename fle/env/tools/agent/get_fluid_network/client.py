from fle.env.entities import Position
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


class GetFluidNetwork(Tool):
    def __call__(
        self,
        position: Position,
        include_members: bool = False,
        max_entities: int = 512,
    ) -> dict:
        """Report the physical state of the fluid network at a position.

        Resolves the pipe, tank, pump, or fluid machine at ``position`` and
        walks its connected segment: the fluid it holds, the total amount and
        capacity, the fill ratio, and how many pipes, tanks, pumps, and
        machines share it. Read-only; use it to verify fluid delivery before
        or after connecting machines.

        :param position: Position of a pipe, tank, pump, or fluid machine
        :param include_members: Include the per-entity member list (max 64)
        :param max_entities: Maximum entities to walk (1-4096)
        :example get_fluid_network(Position(x=29, y=-82))
        :return: {entity, segment_id, fluid, amount, capacity, fill_ratio,
                  entity_count, pipe_count, tank_count, pump_count,
                  machine_count, entities_truncated, members?}
        """
        if not isinstance(position, Position):
            raise ValueError("position must be a Position")  # noqa: TRY004
        if not isinstance(include_members, bool):
            raise ValueError("include_members must be a bool")  # noqa: TRY004
        if isinstance(max_entities, bool) or not isinstance(max_entities, int):
            raise ValueError("max_entities must be an int")  # noqa: TRY004
        if not 1 <= max_entities <= 4096:
            raise ValueError("max_entities must be between 1 and 4096")
        response, _ = self.execute(
            self.player_index,
            position.x,
            position.y,
            include_members,
            max_entities,
        )
        if not isinstance(response, dict) or not (
            "segment_id" in response or "entity" in response
        ):
            message = str(response).split(":")[-1].strip()
            raise Exception(  # noqa: TRY002 - matches the tool error convention
                f"Could not read fluid network at {position}: {message}"
            )
        return _normalize_arrays(response)
