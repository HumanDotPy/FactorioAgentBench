# rotate_entity

The `rotate_entity` tool allows you to change the orientation of placed entities in Factorio. Different entities have different rotation behaviors and requirements.

## Basic Usage

```python
rotate_entity(entity: Entity, direction: Direction = Direction.UP) -> Entity
```

Returns the rotated Entity object.

### Parameters

- `entity`: Entity to rotate
- `direction`: Target direction (UP/DOWN/LEFT/RIGHT)

### Examples

```python
# Rotating inserters - the direction names the DROP side
inserter = place_entity(Prototype.BurnerInserter, position=pos, direction = Direction.UP)
print(f"Original inserter: pickup={inserter.pickup_position}, drop={inserter.drop_position}")
inserter = rotate_entity(inserter, Direction.DOWN)
print(f"Rotated inserter: pickup={inserter.pickup_position}, drop={inserter.drop_position}")
```

Agent-facing inserter directions (here and in `place_entity`) name the DROP
side. The engine stores the pickup side; the boundary inverts exactly once and
receipts include `pickup_side`/`drop_side` plus `direction_warning` if the
built geometry does not match the requested drop side. To move items between
two adjacent entities, prefer `insert_between(source, target)` over placing a
guessed direction.

## Entity-Specific Behaviors

### 1. Assembling Machines, Oil refineries and Chemical plants

Assembling machines, oil refineries and chemical plants can only be rotated when their recipe uses a fluid; Factorio 2.0 disables rotation for machines whose recipe has no fluid ingredient. Set a fluid recipe before rotating, otherwise the call fails without changing the entity.

```python
# Must set a fluid recipe before rotating
assembler = place_entity(Prototype.AssemblingMachine1, position=pos)

# This will fail:
try:
    assembler = rotate_entity(assembler, Direction.RIGHT)
except Exception as e:
    print("Cannot rotate without a fluid recipe")

# Correct way:
assembler = set_entity_recipe(assembler, RecipeName.FillCrudeOilBarrel)
assembler = rotate_entity(assembler, Direction.RIGHT)
```

Rotation keeps the recipe, crafting progress, fluidbox contents, modules and items; nothing is destroyed and recreated.
