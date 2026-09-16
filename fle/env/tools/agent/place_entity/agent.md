# place_entity

`place_entity(Prototype.X, direction=Direction.UP, position=Position(x,y), exact=True)`
places one inventory entity at the requested position and direction, after
approaching within build reach. It returns the placed Entity.

The canonical action profile requires exact placement.
An engine manual-build rejection returns structured diagnostics: requested
position, rotated footprint, overlapping entities with positions, colliding tiles,
and truncation metadata. These describe local collision evidence; engine-specific
rules may also reject placement. The failure does not create ghosts, relocate the
build, or consume its inventory item. Inspect terrain and choose the next build.

The engine snaps even-sized machines to tile corners and odd-sized entities to
tile centers, so the returned position is authoritative: a 2x2 machine requested
at (-12.5,-69.5) is placed at (-12,-69). Read the returned Entity's `position`
and build relative to that, not to the requested coordinates.

For inserter prototypes the requested `direction` names the DROP side: the
inserter picks from the opposite side. Receipts echo `pickup_position` and
`drop_position` plus `pickup_side`/`drop_side`, and set `direction_warning`
when the built drop side does not match the requested direction. To bridge two
placed entities, use `insert_between(source, target)` instead of guessing a
direction.

```python
furnace = place_entity(Prototype.StoneFurnace, position=Position(x=10,y=4))
pump = place_offshore_pump(Position(x=20.5,y=10.5), direction=Direction.UP)
```

Offshore pumps use `place_offshore_pump`; `place_entity(Prototype.OffshorePump)`
is rejected by the canonical profile. `can_place_entity` has no `exact`
parameter: it only reports whether the engine allows the build there.

When the placed entity exposes `drop_position` (mining drills, inserters), the
receipt adds `drop_tile` (the tile holding the drop), `catch_tile` (the tile
center to place a receiver at: `floor(drop_position) + 0.5`), `drop_receivers`
(entities already accepting items there), and `drop_warning` when nothing at the
catch tile can receive the item or item stacks are already piling on the ground.
Place a chest, furnace, belt, or inserter at exactly that reported `catch_tile`.
`catch_output(source)` does this in one step, including the source's footprint
and snapped parity.

A failed exact placement over a machine's output tile returns
`placement_rejected` with `drop_tile_hint`: the nearby machine's name,
position, and `catch_tile`, and a message that the rejected footprint covers
another machine's output tile. The engine's manual build check is the only
placement oracle and reports only "occupied"; this hint explains it.

Placing a mining drill over more than one resource type adds
`resource_warning` with each resource's count under the mining area and the
`dominant` resource, so a mixed copper/iron boundary is visible before the drill
fills the wrong line.

Generic `exact=False` searches belong only to the explicit planner-assisted
ablation profile. They are unavailable in the canonical benchmark.

When the only blocker is your own character, exact placement steps the
character to a nearby free tile away from the requested footprint, retries
once, and discloses `recovered='character_moved'` plus `character_position` in
the receipt. Position, prototype, and direction are never altered; any other
blocker fails with `blocked_by` diagnostics.
