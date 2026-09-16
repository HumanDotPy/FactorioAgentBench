import sys
from pathlib import Path

import pytest

if sys.platform == "win32":
    pytest.skip(
        "Verifiers v1 uses Unix process primitives; test the package on Linux",
        allow_module_level=True,
    )

PACKAGE_ROOT = Path(__file__).parents[2] / "environments" / "factorio_microtasks"
sys.path.insert(0, str(PACKAGE_ROOT))

from factorio_microtasks import FactorioMicrotasksTaskset  # noqa: E402
from factorio_microtasks.taskset import FactorioMicrotasksConfig  # noqa: E402
from verifiers.v1.loaders import taskset_config_type  # noqa: E402
from fle.envd.benchmark import benchmark_catalog  # noqa: E402

pytestmark = [pytest.mark.no_factorio]


def test_published_package_defaults_to_ready_microtasks():
    tasks = list(FactorioMicrotasksTaskset(FactorioMicrotasksConfig()).load())

    assert len(tasks) == 21
    assert all(task.data.task_spec is not None for task in tasks)
    expected_task_ids = {
        item.task_spec.task_id
        for item in benchmark_catalog()
        if item.suite == "api_microtasks_v1" and item.status == "ready"
    }
    assert {task.data.task_id for task in tasks} == expected_task_ids


def test_published_package_can_include_calibration_tasks():
    config = FactorioMicrotasksConfig(
        benchmark_statuses=["ready", "calibration_required"]
    )

    assert len(list(FactorioMicrotasksTaskset(config).load())) == 24


def test_verifiers_narrows_the_public_taskset_config():
    assert taskset_config_type("factorio_microtasks") is FactorioMicrotasksConfig
