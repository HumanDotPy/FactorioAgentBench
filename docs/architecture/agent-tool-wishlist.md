# Agent tool wishlist (live play)

Living list of capabilities we want added. Items should be things a human
player can do in base-game Factorio (confirm with a web search and cite the
wiki/API page), or a direct agentization of a native UI surface.

## Open

1. Automatic target render/map on placement failure. A small image or ASCII
   map attached to a placement error would remove the "remember to render"
   step. (Agentization of the player's eyes on the world; no new game fact.)
2. Map tags / pins. Players can drop named tags on the map; the agent has no
   persistent in-world marker for "water pump here", "iron outpost there".
   Candidate: `create_map_tag(name, position)` / `list_map_tags()` backed by
   chart tags. Confirm the base-game surface with a web search before using.
3. Deconstruction planner filters. `deconstruct_area` currently removes
   everything player-owned in a rectangle; the native planner supports
   whitelist/blacklist filters and trees/rocks toggles. Candidate:
   `include`/`exclude` prototype filters. (Live note: `deconstruct_area` does
   yield stone from mineable rocks; some remaining rock-like entities were not
   covered by the neutral-force query, so a filter/coverage follow-up is
   worthwhile.)
4. Reliable access to prior tool results (mostly built, needs plumbing and two
   fixes). `factorio_read_execution_result(execution_id, section, cursor,
   max_chars)` already pages `receipt|output|events|delivery`, but
   `FACTORIO_TOOL_ARTIFACT_DIR` must be set for artifacts to be persisted
   (now set by `.runtime/play/mcp_launcher.py`). Two refinements:
   - Truncated execute receipts must always carry `artifact.id` (and
     `truncated: true`) in the compact summary; today a summarized receipt can
     omit the artifact id, making the full result unreachable.
   - Add read modes to the artifact reader: `head=n` / `tail=n` lines,
     `line_start`/`line_end`, and an optional case-insensitive `search`
     term over `output` and `events`. This is strictly better than per-tool
     truncation flags: uniform across tools, small by default, complete on
     demand.
5. Per-tool truncation modes (`truncate=first|last`, `n`) as a fallback for
   tools that cannot page. Lower priority than item 4; the artifact reader
   makes it mostly unnecessary.
6. Connection truth for fluids and power (agreed 2026-09-13; see the
   power-plant session in `docs/architecture/2026-09-10-live-play-findings.md`).
   - `get_entity_ports` must report, per port: whether it is connected, to
     which segment/entity, and for an open port the exact tile where a
     pipe/pole must be placed to attach.
   - Fluid/power machine placement receipts must state unconnected ports
     explicitly (e.g. "water input unconnected; attach pipe at (-16.5, 33.5)")
     instead of leaving the agent to diff fluid segments.
   - Document the runtime's actual connection rules in the action reference.
     Base game: directly adjacent buildings join through their pipe
     interfaces without intermediate pipes (offshore pump -> boiler ->
     steam engines placed side by side; https://wiki.factorio.com/Boiler,
     https://wiki.factorio.com/Power_production). State whether this local
     runtime matches and, if not, what it requires instead.
   - Coordinate hygiene: entity positions, port coordinates, tile maps, and
     placement verbs must share one coordinate language; entity center vs
     anchor must be explicit. The 2026-09-13 session lost many interventions
     to half-tile and anchor ambiguity.

## Decisions (2026-09-13 connection review)

- No broad auto-router (`connect_to(source, target)` or restoring
  `connect_entities`); routing is planner behavior the semantic-motor profile
  deliberately omits.
- A single-tile `connect_at(target, position)` (place one connector at an
  exact tile, assert and report the resulting connection) may be added if
  port diagnostics plus truthful placement receipts do not make it
  redundant. No pathfinding, no routing.
- `place_entity_next_to` stays exact by default. An explicit `connect=True`
  opt-in may choose orientation and tile to satisfy connection, but must
  report the choices and the ports that joined, or fail with the reason.
- Blueprints are deferred to the section below; do not start there yet.

## Deferred: blueprint library

Prerequisite: a temporary reference world with editor/creative tools so
blueprints can be authored and validated without touching an active lease.
The base game supports this: map editor and cheat mode allow free crafting
(https://wiki.factorio.com/Console); blueprint rotation/flipping, ghost
placement, library storage, and string import/export are native
(https://wiki.factorio.com/Blueprint).

1. Reference world: launch an isolated editor/creative world with free
   crafting and instant construction, bound to no lease, for authoring and
   validating blueprints. Export to the lineage library by name; it must
   never affect the scored world, state hash, checkpoints, or scoring.
2. Decomposed inspection: `blueprint('get')` returns name, size, and the
   entity list with prototype, relative offset, direction, and any
   circuit/fluid metadata, not only the exchange string.
3. Dry-run placement: validate collisions, terrain, materials, and port
   connections without mutating the world or consuming items; return the
   would-be entity list and per-port connection outcomes.
4. Anchored placement: name an anchor tile on save and require it on place
   (for example, the pump tile) so a power plant can be aligned to a
   shoreline or an ore patch deterministically.
5. Rotation/flip on placement, reporting entities that cannot be flipped
   (rail signals, chain signals, train stops) and any port left unconnected
   after the transform.
6. Metadata: entity count, dimensions, required materials, power/fluid
   inputs and outputs, and expected connections.
7. Deterministic placement receipts: list every placed entity with final
   position and direction; same blueprint + anchor + rotation yields the
   same layout.
8. Library management: rename/delete/tags, content hash (exists), created
   date, times placed, and import/export as exchange strings for sharing
   between lineages and runs.
9. Connection-aware capture and placement: optionally include wires and
   circuit settings (native parameterisation exists in 2.0.7), and report
   unconnected ports using item 6 diagnostics.
10. Blueprint books: group multiple blueprints and place them in a defined
    order, still billing real materials in scored runs.

## Delivered

- `get_power_network`, `get_fluid_network` (2026-09-12).
- `get_entity_ports` fluid ports, `trace_belt(upstream=True)` (2026-09-12).
- `deconstruct_area` bulk deconstruction (2026-09-12).
- Machine warnings name a full result/output (furnace result, assembler output, drill output) with the blocking item(s) and an "extract to resume" hint; a drill feeding a result-jammed furnace now warns instead of reporting the sink as accepting (2026-09-14, pending restage).
- GPT-6 player-information batch: technology, recipes-using, logistic,
  circuit, trains, pollution, force bonuses (commit `b634604b`).
