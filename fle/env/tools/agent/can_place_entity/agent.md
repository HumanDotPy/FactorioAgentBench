# can_place_entity

`can_place_entity` answers "could this entity be placed here right now?" with a
bool. It never builds anything.

```python
can_place = can_place_entity(
    entity: Prototype,  # entity to place from inventory
    direction: Direction = Direction.UP,
    position: Position = Position(x=0, y=0),
) -> bool
```

## Answers

- `False` (normal negative answers, no exception):
  - the position is beyond the character's reach,
  - the inventory holds none of the entity,
  - the engine's manual build check rejects the tile (collision, terrain,
    footprint, missing resources, and so on).
- `True`: all of the checks above pass.
- `ValueError`: genuinely invalid input, such as an unknown entity name
  (typo), a non-`Prototype` entity, or a non-`Direction` direction. These
  remain loud instead of being flattened into `False`.

## Examples

```python
target_pos = Position(x=10, y=10)
move_to(target_pos)
if can_place_entity(Prototype.SteamEngine, position=target_pos, direction=Direction.DOWN):
    place_entity(Prototype.SteamEngine, position=target_pos, direction=Direction.DOWN)
else:
    print("Cannot place steam engine at target position")
```

## Read-only detail

When `False` is not enough, use `plan_placement` for the reason, rotated
footprint, `blocked_by`, overlapping entities and colliding tiles, or
`plan_path` for a whole corridor. Neither mutates the world, and neither needs
`exact=False` (which the action profile rejects for construction).
