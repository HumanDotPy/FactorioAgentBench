from time import sleep

from fle.env.entities import Position
from fle.env.game_types import Resource
from fle.env.tools.agent.get_entity.client import GetEntity
from fle.env.tools.agent.move_to.client import MoveTo
from fle.env.tools.agent.nearest.client import Nearest
from fle.env.tools.agent.inspect_inventory.client import InspectInventory
from fle.env.tools import Tool


class HarvestResource(Tool):
    SELF_UNSTICK_ATTEMPTS = 2

    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)
        self.move_to = MoveTo(connection, game_state)
        self.nearest = Nearest(connection, game_state)
        self.get_entity = GetEntity(connection, game_state)
        self.inspect_inventory = InspectInventory(connection, game_state)

    def _action_expression(self, name: str, *args) -> str:
        parameters = ", ".join(str(arg) for arg in args)
        if self.lua_script_manager.runtime_bundled:
            suffix = f", {parameters}" if parameters else ""
            return f"remote.call('fle_runtime', 'dispatch', '{name}'{suffix})"
        suffix = parameters
        return f"storage.actions.{name}({suffix})"

    def __call__(self, position: Position, quantity=1, radius=10) -> int:
        """
        Harvest a resource at position (x, y) if it exists on the world.
        :param position: Position to harvest resource
        :param quantity: Quantity to harvest
        :example harvest_resource(nearest(Resource.Coal), 5)
        :example harvest_resource(nearest(Resource.Stone), 5)
        :return: The quantity of the resource harvested
        """
        assert isinstance(position, Position), (
            "First argument must be a Position object"
        )

        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        if not self.game_state.instance.fast:
            return self._harvest_native(position, quantity, radius)

        x, y = self.get_position(position)
        self.ensure_reachable(position, stop_distance=1.5)

        # Now we attempt to harvest.
        # In fast mode, this will always be successful (because we don't check if the resource is reachable)

        # Track elapsed ticks for fast forward
        ticks_before = self.game_state.instance.get_elapsed_ticks()

        response, elapsed = self.execute(self.player_index, x, y, quantity, radius)
        recovery = None
        if response == 0 or isinstance(response, str):
            recovery = self._recover_blocked_start(position)
            if recovery is not None:
                response, elapsed = self.execute(
                    self.player_index, x, y, quantity, radius
                )

        # Sleep for the appropriate real-world time based on elapsed ticks
        ticks_after = self.game_state.instance.get_elapsed_ticks()
        ticks_added = ticks_after - ticks_before
        if ticks_added > 0:
            game_speed = self.game_state.instance.get_speed()
            real_world_sleep = ticks_added / 60 / game_speed if game_speed > 0 else 0
            sleep(real_world_sleep)

        if response == 0 or isinstance(response, str):
            msg = str(response).split(":")[-1].strip()
            raise Exception(
                self._harvest_failure_message(None, position, msg, recovery)
            )

        return response

    def _harvest_status(self, item):
        raw = str(
            self.connection.rcon_client.send_command(
                "/sc rcon.print("
                + self._action_expression("get_harvest_status", self.player_index)
                + ")"
            )
        )
        parts = raw.split(",")
        if len(parts) == 3:
            tick, queue, count = (int(part) for part in parts)
            return tick, queue, count
        tick = self._native_tick()
        queue = int(parts[0])
        count = self.inspect_inventory()[item]
        return tick, queue, count

    def _reach_with_recovery(self, position):
        last_error = None
        for attempt in range(self.SELF_UNSTICK_ATTEMPTS + 1):
            try:
                self.ensure_reachable(position, stop_distance=1.5)
                return
            except Exception as exc:
                last_error = exc
                if attempt >= self.SELF_UNSTICK_ATTEMPTS:
                    raise
                if self._recover_blocked_start(position) is None:
                    raise
        raise last_error

    def _recover_blocked_start(self, position) -> dict | None:
        move = getattr(self, "move_to", None)
        if move is None or not hasattr(move, "self_unstick"):
            return None
        try:
            info = move.self_unstick(position, attempts=self.SELF_UNSTICK_ATTEMPTS)
        except Exception:
            return None
        if not isinstance(info, dict) or not info.get("moved"):
            return None
        return info

    def _harvest_failure_message(self, item, position, response, recovery) -> str:
        state = getattr(self, "game_state", None)
        location = getattr(state, "player_location", None)
        if isinstance(location, Position):
            where = f"character at ({location.x:.2f}, {location.y:.2f})"
        else:
            where = "character position unavailable"
        reason = (recovery or {}).get("reason") or "unknown"
        if reason == "start_free":
            reason = "start_free (no blocking entity or terrain found)"
        label = f" {item}" if item else ""
        return (
            f"Could not harvest{label} at ({position.x}, {position.y}): {response}; "
            f"{where}; start blocking reason: {reason}"
        )

    def _harvest_native(self, position, quantity, radius):
        resource = self.get_resource_type_at_position(position)
        item = resource[0]
        start_count = self.inspect_inventory()[item]
        harvested = 0
        while harvested < quantity:
            previous_harvested = harvested
            self._reach_with_recovery(position)
            response, _ = self.execute(
                self.player_index, position.x, position.y, quantity - harvested, radius
            )
            recovery = None
            if isinstance(response, str) or response == 0:
                recovery = self._recover_blocked_start(position)
                if recovery is not None:
                    response, _ = self.execute(
                        self.player_index,
                        position.x,
                        position.y,
                        quantity - harvested,
                        radius,
                    )
            if isinstance(response, str):
                raise RuntimeError(
                    self._harvest_failure_message(item, position, response, recovery)
                )
            last_progress_tick = self._native_tick()
            try:
                while True:
                    control = getattr(
                        getattr(self, "game_state", None), "_program_runtime", None
                    )
                    if control is not None:
                        control.boundary()
                    now, queue, count = self._harvest_status(item)
                    observed = count - start_count
                    if observed > harvested:
                        harvested = observed
                        last_progress_tick = now
                    if queue == 0:
                        break
                    if now - last_progress_tick >= 1800:
                        raise TimeoutError(
                            f"Harvesting {item} stalled for 30 simulated seconds; "
                            f"obtained {harvested}/{quantity}. Check target and reach."
                        )
                    sleep(0.1)
            finally:
                self.connection.rcon_client.send_command(
                    "/sc "
                    + self._action_expression("clear_harvest_queue", self.player_index)
                )
            if harvested < quantity:
                if harvested == previous_harvested:
                    raise RuntimeError(
                        f"Harvesting {item} completed without producing an item"
                    )
                position = self.nearest(resource)
        return harvested

    def _native_tick(self):
        return int(
            self.connection.rcon_client.send_command("/sc rcon.print(game.tick)") or 0
        )

    def get_resource_type_at_position(self, position: Position):
        x, y = self.get_position(position)
        entity_at_position = self.connection.rcon_client.send_command(
            "/silent-command rcon.print("
            + self._action_expression(
                "get_resource_name_at_position", self.player_index, x, y
            )
            + ")"
        )
        return self._resource_type_from_name(entity_at_position, position)

    @staticmethod
    def _resource_type_from_name(entity_name: str, position: Position | None = None):
        resource_types = {
            "coal": Resource.Coal,
            "copper-ore": Resource.CopperOre,
            "iron-ore": Resource.IronOre,
            "stone": Resource.Stone,
            "uranium-ore": Resource.UraniumOre,
        }
        if entity_name and entity_name.startswith("tree"):
            return Resource.Wood
        if entity_name in resource_types:
            return resource_types[entity_name]
        where = f" at {position.x}, {position.y}" if position is not None else ""
        raise Exception(f"Could not find resource to harvest{where}")
