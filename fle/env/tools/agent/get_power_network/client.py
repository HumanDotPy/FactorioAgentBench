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


class GetPowerNetwork(Tool):
    def __call__(
        self,
        position: Position,
        window_seconds: int = 5,
        include_members: bool = False,
    ) -> dict:
        """Read the raw electric network state at a point.

        Returns production and consumption watts per prototype, accumulator
        charge statistics, and optionally the poles on the network. Use it to
        inspect a connected factory; no satisfaction score is computed.

        :param position: Position of an electric pole or connected machine
        :param window_seconds: Averaging window: 5, 60, 600 or 3600
        :param include_members: Also list poles on the same network (bounded)
        :example get_power_network(Position(x=29, y=-82), window_seconds=60)
        :return: {entity, network_id, window_seconds, statistics_available,
            production_w, by_producer, consumption_w, by_consumer, storage,
            generator_count, consumer_count, truncated[, pole_count, members]}
        """
        if not isinstance(position, Position):
            raise ValueError("position must be a Position")  # noqa: TRY004
        if window_seconds not in {5, 60, 600, 3600}:
            raise ValueError("window_seconds must be 5, 60, 600, or 3600")
        if not isinstance(include_members, bool):
            raise ValueError("include_members must be a boolean")  # noqa: TRY004
        response, _ = self.execute(
            self.player_index,
            position.x,
            position.y,
            window_seconds,
            include_members,
        )
        if (
            not isinstance(response, dict)
            or "network_id" not in response
            or response.get("error")
        ):
            message = str(response).split(":")[-1].strip()
            raise Exception(  # noqa: TRY002 - matches the tool error convention
                f"Could not read power network at {position}: {message}"
            )
        return _normalize_arrays(response)
