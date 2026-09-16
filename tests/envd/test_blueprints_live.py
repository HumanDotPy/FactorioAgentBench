"""Opt-in native blueprint acceptance; provisions disposable worlds itself."""

import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("FLE_RUN_BLUEPRINT_WORKSHOP") != "1",
    reason="Set FLE_RUN_BLUEPRINT_WORKSHOP=1 to provision isolated Docker worlds",
)


def test_blueprint_workshop_native_roundtrip():
    from scripts.validate_blueprint_workshop import validate

    report = validate()
    assert report["native_ghosts_without_material_or_research_mutation"]
    assert report["checkpoint_restores_reference_library_and_ghosts"]
    assert report["manual_build_preserves_recipe"]
