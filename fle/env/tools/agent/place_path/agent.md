# place_path

Place an exact axis-aligned polyline of one prototype. The route is never
re-routed around blockers: `place_path` stops at the first blocked tile and
returns the partial work as a value so the program can keep running, inspect
`blocker`, mine it, or resume from `resume_from`.

## Usage

```python
receipt = place_path(
    Prototype.TransportBelt,
    [Position(x=0, y=0), Position(x=20, y=0), Position(x=20, y=6)],
    on_obstacle="clear",
)
print(receipt["status"], receipt["placed"], "of", receipt["requested"])
for tile in receipt["directions"]:
    print(tile["position"], tile["direction"])
if receipt["status"] == "partial":
    print(receipt["resume_from"], receipt["next_step"])
    place_path(
        Prototype.TransportBelt,
        [receipt["resume_from"], Position(x=20, y=6)],
    )
```

A partial result is not an error. `on_collision="raise"` opts back into the
old exception behavior; the default `"stop"` returns the receipt.

## Parameters

- `prototype`: entity to build.
- `points`: start and corner points; every segment must be axis-aligned.
- `routing`: `"polyline"` only; no routing is performed.
- `on_collision`, `on_insufficient_materials`: `"stop"` (default) or
  `"raise"`.
- `on_obstacle`: `"stop"` (default) or `"clear"`. `"clear"` tries
  `mine_entity`, then `pickup_entity` for player-built blockers, then a
  bounded `deconstruct_area` sweep by prototype name around the blocker, then
  retries the blocked tile.

## Return fields

- `status`: `completed` or `partial`.
- `placed`, `requested`, `last_position`, `entity_ids`, `inventory_delta`,
  `ticks_elapsed`.
- `directions`: the derived item-flow direction for every requested tile.
- `resume_from`, `remaining`: the first unplaced tile and the unplaced suffix,
  ready to pass back to `place_path`.
- `blocker`: the blocked tile with `blocked_by` (nearest overlapping entity
  from the placement diagnostics) when the engine refused the build.
- `cleared`: obstacles removed by `on_obstacle="clear"`, each with the tool,
  prototype, position and result.
- `stop_reason`: `completed`, `materials_exhausted`, `collision`,
  `clear_failed`, `clear_no_progress`, or `clear_budget_exhausted`.
- `next_step`: present on partial receipts; names `resume_from` and suggests
  `trace_belt` for auditing the built line.
