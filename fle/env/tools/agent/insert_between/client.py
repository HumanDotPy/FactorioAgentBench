from fle.env.entities import Entity, Position
from fle.env.game_types import Prototype
from fle.env.tools import Tool


class InsertBetween(Tool):
    """Bridge two placed entities with an inserter.

    The inserter is placed on a free tile whose pickup side reaches ``source``
    and whose drop side reaches ``target`` (agent-facing inserter directions
    name the drop side). Returns a receipt with the chosen tile, direction and
    pickup/drop tiles, or a precise reason when no legal placement exists.
    """

    def __call__(
        self,
        source,
        target,
        inserter: Prototype = Prototype.BurnerInserter,
    ) -> dict:
        source_position = source.position if isinstance(source, Entity) else source
        target_position = target.position if isinstance(target, Entity) else target
        if not isinstance(source_position, Position) or not isinstance(
            target_position, Position
        ):
            raise ValueError("source and target must be Entity or Position objects")
        if not isinstance(inserter, Prototype):
            raise ValueError("inserter must be a Prototype")

        name, _ = inserter.value
        midpoint = Position(
            x=(source_position.x + target_position.x) / 2,
            y=(source_position.y + target_position.y) / 2,
        )
        self.ensure_reachable(midpoint)

        response, elapsed = self.execute(
            self.player_index,
            name,
            source_position.x,
            source_position.y,
            target_position.x,
            target_position.y,
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"insert_between({name}) returned {response!r}")
        return response
