# deconstruct_area

Remove everything inside a rectangle in one call, like dragging Factorio's
deconstruction planner over it. Player-force buildings are removed and their
items (including chest contents and belt lanes) return to the inventory;
neutral trees and rocks are included by default and yield wood/stone.

## Usage

```python
result = deconstruct_area(Position(x=0, y=0), Position(x=8, y=8))
print(result["status"], result["removed"])
print(result["items_returned"])  # {"transport-belt": 6, "iron-plate": 12, ...}

# Only one prototype, and leave nature alone:
deconstruct_area(
    Position(x=0, y=0),
    Position(x=8, y=8),
    prototype=Prototype.TransportBelt,
    include_neutral=False,
)
```

## Practical guidance

- `status` is `"completed"` or `"inventory_full"`. On `"inventory_full"` the
  entity named in `inventory_full` and every later target are untouched, so
  free inventory space and call again with the same rectangle.
- `requested` counts matching targets before the `max_entities` (1-2048) cap;
  `truncated` is true when the cap was exceeded and only the first
  `max_entities` targets (sorted by row, then column) were processed.
- `skipped` lists entities left alone and why: `resource`, `ghost`,
  `not_mineable`, `self` (characters) or `protected` (delivery chests); it is
  capped at 32 entries.
- Resources, ghosts, corpses, cliffs, item stacks on the ground and other
  characters are never removed or yielded.
- The rectangle may be at most 64x64 tiles; the character walks to its centre
  first. Prefer one call over many `pickup_entity` calls to clear a build site.
