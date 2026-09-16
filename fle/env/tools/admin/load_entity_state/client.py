import base64
import json
import logging
import zlib
from typing import Union, List, Dict

from fle.env.tools import Tool

logger = logging.getLogger(__name__)


class LoadEntityState(Tool):
    def __init__(self, *args):
        super().__init__(*args)

    def __call__(self, entities: Union[str, List[Dict]], decompress=False) -> bool:
        """
        Loads the entity state back into the game.
        :param entities: Either a list of un-serialized dictionaries or a string containing Base64 encoded JSON data representing the entities to load.
        :return: True if successful, False otherwise
        """

        if isinstance(entities, str):
            entities = base64.b64decode(entities)
            if decompress:
                entities = zlib.decompress(entities)
        else:
            entities = json.dumps(entities)

        result, _ = self.execute(self.player_index, entities)
        if isinstance(result, dict):
            leftover = result.get("leftover") or []
            if leftover:
                logger.warning(
                    "Entity-state restore could not place %d leftover item "
                    "stack(s): %s",
                    len(leftover),
                    leftover,
                )
            result = result.get("restored", result)
        if result is not True and result != 1:
            raise RuntimeError(f"Factorio entity-state restore failed: {result}")
        return True
