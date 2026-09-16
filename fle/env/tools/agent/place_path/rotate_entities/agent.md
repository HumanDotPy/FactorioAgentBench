# rotate_entities

Bulk rotation for an existing set of entities. One call replaces dozens of
`rotate_entity` calls when a whole line was built facing the wrong way.

## Usage

```python
receipt = rotate_entities(belts, Direction.LEFT)
print(receipt["rotated"], "of", receipt["requested"], "failed:", receipt["failed"])
for item in receipt["entities"]:
    if not item["rotated"]:
        print(item["position"], item["name"], item["error"])

# Positions are accepted when the prototype is unambiguous on the tile
rotate_entities([Position(x=0, y=0), Position(x=1, y=0)], Direction.RIGHT)
```

## Parameters

- `entities`: non-empty list of `Entity`, `Position`, `(x, y)` or
  `{x, y, name?}` items. An entity name may be supplied per item; without one
  the nearest rotatable entity on the tile is chosen.
- `direction`: agent-facing `Direction` (0/4/8/12). For inserters this is the
  DROP side, matching `place_entity` and `rotate_entity`.

## Return fields

- `requested`, `rotated`, `failed`, `direction`.
- `entities`: one entry per request with `position`, `name`, `entity_id`,
  `requested_direction`, `engine_direction_before`, `engine_direction`,
  `rotated`, and `error` when the engine refused.

Failures are reported per entity; a partially rotated list returns as a value
so the program can rotate the rest again or fix the blockers first.
