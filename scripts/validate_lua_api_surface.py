"""Validate that engine API members referenced by fle/env Lua exist on a live server.

Read-only: probes `defines.<table>[.<key>]`, `game.<member>`, `surface.<member>`
and `prototypes.<member>` usages with pcall and reports anything the running
Factorio version does not expose. Run it against an isolated instance or a test
pair, for example:

    uv run python scripts/validate_lua_api_surface.py --port 27000

Exit code is non-zero when any referenced member is missing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factorio_rcon import RCONClient

ENV_ROOT = ROOT / "fle" / "env"
DEFINES_PATH = re.compile(r"defines\.([a-z_]+)(?:\.([a-z_0-9]+))?")
MEMBER = re.compile(r"\b(game|surface|prototypes)\.([a-z_0-9]+)")
COMMENT = re.compile(r"--.*$")


def repo_usages():
    defines: set[tuple[str, str | None]] = set()
    members = {"game": set(), "surface": set(), "prototypes": set()}
    for path in sorted(ENV_ROOT.rglob("*.lua")):
        for line in path.read_text(encoding="utf-8").splitlines():
            code = COMMENT.sub("", line)
            for table, key in DEFINES_PATH.findall(code):
                defines.add((table, key or None))
            for root, member in MEMBER.findall(code):
                members[root].add(member)
    return defines, members


def probe_script(defines, members) -> str:
    lines = [
        "local out={defines={},members={}}",
        "local function pget(f)",
        "  local ok,v=pcall(f)",
        "  if not ok then return 'ERROR' end",
        "  if v==nil then return 'MISSING' end",
        "  return 'ok'",
        "end",
        "local s=game.surfaces[1]",
    ]
    for table, key in sorted(defines, key=lambda item: (item[0], item[1] or "")):
        path = table if key is None else f"{table}.{key}"
        if key is None:
            expr = f"defines.{table}"
        else:
            expr = f"defines.{table}['{key}']"
        lines.append(f"out.defines['{path}']=pget(function() return {expr} end)")
    for root, member in sorted(
        (root, member) for root, names in members.items() for member in names
    ):
        if root == "surface":
            expr = f"s['{member}']"
        else:
            expr = f"{root}['{member}']"
        lines.append(
            f"out.members['{root}.{member}']=pget(function() return {expr} end)"
        )
    lines.append("rcon.print(helpers.table_to_json(out))")
    return " ".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=27000)
    parser.add_argument("--password", default="factorio")
    args = parser.parse_args()

    defines, members = repo_usages()
    client = RCONClient(args.host, args.port, args.password, timeout=15)
    raw = client.send_command("/silent-command " + probe_script(defines, members))
    results = json.loads(raw)

    missing = []
    for path, status in results["defines"].items():
        if status != "ok":
            missing.append(f"defines.{path}: {status}")
    for path, status in results["members"].items():
        if status != "ok":
            missing.append(f"{path}: {status}")

    print(
        f"probed {len(results['defines'])} defines paths and "
        f"{len(results['members'])} object members"
    )
    if missing:
        print("\nMISSING ON LIVE SERVER:")
        for item in missing:
            print(" -", item)
        return 1
    print("all referenced members exist on the live server")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
