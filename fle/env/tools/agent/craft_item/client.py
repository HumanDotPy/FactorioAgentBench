from time import sleep

from fle.env.game_types import Prototype
from fle.env.tools.agent.inspect_inventory.client import InspectInventory
from fle.env.tools import Tool


class CraftItem(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)
        self.inspect_inventory = InspectInventory(connection, game_state)

    def _action_expression(self, name: str, *args) -> str:
        parameters = ", ".join(str(arg) for arg in args)
        if self.lua_script_manager.runtime_bundled:
            suffix = f", {parameters}" if parameters else ""
            return f"remote.call('fle_runtime', 'dispatch', '{name}'{suffix})"
        return f"storage.actions.{name}({parameters})"

    def _crafting_status(self, name: str):
        raw = self.connection.rcon_client.send_command(
            "/sc rcon.print("
            + self._action_expression(
                "get_crafting_status", self.player_index, f'"{name}"'
            )
            + ")"
        )
        tick, count = (int(part) for part in str(raw).split(","))
        return tick, count

    def __call__(self, entity: Prototype, quantity: int = 1) -> int:
        """
        Craft an item from a Prototype if the ingredients exist in your inventory.
        :param entity: Entity to craft
        :param quantity: Quantity to craft
        :return: Number of items crafted
        """

        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        if hasattr(entity, "value"):
            name, _ = entity.value
        else:
            name = entity

        count_in_inventory = 0
        if not self.game_state.instance.fast:
            count_in_inventory = self.inspect_inventory()[entity]

        # Track elapsed ticks for fast forward
        ticks_before = self.game_state.instance.get_elapsed_ticks()

        success, elapsed = self.execute(self.player_index, name, quantity)

        if success != {} and isinstance(success, str):
            if success is None:
                raise Exception(
                    f"Could not craft a {name} - Ingredients cannot be crafted by hand."
                )
            else:
                result = self.get_error_message(success)
                raise Exception(result)

        # Sleep for the appropriate real-world time based on elapsed ticks
        ticks_after = self.game_state.instance.get_elapsed_ticks()
        ticks_added = ticks_after - ticks_before
        if ticks_added > 0:
            game_speed = self.game_state.instance.get_speed()
            real_world_sleep = ticks_added / 60 / game_speed if game_speed > 0 else 0
            sleep(real_world_sleep)

        if not self.game_state.instance.fast:
            # Compatibility action: wait for the native crafting queue rather
            # than pretending recipe duration elapsed. New programs should use
            # queue_craft so crafting can overlap movement and other options.
            now, count = self._crafting_status(name)
            timeout_tick = now + 60 * 60 * 10
            while count - count_in_inventory < success:
                if now >= timeout_tick:
                    raise TimeoutError(f"Timed out crafting {quantity}x {name}")
                sleep(0.1)
                now, count = self._crafting_status(name)

        return success
