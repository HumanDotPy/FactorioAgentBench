"""Static guard against LuaTile members removed from the Factorio 2.0 runtime.

Live-verified on the pinned 2.0.77 server: reading `walkable`, `mineable`,
`hidden`, `autoplace`, or `layer` from a LuaTile raises
"LuaTile doesn't contain key <member>." Plain-table mocks silently return nil
instead, which is how `tile.walkable` reached the walking-queue nth-tick
handler and crashed it. LuaTilePrototype still exposes `collision_mask` and
`items_to_place_this` (e.g. when iterating `prototypes.tile`), so those are
deliberately not flagged here.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_factorio

ENV_ROOT = Path(__file__).parents[1] / "fle" / "env"
REMOVED_LUATILE_MEMBERS = ("walkable", "mineable", "hidden", "autoplace", "layer")
TILE_MEMBER_READ = re.compile(
    r"\w*tile\w*\.(" + "|".join(REMOVED_LUATILE_MEMBERS) + r")\b"
)


def test_no_removed_luatile_members_in_env_lua(lua_env_sources):
    offenders = []
    for path, lines in lua_env_sources:
        for line_number, line in enumerate(lines, start=1):
            if TILE_MEMBER_READ.search(line):
                offenders.append(
                    f"{path.relative_to(ENV_ROOT)}:{line_number}: {line.strip()}"
                )
    assert not offenders, (
        "LuaTile members removed in Factorio 2.0 must not be read "
        "(use collides_with(layer) instead):\n" + "\n".join(offenders)
    )
