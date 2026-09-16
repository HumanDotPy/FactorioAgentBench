import hashlib

import pytest

from fle.envd.action_reference import (
    ACTION_PROFILE_REFERENCE,
    ACTION_PROFILE_REFERENCE_ID,
    ACTION_PROFILE_REFERENCE_SHA256,
)
from fle.envd.program_policy import ProgramPolicyViolation, validate_program

pytestmark = pytest.mark.no_factorio


def test_reference_id_sha_and_id_are_consistent():
    assert ACTION_PROFILE_REFERENCE_ID == "semantic-motor-v1/reference-v12"
    assert (
        hashlib.sha256(ACTION_PROFILE_REFERENCE.encode("utf-8")).hexdigest()
        == ACTION_PROFILE_REFERENCE_SHA256
    )
    assert "rejected here" in ACTION_PROFILE_REFERENCE


def test_reference_registers_nested_belt_tools():
    assert "rotate_entities(entities, direction)" in ACTION_PROFILE_REFERENCE
    assert "belt_line_report(position, max_tiles=128, gap_probe_tiles=4)" in (
        ACTION_PROFILE_REFERENCE
    )


def test_reference_documents_wait_manual_production_opt_in():
    assert "exclude manual production unless include_manual_production=True" in (
        ACTION_PROFILE_REFERENCE
    )


@pytest.mark.parametrize(
    "code",
    [
        "place_entity(Prototype.StoneFurnace, position=p, exact=False)",
        "place_entity(Prototype.StoneFurnace, position=p, exact=0)",
        "place_entity(Prototype.StoneFurnace, position=p, exact=None)",
        "place_entity(Prototype.StoneFurnace, position=p, False)",
        "place_entity(**options)",
        "move_to(p, Prototype.TransportBelt)",
        "move_to(p, None, Prototype.TransportBelt)",
        "move_to(p, **options)",
        "set_entity_recipe(**options)",
        "p = place_entity\np(Prototype.StoneFurnace, position=p, exact=False)",
        "(p := place_entity)\np(Prototype.StoneFurnace, exact=False)",
        "p = place_entity\nq = p\nq(Prototype.StoneFurnace, exact=False)",
        "p = place_entity\np = p\np(Prototype.StoneFurnace, exact=0)",
    ],
)
def test_semantic_profile_rejects_guarded_call_bypasses(code):
    with pytest.raises(ProgramPolicyViolation):
        validate_program(code)


@pytest.mark.parametrize(
    "code",
    [
        "place_entity(Prototype.StoneFurnace, position=p, exact=True)",
        "place_entity(Prototype.StoneFurnace, position=p)",
        "move_to(p, stop_distance=1)",
        "move_to(p, None, None, 2)",
        "print('iron__plate and copper__cable')",
        "print('a_b_c')",
        "plan_placement(Prototype.StoneFurnace, position=p)",
        "p = plan_placement\np(Prototype.StoneFurnace, position=p)",
    ],
)
def test_semantic_profile_allows_legitimate_calls(code):
    validate_program(code)


def test_planner_assisted_profile_keeps_guarded_calls_allowed():
    validate_program(
        "connect_entities(a, b, Prototype.TransportBelt)\n"
        "move_to(p, Prototype.TransportBelt)\n"
        "place_entity(Prototype.StoneFurnace, position=p, exact=False)",
        action_profile="planner-assisted-v1",
    )
