# refuel

`refuel(entity)` tops up a burner entity's fuel slot from your inventory in
one call, choosing the best fuel you carry. Use it instead of remembering and
re-inserting fuel by hand.

## Basic Usage

```python
drill = place_entity(Prototype.BurnerMiningDrill, Direction.UP, ore_position)
receipt = refuel(drill)
furnace = place_entity(Prototype.StoneFurnace, Direction.UP, Position(x=0, y=0))
receipt = refuel(furnace)
receipt = refuel(furnace.position)
```

`entity` is an Entity or a Position. The call returns immediately with a
receipt and does not wait for the machine to work.

## Fuel selection

- The best fuel is the one with the highest `fuel_value` prototype value
  (coal 4 MJ beats wood 2 MJ); ties are broken by the largest available
  quantity.
- When the fuel slot already holds a fuel type, only that type is used, even
  when a better fuel is in your inventory. This keeps the slot from mixing
  types.
- The insert is clipped to the space left in the fuel slot; nothing is
  removed from your inventory that did not go in.

## Return value

```python
{status, entity, fuel, inserted, remaining_fuel, available}
```

- `status`: `"refueled"`, `"fuel_full"` (slot already at capacity),
  `"fuel_mismatch"` (slot holds a fuel you do not carry), `"no_fuel"` (no
  fuel item in your inventory) or `"blocked"` (the slot refused the insert).
- `entity`: the serialized burner after the call.
- `fuel`: the chosen fuel, or the blocking fuel on `"fuel_mismatch"`.
- `inserted`: fuel units moved from your inventory into the slot.
- `remaining_fuel`: fuel units the slot can still take after the call.
- `available`: units of `fuel` that were in your inventory before the call.

On `"fuel_mismatch"`, either get the matching fuel or call
`insert_item(new_fuel, entity, replace=True)` to swap the existing stack.

## Fuelable entities

Only burner machines and vehicles have a fuel slot: burner inserter, burner
mining drill, stone/steel furnace, boiler, burner generator, car, tank and
locomotive. Calling `refuel` on anything else (for example an iron chest or an
assembling machine) raises an error naming that list.

## Burner self-fueling

Burner entities burn the fuel in their own fuel slot; they do not run without
it. A burner inserter additionally refuels itself: while it works, if its own
reserve drops low, it takes a fuel item it picked up (from the chest, belt or
machine it is taking from) and puts it into its own fuel slot instead of the
destination. This was confirmed in a Factorio 2.0.77 reference world: a
burner inserter started with one wood feeding from a chest of coal ended the
run with coal in its own fuel slot and kept working. Burner mining drills,
furnaces and boilers do not self-fuel; use `refuel` or `insert_item` for them.

## Common Pitfalls

1. `"no_fuel"` means you carry no burnable item; mine or craft fuel first.
2. `"fuel_mismatch"` means the slot holds a fuel type you do not carry, for
   example a furnace last fed with wood while you only have coal.
3. Fuel is consumed while the machine runs; `refuel` when a burner reports
   `NO_FUEL` or before a long craft, rather than inserting one unit at a time.
4. `insert_item(Prototype.Coal, burner, quantity)` still works for a specific
   fuel and returns a partial receipt when the slot fills first.
