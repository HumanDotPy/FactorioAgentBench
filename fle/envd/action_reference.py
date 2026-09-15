"""Compact model-facing reference for the canonical semantic motor profile."""

from __future__ import annotations

import hashlib

ACTION_PROFILE_REFERENCE_ID = "semantic-motor-v1/reference-v6"

ACTION_PROFILE_REFERENCE = """\
Operate and expand a persistent factory, emphasizing autonomous production,
throughput, and research while satisfying the current contract. The harness
submits one short Python program through `factorio_execute_program`; calls,
loops, and conditionals inside it execute in source order and count as one
intervention. Do not import FLE or use reflection. Do not emit MCP calls from
a program or use host/file/network access or private attributes.

This is a turn-based semantic-motor environment. Factorio is paused while you
reason and runs during actions. Walking, mining, native crafting, machines,
belts, research, pollution, power, and deliveries all advance on real game
ticks. Game speed only changes wall-clock execution speed. Interaction actions
auto-approach their exact requested target. The controller routes the character
around obstacles; it never chooses a factory route or silently changes a
placement. Use explicit waypoints or path corners for strategic layout choices.

Execution receipts include public machine `status_changes`, anchored to an
observation revision. Inspect these for no_fuel, no_power, no_ingredients, and
blocked output. Events are sampled every 60 simulation ticks over registered
machines; sub-second changes can be missed. Coalesced events retain observed
statuses and peak severity. `truncated` or `history_expired` means the feed is
incomplete: query public state with kind='alerts' and since_revision, or request
a current observation. Initial/reconnected state is a keyframe, not a transition.

Core inspection and interaction:
- inspect_inventory(entity=None) -> Inventory
- get_entities(entities=set(), position=None, radius=1000) -> list[Entity]
- nearest(Prototype.X or Resource.X) -> Position
- get_entity(Prototype.X, position) -> Entity; resolve_entity(entity.id) -> Entity
- get_entity_ports(entity) -> {inputs, outputs, ports}
    Runtime fluid ports read from the entity's fluidboxes: each port has
    {x, y, fluidbox_index, flow_direction, connection_type, direction?}.
    inputs/outputs contain ports the game types as input/output; bidirectional
    ports appear only under `ports`. Port coordinates are fluidbox connection
    points and usually sit inside the machine body. Every port also reports
    connection state: `connected` is true when a live neighbour joins it,
    false when open (absent if the runtime cannot resolve it); connected
    ports carry `peers` [{entity_id, name, position}]; open ports carry
    `attach_tiles`, the tile(s) where a pipe makes the connection, best first
    (empty when the tile is blocked). Place the pipe at an attach tile, never
    at the port coordinate itself.
- get_power_network(position, window_seconds=5, include_members=False)
    Electric network state at a point (a pole click): network_id, production_w
    and by_producer, consumption_w and by_consumer, storage (accumulator
    charge statistic), generator/consumer counts, windowed statistics. Raw
    state only - no satisfaction or recommendations.
- get_fluid_network(position, include_members=False, max_entities=512)
    Fluid segment state at a point (a pipe inspection): segment_id, fluid,
    amount, capacity, fill_ratio, and pipe/tank/pump/machine counts. Raw state
    only - no flow rates or starvation counts.
- get_tile_map(center, radius=16) -> {rows, entities, legend}
    Compact ASCII tile map (north up) with a structured entity list. Use it
    before building and immediately after a placement stops short.
- trace_belt(position, max_tiles=64, upstream=False) -> {start, tiles, blocker}
    Follow a belt downstream (default) or upstream: per-tile direction, active
    flag and lane contents, then the first blocker. Downstream reasons:
    end_of_line, blocked_by_entity with the blocking entity, max_tiles_reached.
    Upstream reasons: start_of_line, fed_by_entity with the source entity,
    max_tiles_reached. Use it when items stop flowing or when finding a line's
    origin.
- move_to(target, stop_distance=0, mode='walk', waypoints=None,
    interrupt_on=None, timeout_ticks=36000) -> Position
    Open coordinates are exact; occupied coordinates resolve to the nearest
    walkable point in interaction range. stop_distance stops earlier. If a walk
    stalls with no progress, the controller attempts a bounded local escape
    onto a validated free orthogonal tile: on success it returns that reached
    Position, otherwise it raises naming both the blocked position and the
    requested destination.
- harvest_resource(position, quantity=1) -> int
- mine_entity(target) -> {name, position, items, removed}
    Clear one neutral obstacle near target (an Entity or Position): mine a
    tree, dead trunk or rock into your inventory (counted as manual
    production), or destroy a productless neutral stump or corpse. Only one
    entity within 1.5 tiles is affected and force-owned entities are refused.
    Use this instead of deconstruct_area to clear a single tree, rock or stump.
- insert_item(item, target, quantity=5, replace=False) -> Entity
    `replace=True` swaps a burner machine's fuel when its single fuel slot
    holds a different item: the old stack is moved back to your inventory and
    the receipt reports it under `replaced_fuel`. Without it the call fails
    and names the blocking item and both remedies.
- extract_item(item, source, quantity=5) -> int
- transfer_item(item, source, target, quantity=5) -> dict
- pickup_entity(entity), rotate_entity(entity, direction)
- deconstruct_area(top_left, bottom_right, prototype=None, include_neutral=True,
    max_entities=512) -> {status, area, removed, requested, items_returned,
    skipped, truncated, inventory_full, tick}
    Bulk-deconstruct an axis-aligned rectangle (a planner drag) and return the
    items to your inventory. Player entities keep their inventory and belt-lane
    contents; neutral trees/rocks yield their mineable products when
    include_neutral is set. Resources, ghosts, corpses, cliffs, dropped items
    and characters are never removed. Protected entities are skipped. Stops
    with status='inventory_full' before removing what would not fit. The
    rectangle is at most 64x64 tiles.
- set_entity_recipe(entity, RecipeName.X)

Construction is exact and non-atomic. Earlier successful placements remain
when a later placement fails. Failures expose `blocked_by` (nearest blocking
entity with name/position) when an entity is the cause:
- place_entity(Prototype.X, direction=Direction.UP, position=Position(x,y), exact=True)
    Receipts for fluid machines include the live port report under `fluid` and
    add `warnings` for every open machine port, each naming the attach tile to
    use; pipes stay quiet because an open pipe end is normal while building.
    When the ONLY blocker is your own character, the controller steps the
    character to a nearby free tile away from the requested footprint, retries
    the exact placement once, and adds `recovered='character_moved'` plus
    `character_position` to the receipt. Position, prototype, and direction are
    never changed; any other blocker still fails with its `blocked_by`
    diagnostics.
- place_path(prototype, points, routing='polyline', on_collision='stop',
    on_insufficient_materials='stop') -> structured partial/completed receipt
    Segments are axis-aligned; specify every corner. The controller infers
    segment orientations but does not route around obstacles.
- place_grid(prototype, origin, rows, columns, spacing=(x,y), direction=...)
- repeat_pattern(pattern, origin, count, stride), where each pattern entry has
    prototype, offset, and optional direction
- place_between(prototype, source, target, position) infers orientation only;
    you still choose the placement tile
- place_power_line(points, pole, spacing=7) -> structured partial/completed receipt
    Poles are exact and evenly spaced along the polyline; there is no routing.
    Interpolated points that already hold an electric pole are reported under
    `existing` and count as satisfied, so re-issuing the same points resumes a
    partial line. The first genuinely blocked point stops the line and returns
    `blocker` (position/name/blocked_by), the untouched suffix under
    `remaining`, and `stop_reason` (collision or materials_exhausted).
- place_offshore_pump(preferred_position, direction=...) provides the one
    explicit shoreline-snapping exception

Fluid and power connectivity follows the engine. Directly adjacent buildings
join through their fluidboxes when their connection points meet: an offshore
pump feeds a boiler, a boiler feeds steam engines, and a pipe placed against a
machine or another pipe snaps into the network - no wires-and-magic step.
Machine ports report `connected` plus `attach_tiles` (see get_entity_ports),
and placement/rotation receipts carry the same report under `fluid` with
explicit warnings for open machine ports, so connect by placing one pipe at a
reported attach tile and re-reading the port to confirm. Power poles connect
machines whose supply areas overlap; read coverage with get_power_network.

World facts the engine will not forgive: belts never insert into chests or
machines (an inserter is always required); a resource tile holds exactly one
resource, so patches cannot overlap and a patch's bounding box includes
non-ore gaps; deconstruct_area with include_neutral removes trees, rocks and
stumps and returns their products, which is the intended way to clear a
corridor, while mine_entity does the same for a single obstacle.

`connect_entities`, `nearest_buildable`, move_to laying/leading, and generic
non-exact placement belong to `planner-assisted-v1` and are rejected here.

Native asynchronous work and event-oriented waits:
- submit_actions(actions, interrupt_on=None) executes a finite command queue
    immediately and returns when completed, halted, or interrupted. Each action
    is {'id': optional_name, 'action': name, 'args': [...], 'kwargs': {...}}.
    Use {'$result': id} inside later args to consume an earlier result. The
    queue stops on the first execution failure without undoing prior actions.
- inspect_action_queue(); cancel_actions(from_index=None);
    insert_actions(before_index, actions); resume_actions(). Pending actions
    persist across model turns. Indices are zero-based. Capability availability
    is checked when submitted; inventory, geometry, and other state-dependent
    constraints are checked when each action executes. Common interrupts are
    action_failure, research_completed, under_attack, and new_order.
- get_craft_plan(Prototype.X, quantity=1, depth=2) reads the native crafting menu:
    craftable_now counts output items including native intermediate crafting;
    ingredients show have/need/missing. Subrecipes are bounded independent
    previews sharing the same inventory, not a combined allocation plan.
    factorio_get_craft_plan exposes the same read without a program intervention.
- queue_craft(Prototype.X, quantity=1) -> {handle, crafted, queued, queued_crafts, partial, tick}
    quantity and queued count output items; recipes round up to whole crafts.
    The craft completes within the same intervention so the items are
    immediately available; partial results are reported explicitly and
    failures include craft_plan. Only ingredients already in the inventory
    are consumed.
- get_craft_queue() -> {active, queue, tick}; cancel_craft(index=1, quantity=None)
- craft_item(...) is blocking compatibility sugar; prefer queue_craft so hand
    crafting overlaps movement and other live actions
- wait(ticks, until=None, poll_ticks=30) waits authoritative simulation ticks
    (60 ticks = 1 game second) and may
    stop early on exactly one condition: inventory, research, craft_queue,
    production_rate, machine_status, delivery, or event. Engine samples latch the
    first match; decision_tick and poll_latency_ticks separate the decision from
    transport delay. Production rates include manual production. Example:
    wait(18000, until={'inventory': {'entity': chest,
        'item': Prototype.IronPlate, 'at_least': 100}})
    wait(18000, until={'production_rate': {'item': Prototype.IronPlate,
        'at_least': 200, 'window_seconds': 60}})
- get_production_statistics(items=None, window_seconds=60, category='item', limit=32)
    reads native produced/consumed totals and per-minute rates, including manual
    production. Windows: 5/60/600/3600 seconds; category: item/fluid. Results are
    bounded with truncation metadata. query_state(kind='production') includes
    these public statistics as well as observation history.
- queue_research([Technology.X, Technology.Y]) appends enabled technologies to
    Factorio's native queue; set_research(Technology.X) replaces the queue
- get_research_progress(Technology.X)
- get_technology(Technology.X or 'technology-name') reads live researchability,
    prerequisites, successors, science cost, effects/unlocks and research_trigger.
    can_queue is false for trigger research; researchable means its prerequisites
    are met. get_available_technologies(limit=64, offset=0) lists these candidates.
- get_research_queue() reads the native ordered queue and current progress.
- get_recipes_using(Prototype.X, category='item', limit=64, offset=0) finds
    consuming recipes, including locked recipes; category may also be 'fluid'.
- get_logistic_network(position, limit=64, offset=0) reads network contents,
    roboport count and available/total robots inside logistic coverage.
- get_circuit_network(position, wire='red', connector_id=None, limit=64, offset=0)
    reads signals per connector and combinator parameters. Inputs/outputs stay
    separate. wire may be 'green'; reading never creates a connection.
- get_trains(limit=32, offset=0) reads this force's trains on the current surface:
    schedules, states, destinations, cargo and fuel. get_train_stop(position,
    limit=64, offset=0) reads a stop's limits, association count and scheduled IDs.
- get_pollution(position, radius_chunks=0) reads generated chunks (32 tiles each),
    with radius 0-8; ungenerated chunks omit pollution, matching camera visibility.
- get_force_bonuses() reads research modifiers for production, robots,
    inserters, braking, character capabilities and ammo.
    Paginated reads report total/offset/truncated; pages are fresh live reads.

Blueprint library (native construction plans):
- blueprint('save', name, x, y, radius=32) captures entities, tiles and settings.
- blueprint('place', name_or_string, x, y, direction=0, build_mode='normal',
    book_path=None) creates native ghosts; it never grants or consumes materials.
    Robots construct using network materials, or build matching ghosts manually.
    build_mode accepts normal, forced or superforced; direction is 0/4/8/12.
- blueprint('ghosts', x, y, radius=32, offset=0) inspects pending construction.
- blueprint('list') lists saved names and usage counts.
- blueprint('get', name) returns the full exchange string.
- blueprint('inspect', name) returns editable native JSON.
- blueprint('import'|'edit', name, content) saves an engine-validated exchange
    string or native JSON document, including books and planners.
- blueprint('apply', planner_name, x, y, radius=32, cancel=False) marks/cancels
    native upgrade/deconstruction orders. blueprint('delete', name) removes a design.
- factorio_reference_world is a direct MCP tool: create a separate creative
    Factorio process; execute native Lua; run exact ticks; capture a tested
    design into this library; destroy when done. Reference inventory, research,
    ticks and production never transfer into the benchmark factory.
Prefer library names over re-emitting exchange strings. Inspect created_ghosts
and ghost positions; placement alone is not a working factory.

Program library and pacing (harness tools, not in-program calls):
- factorio_save_program_template / factorio_run_program_template store and
  replay canonical programs with {{parameter}} substitution; templates are
  expanded and validated by this same policy before they run.
- factorio_set_realtime(enabled, speed) opts into a running world between
  interventions (1x-10x, never below 1x); the default is paused-while-thinking.

Customer output:
- set_delivery_chest(chest, product) binds an existing empty player-owned chest;
  high-rate lines may allow multiple chests and report the remaining allowance
  for the current product. Only inserter-fed delivery counts. Excess remains in
  the chest and it becomes ordinary when the order ends.

RecipeName is the recipe namespace; Prototype identifies items/entities. Query
get_prototype_recipe before assuming ingredients. Trigger technologies cannot
be started with set_research: inspect their research_trigger in the game-data
reference and satisfy it. Returned entities include stable integer `id` handles;
use resolve_entity(id) after the world changes instead of trusting stale fields.
Every operation still obeys reach, collision, inventory, native duration, and
partial effects. Inspect the returned receipt or re-query state before assuming
a plan worked.
"""

ACTION_PROFILE_REFERENCE_SHA256 = hashlib.sha256(
    ACTION_PROFILE_REFERENCE.encode("utf-8")
).hexdigest()
