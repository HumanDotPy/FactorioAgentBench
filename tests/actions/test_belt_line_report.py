from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fle.env.entities import Position
from fle.env.tools.agent.place_path.belt_line_report.client import BeltLineReport

pytestmark = pytest.mark.no_factorio


def belt(x, direction):
    return {"position": {"x": x, "y": 0}, "direction": direction}


def missing(*_args, **_kwargs):
    raise Exception("no transport-belt at the requested position")


def make_tool(trace):
    tool = BeltLineReport.__new__(BeltLineReport)
    tool.name = "belt_line_report"
    tool.player_index = 1
    tool.game_state = SimpleNamespace(trace_belt=Mock(side_effect=trace))
    return tool


def straight_line_trace(position, max_tiles=64, upstream=False):
    if upstream:
        return {
            "tiles": [belt(1, "east"), belt(0, "east")],
            "blocker": {"position": {"x": -1, "y": 0}, "reason": "start_of_line"},
        }
    if position.x != 0:
        raise Exception("no transport-belt at the requested position")
    return {
        "tiles": [belt(0, "east"), belt(1, "east"), belt(2, "east")],
        "blocker": {"position": {"x": 3, "y": 0}, "reason": "end_of_line"},
    }


def test_clean_line_reports_no_issues():
    tool = make_tool(straight_line_trace)
    report = tool(Position(x=2, y=0), max_tiles=16)
    assert report["status"] == "clean"
    assert report["total_tiles"] == 3
    assert report["gaps"] == []
    assert report["mis_directed"] == []
    assert report["dead_ends"][0]["reason"] == "end_of_line"
    assert report["line_start"] == {"x": 0, "y": 0}


def test_gap_is_found_past_a_dead_end():
    def trace(position, max_tiles=64, upstream=False):
        if upstream:
            return {
                "tiles": [belt(2, "east")],
                "blocker": {"position": {"x": 1, "y": 0}, "reason": "start_of_line"},
            }
        return {
            "tiles": [belt(0, "east"), belt(1, "east"), belt(2, "east")],
            "blocker": {"position": {"x": 3, "y": 0}, "reason": "end_of_line"},
        }

    def trace_with_gap(position, max_tiles=64, upstream=False):
        if not upstream and position.x >= 3:
            if position.x == 4:
                return {"tiles": [belt(4, "east")], "blocker": {}}
            raise Exception("no transport-belt at the requested position")
        return trace(position, max_tiles=max_tiles, upstream=upstream)

    tool = make_tool(trace_with_gap)
    report = tool(Position(x=2, y=0), max_tiles=16, gap_probe_tiles=3)
    assert report["status"] == "issues"
    assert report["gaps"] == [
        {
            "after": {"x": 2, "y": 0},
            "resumes_at": {"x": 4, "y": 0},
            "missing": [{"x": 3, "y": 0}],
        }
    ]
    assert "interrupted" in report["next_step"]


def test_flow_reversal_is_reported_as_mis_directed():
    def trace(position, max_tiles=64, upstream=False):
        if upstream:
            return {
                "tiles": [belt(0, "east")],
                "blocker": {"position": {"x": -1, "y": 0}, "reason": "start_of_line"},
            }
        return {
            "tiles": [belt(0, "east"), belt(1, "west")],
            "blocker": {"position": {"x": 2, "y": 0}, "reason": "blocked_by_reversed_belt"},
        }

    tool = make_tool(trace)
    report = tool(Position(x=0, y=0), max_tiles=16, gap_probe_tiles=0)
    assert report["status"] == "issues"
    assert report["mis_directed"][0]["position"] == {"x": 1, "y": 0}
    assert report["mis_directed"][0]["issue"] == "flow reversal"
    assert "rotate" in report["next_step"]


def test_client_validates_arguments():
    tool = make_tool(straight_line_trace)
    with pytest.raises(ValueError, match="position must be a Position"):
        tool((0, 0))
    with pytest.raises(ValueError, match="max_tiles"):
        tool(Position(x=0, y=0), max_tiles=0)
    with pytest.raises(ValueError, match="gap_probe_tiles"):
        tool(Position(x=0, y=0), gap_probe_tiles=9)
    tool.game_state.trace_belt.assert_not_called()
