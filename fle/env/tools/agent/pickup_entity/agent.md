# pickup_entity

The `pickup_entity` tool allows you to remove entities from the world and return them to your inventory. It can handle single entities, entity groups (like belt lines), and items on the ground.

## Basic Usage

```python
pickup_entity(
    entity: Optional[Union[Entity, Prototype, EntityGroup]] = None,
    position: Optional[Position] = None
) -> bool | dict
```

Returns a receipt `{status, requested, picked_up, leftovers}` when the game
reports one. `status` is `"completed"` or `"partial"`. A partial pickup destroys
only the part that actually entered your inventory and lists the remainder that
stayed on the ground under `leftovers`; group pickups return True only when
every member is fully collected. `True` is also returned for legacy successes.
If the engine cannot keep or recreate a ground remainder, the shortfall is
reported under `lost` instead of being silently discarded.

### Parameters

- `entity`: Entity/Prototype to pickup. For ground stacks this filters by stack
  name and, when the object carries a `quality`, by that quality as well.
- `position`: Optional position to pickup from (required for Prototypes)

Calling `pickup_entity(position=Position(x, y))` with no entity is the
empty-hand ground sweep: every stack lying on the ground at that position is
picked up, regardless of item. Placed entities are never picked up this way.

### Ground stacks

`requested` echoes what the call asked for: `{name, quality}` for an item
filter (quality is present only when it was requested) or `"all"` for an
empty-hand sweep. `picked_up` maps each item name to the amount that actually
entered your inventory. A filtered pickup that matches no ground stack raises a
clear error and leaves every stack untouched; unrelated stacks are never picked
up implicitly.

### Examples

```python
# Pickup using prototype and position
pickup_entity(Prototype.Boiler, Position(x=0, y=0))

# Pickup using entity reference
boiler = place_entity(Prototype.Boiler, position=pos)
pickup_entity(boiler)

# Pick up only the iron ore lying on the ground (other stacks stay put)
pickup_entity(Prototype.IronOre, Position(x=5, y=5))

# Empty-hand sweep: pick up every ground stack at a position
pickup_entity(position=Position(x=5, y=5))

# Pickup entity group (like belt lines)
# Belt groups are picked up automatically
belt_group = connect_entities(start_pos, end_pos, Prototype.TransportBelt)
pickup_entity(belt_group)  # Picks up all belts in group

# same for underground belts
belt_group = connect_entities(start_pos, end_pos, Prototype.UndergroundBelt)
pickup_entity(belt_group)  # Picks up all belts in group
```

## Best Practices

1. **Group Cleanup**

```python
def cleanup_belt_line(belt_group):
    try:
        # First try group pickup
        pickup_entity(belt_group)
    except Exception:
        # Fallback to individual pickup
        for belt in belt_group.belts:
            try:
                pickup_entity(belt)
            except Exception:
                print(f"Failed to pickup belt at {belt.position}")
```
