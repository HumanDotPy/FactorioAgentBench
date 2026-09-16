# insert_item

The `insert_item` tool allows you to insert items from your inventory into entities like furnaces, chests, assembling machines, and transport belts. This guide explains how to use it effectively.

## Basic Usage

```python
insert_item(item: Prototype, target: Union[Entity, EntityGroup], quantity: int = 5) -> Entity
```

The function returns the updated target entity.

The receipt records how much actually went in: `inserted`, `requested` and
`insert_status` (`"completed"` or `"partial"`). When the target exposes an item
inventory the receipt also carries `remaining_capacity`, the number of further
items of that type the target can take after the call (0 means it is now full).
A partial insert (for example a fuel slot, machine input or chest that fills
before the whole quantity fits, or a request larger than your stock) also adds
a diagnostic to the entity `warnings`; it is never reported as a full success.
Only a call where nothing at all can be accepted raises, with the remaining
capacity in the message. `replace=True` swaps a burner's fuel only when the new
stack can be inserted, otherwise the old fuel is restored.

Example: a burner mining drill whose fuel slot holds 40/50 coal answers
`insert_item(Prototype.Coal, drill, 20)` with `inserted=10, requested=20,
remaining_capacity=0, insert_status="partial"` instead of failing.

### Parameters

- `item`: Prototype of the item to insert
- `target`: Entity or EntityGroup to insert items into
- `quantity`: Number of items to insert (default: 5)

### Examples

```python
# Insert coal into a furnace
furnace = insert_item(Prototype.Coal, furnace, quantity=10)

# Insert iron ore into a furnace
furnace = insert_item(Prototype.IronOre, furnace, quantity=50)
```

## Important Rules

Direct insertion into a customer depot is recorded as manual audit traffic and
does not fulfill customer contracts. Route factory output into a depot with an
inserter; belts may supply the inserter.

1. **Always update the target variable with the return value:**

```python
# Wrong - state will be outdated
insert_item(Prototype.Coal, furnace, 10)

# Correct - updates furnace state
furnace = insert_item(Prototype.Coal, furnace, 10)
```

2. **Check inventory before inserting:**

```python
inventory = inspect_inventory()
if inventory[Prototype.Coal] >= 10:
    furnace = insert_item(Prototype.Coal, furnace, 10)
```

## Entity Type Rules

### 1. Furnaces

- Can accept fuels (coal, wood)
- Can accept smeltable items (ores)
- Cannot mix different ores in same furnace (extract ores and plates of different types before inputting new ones)

### 2. Burner Entities

- Can only accept fuel items
- Common with BurnerInserter, BurnerMiningDrill
- The fuel slot holds one fuel type at a time; feeding a different type fails
  and names the blocking stack unless you pass `replace=True`
- For topping up a burner with whatever fuel you carry, use `refuel(entity)`;
  it picks the best `fuel_value`, respects the existing fuel type and the
  remaining slot capacity
- Burner entities burn the fuel in their own fuel slot. A burner inserter also
  self-fuels: when its reserve runs low it puts a fuel item it picked up into
  its own fuel slot instead of the destination (confirmed in a Factorio 2.0.77
  reference world), so it stays fed from a chest or belt of coal. Burner
  mining drills, furnaces and boilers do not self-fuel and need `refuel`.

### 3. Assembling Machines

- Must have recipe set first
- Can only accept ingredients for current recipe
