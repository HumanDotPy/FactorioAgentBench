# get_entities

The get_entities tool allows you to find and retrieve entities in the Factorio world based on different criteria. This tool is essential for locating specific entities, gathering information about your surroundings, and interacting with the game world.

## Basic Usage

```python
# Get entities by prototype within a radius
entities = get_entities(prototype=Prototype.IronChest, radius=10)

# Get entities by position
entities = get_entities(position=Position(x=10, y=15), radius=5)

# Get all entities of a certain type around the player
entities = get_entities(prototype=Prototype.AssemblingMachine1)
```

The function returns a list of Entity objects that match the specified criteria.

## Ground Items And Footprints

Item-on-ground stacks are returned separately from machines on the same list:

- `entities.ground_items` holds one `GroundItem` per stack (`name`, `count`,
  `position`); `entities.ground_item_count` is the stack count,
  `entities.ground_item_totals` maps item name to total count, and
  `entities.ground_items_truncated` reports the 32-stack listing cap.
- Every returned machine also carries `tile_size` (`width`, `height` in
  tiles), `center_parity` (`0` when the center sits on tile-center
  coordinates, `1` on a tile corner) and `snapped_center` (the center of the
  tile containing the entity center).
- A catch tile for a machine output is `floor(drop_position) + 0.5`; compare
  it with nearby machines' `snapped_center` and `tile_size` to see whether the
  dropped items have a receiver or are landing on the ground.

```python
nearby = get_entities(position=Position(x=10, y=15), radius=8)
print(nearby.ground_item_totals, nearby.ground_item_count)
for item in nearby.ground_items:
    print(item.name, item.count, item.position)
for machine in nearby:
    print(machine.name, machine.tile_size, machine.center_parity)
```

## Parameters

- `entities`: Set of Prototypes to find (optional; empty means all)
- `position`: Position to search around (default=player's current position)
- `radius`: Search radius in tiles (default=32; pass a larger explicit value for wider scans). The returned list records the effective radius as `query_radius`.

**Search Behavior**

- If no prototype is specified, returns all player-force entities within radius
- Returns empty list if no matching entities are found
- Results only cover the player's force; characters and prototypes this
  client cannot map are dropped, and the returned list carries the drop
  counts as `other_forces`, `characters_skipped`, `unmatched_prototypes`,
  `server_skipped` and `skipped` attributes (also shown in its repr).

## Examples

### Finding Specific Entities

```python
# Find all transport belts within 15 tiles of the player
belts = get_entities(prototype=Prototype.TransportBelt, radius=15)
print(f"Found {len(belts)} transport belts nearby")

# Find the closest furnace to a specific position
position = Position(x=5, y=10)
furnaces = get_entities(prototype=Prototype.StoneFurnace, position=position, radius=30)
if furnaces:
    closest_furnace = min(furnaces, key=lambda entity: entity.position.distance_to(position))
    print(f"Closest furnace is at {closest_furnace.position}")
```

## Common Pitfalls

1. **Performance Considerations**
   - Using too large of a radius can impact performance
   - Filter results as specifically as possible

2. **Entity Access**
   - Some actions may require the player to be near the entity

## Best Practices

1. **Efficient Searching**

```python
# Instead of searching the entire map:
def find_resource_patch(resource_type: Prototype):
    # Start with a reasonable radius
    for radius in [20, 40, 60, 80]:
        resources = get_entities(prototype=resource_type, radius=radius)
        if resources:
            return resources

    # If still not found, search in different directions
    for direction in [(50, 0), (0, 50), (-50, 0), (0, -50)]:
        pos = Position(x=player.position.x + direction[0],
                       y=player.position.y + direction[1])
        resources = get_entities(prototype=resource_type, position=pos, radius=40)
        if resources:
            return resources

    return []
```

2. **Combining with Other Tools**

```python
# Find and interact with all chests containing iron plates
chests = get_entities(prototype=Prototype.IronChest)
iron_containing_chests = []

for chest in chests:
    inventory = inspect_inventory(chest)
    if Prototype.IronPlate in inventory and inventory[Prototype.IronPlate] > 0:
        iron_containing_chests.append(chest)
        print(f"Chest at {chest.position} contains {inventory[Prototype.IronPlate]} iron plates")

# Extract iron from the chest with the most plates
if iron_containing_chests:
    target_chest = max(iron_containing_chests,
                       key=lambda c: inspect_inventory(c)[Prototype.IronPlate])
    extracted = extract_item(Prototype.IronPlate, target_chest, quantity=10)
    print(f"Extracted {extracted} iron plates from chest at {target_chest.position}")
```
