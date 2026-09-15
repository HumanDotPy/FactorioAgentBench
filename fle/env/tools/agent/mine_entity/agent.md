# mine_entity

Mine or remove exactly one neutral obstacle - a tree, dead trunk, rock, stump
or corpse - near a position. This is the precision counterpart to
`deconstruct_area`: it never touches more than one entity and never uses a
64x64 rectangle.

## Usage

```python
result = mine_entity(nearest(Resource.Wood))
print(result["name"], result["items"], result["removed"])

mine_entity(Position(x=12, y=-3))
```

`target` may be an `Entity` (resolved fresh when it has an `id`) or a
`Position`. The tool walks into interaction range first when the game is not
in fast mode.

## Result

```python
{"name": "tree-01", "position": {"x": 0.5, "y": 0.0},
 "items": {"wood": 2}, "removed": True}
```

- Trees, dead trunks and rocks with mineable products are mined and their
  products are inserted into your inventory. The mining time is charged to
  elapsed ticks in fast mode and the products are recorded in manual
  production statistics.
- Neutral stumps and other productless, destroyable obstacles are removed with
  `destroy()`; `items` is then empty.

## Practical guidance

- The search radius is 1.5 tiles around the requested position. Nothing
  neutral in range is an error; stand or click closer and retry.
- Only neutral entities are eligible. Player-owned corpses and other
  force-owned entities of the same type are refused so their contents are not
  lost; use `insert_item`/`extract_item` or `deconstruct_area` for those.
- Reach is checked against your resource reach distance. `move_to` closer when
  the error names the distance.
- Mining is refused up front when the inventory cannot hold the products.
- Prefer this over `harvest_resource` when you need one specific entity gone:
  `harvest_resource` queues the nearest matching resource and stops at the
  requested quantity.
