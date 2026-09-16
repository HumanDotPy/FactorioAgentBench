from time import sleep

from fle.env.entities import Entity, Position
from fle.env.tools import Tool


class MineEntity(Tool):
    def __call__(self, target: Entity | Position) -> dict:
        """Mine or remove one neutral obstacle at a position.

        Trees and rocks with mineable products are mined into the character
        inventory and counted in manual production statistics; neutral stumps,
        corpses and productless rocks are destroyed. Use this instead of
        ``deconstruct_area`` to clear a single tree, trunk, stump or rock.

        :param target: Entity to mine or the Position of a tree, rock, stump or corpse
        :example mine_entity(nearest(Resource.Wood))
        :example mine_entity(Position(x=12, y=-3))
        :return: {name, position, items, removed}
        """
        if isinstance(target, Position):
            x, y = target.x, target.y
            name = None
        else:
            if not hasattr(target, "position") or not hasattr(target, "name"):
                raise TypeError("target must be an Entity or Position")
            fresh = (
                self.game_state.resolve_entity(target)
                if getattr(target, "id", None) is not None
                else target
            )
            x, y = fresh.position.x, fresh.position.y
            name = fresh.name

        self.ensure_reachable(Position(x=x, y=y), stop_distance=1.5)

        ticks_before = self.game_state.instance.get_elapsed_ticks()
        response, _ = self.execute(self.player_index, x, y, name)
        ticks_added = self.game_state.instance.get_elapsed_ticks() - ticks_before
        if ticks_added > 0:
            game_speed = self.game_state.instance.get_speed()
            if game_speed > 0:
                sleep(ticks_added / 60 / game_speed)

        if not isinstance(response, dict) or "removed" not in response:
            if isinstance(response, dict) and "error" in response:
                message = response["error"]
            else:
                message = str(response).split(":")[-1].strip()
            raise Exception(  # noqa: TRY002 - matches the tool error convention
                f"Could not mine entity at ({x}, {y}): {message}"
            )
        return response
