"""Export authoritative prototypes for privileged benchmark setup over RCON.

This utility uses Factorio's runtime scripting API and must never be exposed as
an agent tool. Agents use the public recipe/research actions instead.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from factorio_rcon import RCONClient


def _json_command(client: RCONClient, source: str) -> Any:
    response = client.send_command("/sc " + source)
    try:
        return json.loads(response)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Factorio returned non-JSON {response!r} for Lua: {source}"
        ) from exc


def _empty_table_as_list(value: Any) -> Any:
    return [] if isinstance(value, dict) and not value else value


def export_game_data(host: str, port: int, password: str) -> dict[str, Any]:
    client = RCONClient(host, port, password)
    try:
        version = _json_command(
            client,
            "rcon.print(helpers.table_to_json({"
            "factorio_version=script.active_mods['base']}))",
        )["factorio_version"]
        combined = _json_command(
            client,
            "local rn={} for n,_ in pairs(prototypes.recipe) do "
            "table.insert(rn,n) end table.sort(rn) "
            "local recipes={} for _,n in ipairs(rn) do "
            "local r=prototypes.recipe[n] local i={} local p={} "
            "for _,v in pairs(r.ingredients) do table.insert(i,{"
            "name=v.name,amount=v.amount,type=v.type}) end "
            "for _,v in pairs(r.products) do local a=v.amount "
            "or ((v.amount_min or 0)+(v.amount_max or 0))/2 "
            "* (v.probability or 1) table.insert(p,{name=v.name,"
            "amount=a,type=v.type}) end "
            "table.insert(recipes,{name=r.name,"
            "category=r.category,energy=r.energy,enabled=r.enabled,"
            "ingredients=i,products=p}) end "
            "local tn={} for n,_ in pairs(prototypes.technology) do "
            "table.insert(tn,n) end table.sort(tn) "
            "local technologies={} for _,n in ipairs(tn) do "
            "local t=prototypes.technology[n] local p={} local u={} "
            "for x,_ in pairs(t.prerequisites) do table.insert(p,x) end "
            "for _,e in pairs(t.effects) do if e.type=='unlock-recipe' "
            "then table.insert(u,e.recipe) end end table.sort(p) "
            "table.sort(u) local count=t.research_unit_count "
            "if type(count)~='number' then count=1 end "
            "table.insert(technologies,{name=t.name,"
            "prerequisites=p,unlocked_recipes=u,unit_count=count,"
            "unit_energy=t.research_unit_energy,"
            "research_trigger=t.research_trigger}) end "
            "rcon.print(helpers.table_to_json({recipes=recipes,"
            "technologies=technologies}))",
        )

        recipes = list(_empty_table_as_list(combined.get("recipes")) or [])
        for recipe in recipes:
            recipe["ingredients"] = _empty_table_as_list(recipe.get("ingredients"))
            recipe["products"] = _empty_table_as_list(recipe.get("products"))

        technologies = list(_empty_table_as_list(combined.get("technologies")) or [])
        for technology in technologies:
            technology["prerequisites"] = _empty_table_as_list(
                technology.get("prerequisites")
            )
            technology["unlocked_recipes"] = _empty_table_as_list(
                technology.get("unlocked_recipes")
            )
        # Prototype metadata is kept separate from recipes so lookup tools can
        # answer machine/prototype questions without asking the agent to infer
        # them from a category string.  Only stable, serializable fields are
        # exported; field access is guarded because not every entity prototype
        # exposes every machine property.
        prototypes = _json_command(
            client,
            "local o={} for n,e in pairs(prototypes.entity) do "
            "local categories={} local ok,cats=pcall(function() return e.crafting_categories end) "
            "if ok and cats then for c,_ in pairs(cats) do table.insert(categories,c) end end "
            "table.sort(categories) local energy=nil local eok,ev=pcall(function() return e.energy_usage end) "
            "if eok then energy=ev end table.insert(o,{name=e.name,type=e.type,crafting_categories=categories,energy_usage=energy}) "
            "end table.sort(o,function(a,b) return a.name<b.name end) "
            "rcon.print(helpers.table_to_json(o))",
        )
        prototypes = _empty_table_as_list(prototypes)
        return {
            "factorio_version": version,
            "recipes": recipes,
            "technologies": technologies,
            "prototypes": prototypes,
        }
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=27000)
    parser.add_argument("--password", default="factorio")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = export_game_data(args.host, args.port, args.password)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(
        f"wrote {len(payload['recipes'])} recipes and "
        f"{len(payload['technologies'])} technologies to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
