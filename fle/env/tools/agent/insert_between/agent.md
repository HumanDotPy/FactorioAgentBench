# insert_between

`insert_between(source, target, inserter=Prototype.BurnerInserter)` places one
inserter between two placed entities so that it takes from `source` and drops
into `target`.

```python
insert_between(drill, chest)
insert_between(furnace, belt, inserter=Prototype.FastInserter)
```

`source` and `target` may be Entity objects or Positions. The tool searches the
tiles around the source footprint for a free tile whose pickup tile belongs to
`source` and whose drop tile belongs to `target`, then places the inserter there
with the drop side facing `target`. It walks into build reach first.

The receipt reports `tile`, `direction` (agent-facing: the DROP side), and the
exact `pickup_tile` / `drop_tile`, plus the full `place_entity` receipt under
`entity` (including pickup/drop sides and any direction warning).

When no legal tile exists the receipt is `status='impossible'` with a precise
reason:

- `source` and `target` are edge-adjacent: an inserter picks from one tile and
  drops on the opposite tile, so it needs a free tile in between. Move one
  entity one tile further away, or connect them with a belt.
- `source` and `target` are diagonally adjacent: an inserter cannot bridge a
  corner. Use two inserters with a belt between them.
- candidate tiles existed but were blocked, out of reach, or the inserter is
  missing from the inventory; `rejections` lists the first attempts with their
  reasons (walk closer or free the tile).

Inserters cannot move items over a diagonal; the pickup and drop sides of one
inserter are always opposite. Long-handed inserters reach two tiles per side,
so the entities must be separated by four tiles on one axis.

Related tools:

- `place_between(prototype, source, target, position)` places any prototype at
  an explicit tile and infers orientation from source to target. Use it when you
  already know the exact tile, or for non-inserter bridges.
- `place_entity_next_to(prototype, reference_position, direction, spacing)`
  places relative to one entity only; it does not check the far side.
- Agent-facing inserter directions name the DROP side everywhere (`place_entity`,
  `rotate_entity`, receipts); the engine value is the pickup side.
