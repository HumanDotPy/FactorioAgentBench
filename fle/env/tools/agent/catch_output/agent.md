# catch_output

`catch_output(source, prototype=Prototype.IronChest, path=True)` places one
receiver exactly on a machine's output tile and returns a receipt.

`source` is an Entity with a live `drop_position` (mining drills and
inserters) or its Position. The engine's `drop_position` is the machine's
authoritative output coordinate; the tile a receiver must stand on is
`floor(drop_position) + 0.5`. The receipt reports the source's tile footprint
and snapped parity (`corner` for even-sized machines placed on integer
corners, `center` for odd-sized machines on tile centers), then verifies and
places:

```python
drill = get_entities(Prototype.ElectricMiningDrill, position=Position(x=0,y=0))[0]
receipt = catch_output(drill)
# receipt["catch_tile"] -> the tile to build on
```

Receipt:

```python
{
    "status": "placed" | "already_receiver" | "blocked" | "placement_rejected" |
              "placement_failed",
    "source": {entity_id, name, position, drop_position, footprint, tile_size, parity},
    "drop_position": {x, y},
    "catch_tile": {x, y},
    "placed": {entity_id, name, position} | None,
    "item_on_ground_before": int,
    "item_on_ground": {item: count},
    "blockers": [...],
    "output_tiles": [...],
    "warnings": [...],
}
```

`status == "placed"` means the receiver is built. `already_receiver` means the
tile already holds an entity that accepts items (chest, furnace input, belt,
inserter). `blocked` names the occupying entity or the other machine whose
output tile the catch tile is, so a mis-built line is visible without guessing.
Item-on-ground counts what was already on the tile; it does not block
construction but should be picked up.

The live check and the exact manual build check are the same engine path as
`place_entity` (exact placement, no relocation, no ghost). `path=True` walks
to the catch tile before the check; `path=False` never pre-approaches.
Sources without a `drop_position` raise with the entity types that have one.
