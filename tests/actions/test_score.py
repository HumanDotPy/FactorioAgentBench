from unittest.mock import Mock

import pytest

from fle.env.tools.admin.score.client import Reward as AdminReward
from fle.env.tools.agent.score.client import Reward


def _reward(cls):
    tool = cls.__new__(cls)
    tool.player_index = 1
    tool.name = "score"
    return tool


@pytest.mark.no_factorio
def test_agent_score_does_not_rebase_the_server_result():
    tool = _reward(Reward)
    tool.execute = Mock(return_value=({"player": 120, "automated": 80}, 0))
    assert tool() == (120, 80)


@pytest.mark.no_factorio
def test_agent_score_raises_on_error_response_without_key_access():
    tool = _reward(Reward)
    tool.execute = Mock(return_value=("Error: score unavailable", 0))
    with pytest.raises(Exception, match="Could not get player score"):
        tool()


@pytest.mark.no_factorio
def test_agent_score_tolerates_missing_keys():
    tool = _reward(Reward)
    tool.execute = Mock(return_value=({}, 0))
    assert tool() == (0, 0)


@pytest.mark.no_factorio
def test_admin_score_raises_on_error_response():
    tool = _reward(AdminReward)
    tool.execute = Mock(return_value=("Error: score unavailable", 0))
    with pytest.raises(Exception, match="Could not get player score"):
        tool()


@pytest.mark.no_factorio
def test_admin_score_returns_goal():
    tool = _reward(AdminReward)
    tool.execute = Mock(return_value=({"player": 7, "goal": "automate"}, 0))
    assert tool() == (7, "automate")


def test_get_score(game):
    score, _ = game.score()
    assert isinstance(score, int)
