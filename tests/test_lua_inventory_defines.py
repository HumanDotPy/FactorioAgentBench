"""Offline guard: defines.inventory keys used in Lua must exist on the pin.

The key set below was dumped live from Factorio 2.0.77 (the pinned version) and
covers every key the engine exposes. A missing key resolves to nil; the old
extract_item scan put those nils inside an array literal, so `ipairs` silently
stopped at the first hole and every later inventory became unreachable.

When FACTORIO_VERSION changes, re-dump `defines.inventory` from the live server
and update the list before updating this assertion.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_factorio

REPO_ROOT = Path(__file__).parents[1]
INVENTORY_DEFINE = re.compile(r"defines\.inventory\.([a-z_0-9]+)")

LIVE_VERIFIED_INVENTORY_KEYS = {
    "agricultural_tower_input",
    "agricultural_tower_output",
    "artillery_turret_ammo",
    "artillery_wagon_ammo",
    "assembling_machine_dump",
    "assembling_machine_input",
    "assembling_machine_modules",
    "assembling_machine_output",
    "assembling_machine_trash",
    "asteroid_collector_arm",
    "asteroid_collector_output",
    "beacon_modules",
    "burnt_result",
    "car_ammo",
    "car_trash",
    "car_trunk",
    "cargo_landing_pad_main",
    "cargo_landing_pad_trash",
    "cargo_unit",
    "cargo_wagon",
    "character_ammo",
    "character_armor",
    "character_corpse",
    "character_guns",
    "character_main",
    "character_trash",
    "character_vehicle",
    "chest",
    "crafter_input",
    "crafter_modules",
    "crafter_output",
    "crafter_trash",
    "editor_ammo",
    "editor_armor",
    "editor_guns",
    "editor_main",
    "fuel",
    "furnace_modules",
    "furnace_result",
    "furnace_source",
    "furnace_trash",
    "god_main",
    "hub_main",
    "hub_trash",
    "item_main",
    "lab_input",
    "lab_modules",
    "lab_trash",
    "linked_container_main",
    "logistic_container_trash",
    "mining_drill_modules",
    "proxy_main",
    "roboport_material",
    "roboport_robot",
    "robot_cargo",
    "robot_repair",
    "rocket_silo_input",
    "rocket_silo_modules",
    "rocket_silo_output",
    "rocket_silo_rocket",
    "rocket_silo_trash",
    "spider_ammo",
    "spider_trash",
    "spider_trunk",
    "turret_ammo",
}


def pinned_version() -> str:
    source = (REPO_ROOT / "fle" / "cluster" / "run_envs.py").read_text(encoding="utf-8")
    match = re.search(r'FACTORIO_VERSION\s*=\s*"([^"]+)"', source)
    assert match, "FACTORIO_VERSION not found in fle/cluster/run_envs.py"
    return match.group(1)


def test_inventory_key_list_matches_pinned_version():
    assert pinned_version() == "2.0.77", (
        "Re-dump defines.inventory from the live server for the new pinned "
        "Factorio version and update LIVE_VERIFIED_INVENTORY_KEYS."
    )


def test_env_lua_uses_only_live_inventory_defines(lua_env_sources):
    offenders = []
    for path, lines in lua_env_sources:
        for line_number, line in enumerate(lines, start=1):
            for key in INVENTORY_DEFINE.findall(line):
                if key not in LIVE_VERIFIED_INVENTORY_KEYS:
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{line_number}: "
                        f"defines.inventory.{key}"
                    )
    assert not offenders, (
        "defines.inventory keys absent from the pinned Factorio version:\n"
        + "\n".join(offenders)
    )
