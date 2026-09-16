# Blueprint workshop and native construction

The agent can create a lease-owned creative Factorio process, experiment there,
and transfer designs to its real factory through the blueprint library. Reference
worlds run the same pinned vanilla Factorio version and bundled runtime as a newly
provisioned local worker. No browser editor is required for model use.

## Agent workflow

`factorio_reference_world` is a direct MCP tool (HTTP:
`POST /v1/leases/{lease_id}/reference-world`). Its `action` selects an operation;
`arguments` contains that operation's fields. HTTP callers provide a unique
`request_id` and reuse it for retries of the same operation.

1. `create` starts a dedicated Docker process on an automatically allocated,
   loopback-only RCON port. Repeated creates return the existing world. It starts
   paused, with all research unlocked and a flat 128×128 laboratory area.
2. `execute` accepts native Lua in `arguments.code`. The local names `surface`
   and `force` refer to the reference surface and player force. All native Lua
   APIs available in the headless engine can be used for free construction,
   destruction, terrain, resources, machine settings, infinity containers/pipes,
   energy interfaces, circuits and diagnostics. Return JSON-compatible data,
   rather than LuaObjects. Executions finish paused, including after Lua errors.
3. `run` advances exactly `ticks` simulation ticks at optional `speed` (default
   10). Calls allow up to one simulated hour; long experiments can use successive
   calls. The reference process has its own game clock. A realtime benchmark
   factory continues its ordinary simulation independently.
4. `capture`, with `name` and `area=[[left,top],[right,bottom]]`, saves an engine
   blueprint into the owning lease's library. `place`, with `source`,
   `position=[x,y]`, optional `book_path` and `options`, tests a library design or
   exchange string in the reference world. Options are `direction`, `build_mode`
   and `instant` (default true). Free revival reports remaining ghosts and keeps
   unresolved material requests visible.
5. In the real runtime, `blueprint('place', name, x, y)` places native ghosts.
   Build over matching ghosts manually with `place_entity`, or supply a native
   construction robot network. Ghost placement never grants materials, unlocks
   research, revives entities, or adds artificial construction ticks.
6. `destroy` releases the reference process. Lease release also destroys it.

For example, reference `execute` can run:

```lua
local machine = surface.create_entity{
    name="assembling-machine-2", position={0.5,0.5}, force=force
}
machine.set_recipe("iron-gear-wheel")
machine.insert{name="iron-plate",count=100}
local supply = surface.create_entity{
    name="electric-energy-interface",position={8,0},force=force
}
supply.electric_buffer_size=100000000
supply.power_production=10000000
surface.create_entity{name="substation",position={5,5},force=force}
return {recipe=machine.get_recipe().name}
```

After `run` with `ticks=600`, inspect production with:

```lua
return force.get_item_production_statistics(surface).get_input_count("iron-gear-wheel")
```

Capture just the machine with `area=[[-1,-1],[2,2]]`; include the rest of a
factory only when those entities belong in the deployed design. Laboratory
infinity sources are test fixtures. Blueprint transfer creates designs, not
reference inventory or production credit.

## Editing, books and planners

The [agent reference](../../fle/env/tools/agent/blueprint/agent.md) defines the
library API. `inspect` returns the complete native exchange document; `import`
or `edit` saves a replacement document after validation by Factorio. This
supports creating designs from scratch, copying them under another name,
changing entities/tiles/recipes/modules/circuit settings, book entries, labels,
icons, grids and native planner filters. Unknown JSON fields survive the codec;
the engine determines whether it accepts a document. An import that the engine
reports as repaired is surfaced as an error, never silently saved as the original.

Native placement supports rotation, grid snapping, normal/forced/superforced
build modes, tiles, wires and item-request proxies. Book selection uses native
zero-based entry indices, including nested books. `apply` executes native
upgrade/deconstruction planner orders or cancels them. It does not materialize
upgrades or destroy real entities immediately.

The headless Lua API has no blueprint flip method and no API for creating a
real player. There is no separate flip convenience argument; designs are editable
as native documents, including native entity `mirror` fields. A graphical editor
and complete automated geometric reflection are not supplied by this change.
The linked [Teoxoy editor](https://github.com/Teoxoy/factorio-blueprint-editor)
was inspected but not copied: it is marked unmaintained and its flip operation
also rejects some entity types. It remains a possible user interface over the
exchange-document boundary; its TypeScript simulation/rendering is not the
source of truth for whether a factory works.

## Isolation, allocation and persistence

Local envd provisions reference containers lazily, up to the real-worker count
by default. `--reference-capacity N` changes the cap; zero disables the feature.
Remote RCON workers and AgentENV do not advertise creative reference support.
Docker must be available on the local envd host. The health capability is
`creative_reference_worlds`. Nothing is allocated before `create`.

Processes use generated Compose projects, separate storage, a 1-CPU/1-GiB cap,
and loopback RCON; they never borrow a live or audit worker. The agent never
receives a runtime RCON connection. A native script timeout terminates its
reference process. Recreate it with destroy/create after a runaway script.
The program byte limit and simulation request bounds protect service capacity;
they are not gameplay inventory, research, reach or placement restrictions.

Requests are lease-bound and serialized with lease operations. Reference calls
have a distinct idempotency cache and never enter the real intervention ledger,
production history, verification or scoring. The real worker only reads/writes
its blueprint store during reference transfers. Transport output is bounded by
the existing MCP response contract; query a focused area or summary for large
worlds. The native API can generate more chunks and change the laboratory area.

Environment checkpoints include an immutable native save of the reference
process, and ephemeral blueprint libraries retain their contents and usage
counters. Unchanged reference worlds reuse their last native save. A resumed
lease restores the experiment lazily on its next `create`; it does not attach
the old process or continue from mutations performed after the checkpoint.
Durable lineage libraries continue to use their shared SQLite scope. Native
pending-construction overlays preserve ghosts across the real worker's entity
snapshot restore. Reference save files remain under the envd state directory
for checkpoint recovery after the owning container is released.

## Validation

Run `uv run python scripts/validate_blueprint_workshop.py`. It creates its own
runtime and reference containers and never connects to the normal ports 27000
or 27001. Results are written to `.runtime/blueprint-workshop-validation/validation.json`.
The opt-in pytest entry is `tests/envd/test_blueprints_live.py`, enabled with
`FLE_RUN_BLUEPRINT_WORKSHOP=1`.

Focused unit coverage is in `tests/envd/test_blueprint_workshop.py` and
`tests/envd/test_blueprints.py`. It covers lossless documents, nested books,
invalid/oversized data, scoped persistence, lease isolation, idempotency,
HTTP routing, and cleanup failure behavior.
