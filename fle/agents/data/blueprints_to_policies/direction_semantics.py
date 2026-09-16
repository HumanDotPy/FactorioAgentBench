"""Agent-facing direction conventions shared by blueprint/SFT generators.

Blueprint JSON stores engine-native directions. For inserter prototypes the
engine direction is the PICKUP side, while agent-facing ``Direction`` values
name the DROP side (live-confirmed on 2.0.77). Generated programs must invert
inserter directions so the training data matches the tool contract.
"""

from fle.env.entities import Inserter
from fle.env.game_types import prototype_by_name

_INSERTER_NAME_SUFFIX = "inserter"


def is_inserter_prototype(name) -> bool:
    if not isinstance(name, str):
        return False
    prototype = prototype_by_name.get(name)
    if prototype is not None:
        entity_class = prototype.value[1]
        while isinstance(entity_class, tuple):
            entity_class = entity_class[1]
        if isinstance(entity_class, type) and issubclass(entity_class, Inserter):
            return True
    return name.endswith(_INSERTER_NAME_SUFFIX)


def agent_direction(name, engine_direction):
    """Convert a stored engine direction to the agent-facing convention."""
    if engine_direction is None:
        return None
    if is_inserter_prototype(name):
        return (engine_direction + 8) % 16
    return engine_direction
