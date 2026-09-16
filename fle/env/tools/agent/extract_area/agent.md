# extract_area

Collect items from the machine inventories inside a rectangle in one call.
Use it after smelting or crafting production backs up: instead of walking
furnace to furnace with `extract_item`, name the block once and take the
output. Only item stacks are moved; no entity is destroyed. By default only
product and storage slots are scanned (furnace/assembler/silo outputs, chests,
vehicle trunks), so fuel and in-progress inputs are never touched unless you
pass `include_inputs=True`.

## Usage

```python
result = extract_area(
    Position(x1, y1),
    Position(x2, y2),
    items=[Prototype.IronPlate],
)
print(result["status"], result["extracted"], result["out_of_reach"])

# Everything in every scanned product/storage slot:
result = extract_area(Position(x1, y1), Position(x2, y2))

# Also drain fuel, machine inputs, modules, ammo and robot slots:
result = extract_area(Position(x1, y1), Position(x2, y2), include_inputs=True)

# Reachable-only, never walk:
result = extract_area(Position(x1, y1), Position(x2, y2), path=False)
```

## Parameters

- `top_left`, `bottom_right`: opposite corners of an axis-aligned rectangle of
  at most 64x64 tiles.
- `items`: prototypes or name strings limiting what is taken; `None` takes
  every stack found in the scanned slots.
- `path=True` (default): when machines are out of reach, walk to the nearest
  one and retry, up to 64 walks or until a walk makes no progress.
- `path=False`: one call, reachable machines only; out-of-reach machines are
  reported but not visited.
- `interaction_radius`: reach in tiles (default 10.0).
- `max_entities`: maximum entities scanned per call (default 512).
- `max_items`: maximum items extracted per call (default 4096).
- `include_inputs` (default `False`): also scan fuel, machine input, module,
  ammo and robot slots. Leave off to protect running machines.

## Return fields

- `status`: `completed`, `partial` (entities out of reach or a cap hit),
  `inventory_full`, or `no_targets` (nothing matched).
- `area`: floored `left`/`top`/`right`/`bottom` of the processed rectangle.
- `scanned`: entities inspected; `extracted`: `{name: count}` returned to the
  character, summed across any retries.
- `out_of_reach`: `[{name, position}]` machines with matching items that were
  not reached; walk there and call again, or fix your inventory space first.
- `inventory_full`: the `{name, position}` stack that did not fit, or `None`.
  Nothing is removed when the character cannot accept a stack.
- `truncated`: a cap stopped work before the rectangle was exhausted.
- `tick`: simulation tick of the final call.

## Reach and fast-mode semantics

Reach checks use `interaction_radius` around the character. In fast mode
(`storage.fast`) the runtime ignores reach entirely, so a `path=True` call
ends after a single pass and every scanned machine is processed. Machines are
scanned in deterministic order (unit number, then position), so partial runs
are reproducible.
