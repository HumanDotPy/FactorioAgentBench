import os

from fle.env.entities import Position
from fle.env.tools import Tool

FLOW_VECTORS = {
    "north": (0, -1),
    "east": (1, 0),
    "south": (0, 1),
    "west": (-1, 0),
}


class BeltLineReport(Tool):
    """Audit a whole belt line in one call: gaps, dead ends, mis-directed corners."""

    def load(self):
        self.lua_script_manager.load_tool_into_game(f"place_path{os.sep}{self.name}")

    def __call__(self, position: Position, max_tiles: int = 128, gap_probe_tiles: int = 4):
        if not isinstance(position, Position):
            raise ValueError("position must be a Position")
        if isinstance(max_tiles, bool) or not 1 <= int(max_tiles) <= 256:
            raise ValueError("max_tiles must be between 1 and 256")
        if isinstance(gap_probe_tiles, bool) or not 0 <= int(gap_probe_tiles) <= 8:
            raise ValueError("gap_probe_tiles must be between 0 and 8")
        trace = getattr(self.game_state, "trace_belt", None)
        if trace is None:
            raise RuntimeError("belt_line_report requires the trace_belt tool")
        max_tiles = int(max_tiles)
        gap_probe_tiles = int(gap_probe_tiles)
        upstream = trace(position, max_tiles=max_tiles, upstream=True)
        start = self._line_start(upstream, position)
        downstream = trace(start, max_tiles=max_tiles, upstream=False)
        report = self._analyze(downstream, gap_probe_tiles)
        report["query"] = {"x": position.x, "y": position.y}
        report["line_start"] = {"x": start.x, "y": start.y}
        report["source"] = upstream.get("blocker")
        return report

    @staticmethod
    def _line_start(upstream, fallback):
        tiles = upstream.get("tiles") or []
        if not tiles:
            return fallback
        position = tiles[-1].get("position") or {}
        return Position(x=float(position.get("x", fallback.x)), y=float(position.get("y", fallback.y)))

    def _analyze(self, downstream, probe_tiles):
        tiles = downstream.get("tiles") or []
        blocker = downstream.get("blocker") or {}
        corners = []
        misdirected = []
        for previous, current in zip(tiles, tiles[1:]):
            previous_direction = previous.get("direction")
            current_direction = current.get("direction")
            if current_direction != previous_direction:
                corners.append(
                    {
                        "position": current.get("position"),
                        "from": previous_direction,
                        "to": current_direction,
                    }
                )
            previous_vector = FLOW_VECTORS.get(previous_direction)
            current_vector = FLOW_VECTORS.get(current_direction)
            if previous_vector and current_vector == (
                -previous_vector[0],
                -previous_vector[1],
            ):
                misdirected.append(
                    {
                        "position": current.get("position"),
                        "direction": current_direction,
                        "approaching_from": previous_direction,
                        "issue": "flow reversal",
                    }
                )
        dead_ends = []
        reason = blocker.get("reason")
        end = tiles[-1].get("position") if tiles else None
        if end is not None:
            dead_ends.append(
                {
                    "position": end,
                    "reason": reason or "unknown",
                    "entity": blocker.get("entity"),
                    "next_tile": blocker.get("position"),
                }
            )
        if reason == "blocked_by_reversed_belt":
            misdirected.append(
                {
                    "position": end,
                    "direction": (tiles[-1].get("direction") if tiles else None),
                    "approaching_from": None,
                    "issue": "belt at the next tile flows against the line",
                    "next_tile": blocker.get("position"),
                }
            )
        gaps = []
        if tiles and probe_tiles and reason in {"end_of_line", "blocked_by_reversed_belt"}:
            gaps = self._probe_gaps(tiles[-1], blocker, probe_tiles)
        status = "clean" if not gaps and not misdirected else "issues"
        return {
            "status": status,
            "total_tiles": len(tiles),
            "start": tiles[0].get("position") if tiles else None,
            "end": end,
            "corners": corners,
            "gaps": gaps,
            "dead_ends": dead_ends,
            "mis_directed": misdirected,
            "blocker": blocker,
            "next_step": self._next_step(status, gaps, misdirected),
        }

    @staticmethod
    def _next_step(status, gaps, misdirected):
        if gaps:
            first = gaps[0]
            return (
                f"belt line is interrupted at {first['after']}; the line resumes at "
                f"{first['resumes_at']} - fill the missing tiles or place_path between them"
            )
        if misdirected:
            first = misdirected[0]
            return (
                f"belt at {first['position']} flows back into the line; rotate it "
                f"with rotate_entities([...], Direction.X) or rotate_entity"
            )
        if status == "clean":
            return "line is continuous with no reversed flow"
        return "inspect the dead end before extending the line"

    def _probe_gaps(self, end, blocker, probe_tiles):
        vector = FLOW_VECTORS.get(end.get("direction"))
        if vector is None:
            return []
        origin = blocker.get("position") or end.get("position") or {}
        origin_x = float(origin.get("x", end["position"]["x"]))
        origin_y = float(origin.get("y", end["position"]["y"]))
        for offset in range(1, probe_tiles + 1):
            probe = Position(
                x=origin_x + vector[0] * offset,
                y=origin_y + vector[1] * offset,
            )
            if self._belt_at(probe):
                missing = [
                    {
                        "x": origin_x + vector[0] * index,
                        "y": origin_y + vector[1] * index,
                    }
                    for index in range(offset)
                ]
                return [
                    {
                        "after": end.get("position"),
                        "resumes_at": {"x": probe.x, "y": probe.y},
                        "missing": missing,
                    }
                ]
        return []

    def _belt_at(self, point):
        try:
            self.game_state.trace_belt(point, max_tiles=1)
        except Exception:
            return False
        return True
