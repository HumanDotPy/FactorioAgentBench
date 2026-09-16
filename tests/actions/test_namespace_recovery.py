import pytest

from fle.env.instance import FactorioInstance, GameControl
from fle.env.namespace import FactorioNamespace

pytestmark = pytest.mark.no_factorio


class _Instance:
    tcp_port = 1


def _namespace() -> FactorioNamespace:
    namespace = FactorioNamespace(_Instance(), 0)
    namespace.score = lambda: (0.0, 0.0)
    return namespace


def test_partial_assignments_are_kept_and_divergence_is_marked():
    namespace = _namespace()
    _, _, output = namespace.eval_with_timeout(
        "flag = True\nif flag:\n    assigned = 10\n    raise RuntimeError('boom')\n"
    )

    assert namespace.persistent_vars["flag"] is True
    assert namespace.persistent_vars["assigned"] == 10
    assert "not rolled back" in output
    assert "RuntimeError" in output


def test_loop_progress_before_a_failure_is_kept():
    namespace = _namespace()
    _, _, output = namespace.eval_with_timeout(
        "total = 0\n"
        "for index in range(3):\n"
        "    total = total + 10\n"
        "    if index == 1:\n"
        "        raise ValueError('stop')\n"
    )

    assert namespace.persistent_vars["total"] == 20
    assert "not rolled back" in output
    assert "ValueError" in output


def test_successful_state_is_unchanged_by_the_no_rollback_path():
    namespace = _namespace()
    score, automated, output = namespace.eval_with_timeout(
        "value = 7\nvalue = value + 1\n"
    )

    assert score == 0.0
    assert automated == 0.0
    assert namespace.persistent_vars["value"] == 8
    assert "not rolled back" not in output


class _Rcon:
    def __init__(self, responses):
        self.responses = list(responses)
        self.commands = []

    def send_command(self, command):
        self.commands.append(command)
        return self.responses.pop(0) if self.responses else "false"


class _Manager:
    runtime_bundled = False

    def __init__(self):
        self.cache_scripts = True
        self.init_calls = []
        self.tool_calls = []

    def load_init_into_game(self, name):
        self.init_calls.append(name)

    def load_tool_into_game(self, name):
        self.tool_calls.append(name)


def _non_bundled_instance(responses):
    instance = FactorioInstance.__new__(FactorioInstance)
    instance.rcon_client = _Rcon(responses)
    instance.lua_script_manager = _Manager()
    instance.controllers = {"move_to": object(), "place_entity": object()}
    return instance


def test_non_bundled_runtime_reloads_after_storage_functions_are_stripped():
    instance = _non_bundled_instance(["false", "true"])

    assert instance.ensure_non_bundled_runtime() is True

    manager = instance.lua_script_manager
    assert manager.init_calls[0] == "initialise"
    assert "utils" in manager.init_calls
    assert sorted(manager.tool_calls) == ["move_to", "place_entity"]
    assert manager.cache_scripts is True


def test_non_bundled_runtime_skips_reload_when_functions_exist():
    instance = _non_bundled_instance(["true"])

    assert instance.ensure_non_bundled_runtime() is False
    assert instance.lua_script_manager.init_calls == []
    assert instance.lua_script_manager.cache_scripts is True


def test_non_bundled_runtime_raises_when_reload_fails():
    instance = _non_bundled_instance(["false", "false"])

    with pytest.raises(RuntimeError, match="could not be reloaded"):
        instance.ensure_non_bundled_runtime()


def test_require_non_bundled_function_names_the_save_load_limitation():
    instance = _non_bundled_instance(["false", "true", "false"])

    with pytest.raises(RuntimeError, match="do not survive a save/load"):
        instance.require_non_bundled_function(
            "storage.utils and storage.utils.remove_enemies",
            "storage.utils.remove_enemies",
        )


def test_game_control_retries_the_elapsed_tick_counter_after_a_reload():
    rcon = _Rcon(["nil", "120"])
    control = GameControl(rcon, None, runtime_ready=lambda: True)

    assert control.get_elapsed_ticks() == 120
    assert len(rcon.commands) == 2


def test_game_control_reports_zero_when_the_counter_stays_missing():
    rcon = _Rcon(["nil", "nil"])
    control = GameControl(rcon, None, runtime_ready=lambda: True)

    assert control.get_elapsed_ticks() == 0
