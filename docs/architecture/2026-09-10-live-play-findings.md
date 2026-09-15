# Live-play findings

Running log for the current freeplay run (realtime 1x, rocket-launch goal).
Addressed items were removed on 2026-09-14 when this log was reset. Keep entries
short, factual, and tied to agent-visible evidence; put missing base-game
features in `agent-tool-wishlist.md`.

## Open items carried in

- Direct `FactorioInstance` attach resets the live world. Do not attach a
  second instance to a lease that is in use; the envd worker owns it.
- `get_entities` reports machines and resources only. Neutral trees, rocks,
  stumps and the character are visible through `get_tile_map` (`t`, `R`, `s`,
  `@`) and can be cleared with `mine_entity`.
- Trigger technologies cannot be queued. `set_research`/`queue_research`
  reject them with an opaque error; read `get_technology(...)` and check its
  `research_trigger` first, then satisfy the trigger by crafting/building.
- Fluid and power reads are raw state only on Factorio 2.0.77: no satisfaction
  percentage, no fluid flow-rate summaries, no `LuaElectricNetwork`.
- `extract_item` requires a `Prototype`, but an entity's serialized
  inventories (`furnace_result`, `furnace_source`, `fuel`) are keyed by
  item-name strings, so iterating the result and passing the key fails with
  `'str' object has no attribute 'value'`. Read the measured item name and
  pass the matching `Prototype.X`.

## Run log

- 2026-09-14: run initialized. Realtime execution mode at 1x for the whole
  episode; programs are admitted in the background and results are read with
  `factorio_get_program_status`, with `factorio_await_events` for waiting.
- 2026-09-14: `factorio_await_events` only blocks when the runtime cursor is
  exactly current; with an older cursor it returns immediately and replays
  retained events. An agent that reads "await returned" as "program still
  running" can lose a finished program. Always follow an admission with
  `factorio_get_program_status`, and re-read status after any await that does
  not carry a terminal event. Two related observability facts: a failed
  program keeps its placed prefix and cancels queued dependents, so the world
  can look half-built while nothing runs; and at 1x, long hand-mining
  programs leave the character stationary on a patch, which reads as idle
  even though ticks and production continue.
