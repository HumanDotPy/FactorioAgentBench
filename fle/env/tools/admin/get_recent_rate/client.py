from typing import Any

from fle.env.tools import Tool


class GetRecentRate(Tool):
    """Cheap privileged production-rate query backed by LuaFlowStatistics."""

    def __call__(self, item_name: Any, window_seconds: Any = 5) -> dict[str, Any]:
        if isinstance(item_name, str) and not isinstance(
            window_seconds, (list, tuple, set)
        ):
            response, _ = self.execute(self.player_index, item_name, window_seconds)
            return response
        if isinstance(item_name, str):
            items = [item_name]
        else:
            items = [str(item) for item in item_name]
        if isinstance(window_seconds, (list, tuple, set)):
            windows = [int(window) for window in window_seconds]
        else:
            windows = [int(window_seconds)]
        response, _ = self.execute(self.player_index, items, windows)
        return response
