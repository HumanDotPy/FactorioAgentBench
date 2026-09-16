import pytest

from fle.envd.microtasks import get_microtask
from fle.envd.program_policy import ProgramPolicyViolation, validate_program

pytestmark = pytest.mark.no_factorio

_REACHABLE = {
    "micro_place_entity_next_to_v1": (
        "place_entity(Prototype.SmallElectricPole, position=p)"
    ),
    "micro_connect_offshore_pump_v1": "place_offshore_pump(p)",
    "micro_connect_belt_v1": ("place_path(Prototype.TransportBelt, [a, b, c])"),
}


@pytest.mark.parametrize("task_id,code", sorted(_REACHABLE.items()))
def test_required_microtask_actions_pass_the_default_profile(task_id, code):
    task = get_microtask(task_id)

    assert task.action_profile == "semantic-motor-v1"
    required = [
        constraint.limit
        for constraint in task.constraints
        if constraint.kind == "required_action"
    ]
    assert required
    for action in required:
        assert action in code
    validate_program(code, action_profile=task.action_profile)
    assert "connect_entities" not in task.goal
    assert "place_entity_next_to" not in task.goal


def test_default_profile_still_rejects_the_old_helpers():
    for code in (
        "connect_entities(a, b, Prototype.TransportBelt)",
        "nearest_buildable(Prototype.StoneFurnace)",
    ):
        with pytest.raises(ProgramPolicyViolation):
            validate_program(code)
