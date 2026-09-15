from fle.env.entities import Entity
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


class GetEntityPorts(Tool):
    def __call__(self, entity: Entity) -> dict:
        """Read the fluid connection ports of an entity from the live game.

        Returns the entity id and name plus ``inputs`` (ports whose
        ``flow_direction`` is ``input``), ``outputs`` (ports whose
        ``flow_direction`` is ``output``) and ``ports`` (every pipe
        connection). Each port carries ``x``, ``y``, ``fluidbox_index``,
        ``flow_direction`` (``input``, ``output`` or ``input-output``),
        ``connection_type`` and, when exposed, ``direction``. Ports also
        carry ``connected`` (``true``/``false``, absent when the runtime
        cannot resolve it), ``peers`` when connected, and ``attach_tiles``
        when open: the tile(s) where a pipe makes the connection, best
        candidate first. Entities without a fluidbox return empty lists.

        :param entity: Entity to inspect (resolved fresh when it has an id)
        :example get_entity_ports(boiler)
        :return: {entity_id, name, inputs, outputs, ports}
        """
        fresh = (
            self.game_state.resolve_entity(entity) if entity.id is not None else entity
        )
        response, _ = self.execute(
            self.player_index, fresh.position.x, fresh.position.y, fresh.name
        )
        if not isinstance(response, dict) or "entity_id" not in response:
            if isinstance(response, dict) and "error" in response:
                message = response["error"]
            else:
                message = str(response).split(":")[-1].strip()
            raise Exception(  # noqa: TRY002 - matches the tool error convention
                f"Could not read entity ports for {fresh.name}: {message}"
            )
        return _normalize_arrays(response)
