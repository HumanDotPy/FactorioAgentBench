import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from fle.env.tools.agent.sleep.client import Sleep


@pytest.mark.parametrize("speed", [1, 2, 10])
def test_sleep(game, speed):
    game.instance.set_speed(speed)
    start = time.time()
    game.sleep(10)
    elapsed = time.time() - start
    assert elapsed * speed - 10 < 1, f"Sleep behaved unexpectedly at speed {speed}"


@pytest.mark.no_factorio
def test_sleep_charges_action_ticks_after_simulation_wait():
    tool = Sleep.__new__(Sleep)
    tool.connection = object()
    tool.game_state = SimpleNamespace()
    tool.execute = Mock()

    with patch("fle.env.tools.agent.wait.client.Wait") as wait_type:
        assert tool(2) is True

    wait_type.assert_called_once_with(tool.connection, tool.game_state)
    wait_type.return_value.assert_called_once_with(120)
    tool.execute.assert_called_once_with(2)
