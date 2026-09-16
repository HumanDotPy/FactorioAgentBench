# Patterns

## Direction and tool semantics

`Direction` is agent-facing. For inserters `direction` names the DROP side
(the engine stores the pickup side; receipts echo `pickup_side`/`drop_side`).
For belts, underground belts and drills it names item flow and output. `+y`
points south. Belt tiles are walkable, so a walk may start on or cross them;
only entities that block the player layer stop movement. In a program,
`player_position` reads the character's current `Position`.

Placement is exact and non-atomic. Probe with `plan_placement`/`plan_path`,
then build with `place_entity`/`place_path`; the returned position is
authoritative because the engine snaps footprints to tiles. Inspect fluids and
ports with `get_entity_ports` and power with `get_power_network`.

Items on the ground are first-class reads, not invisible clutter.
`get_entities(...).ground_items` lists one entry per dropped stack (`name`,
`count`, `position`) and sets `ground_items_truncated` when the stack listing
is capped; `get_tile_map` draws each stack as the `o` glyph and its structured
entity record carries `item` and `count`. Ground items never block
construction, but they explain catch failures: `catch_output` receipts report
`item_on_ground_before` (plus warnings) when the catch tile already holds
items, and `place_entity` receipts add `drop_warning` when nothing at a
machine's catch tile can receive its output. Check them before assuming a
receiver is working.

| Intent | Tool |
| --- | --- |
| Place one exact entity on a tile | `place_entity(exact=True)` |
| Link two existing entities point-to-point | `connect_entities` (planner-assisted profile only) |
| Build an exact axis-aligned polyline | `place_path` |
| Probe a tile or corridor before building | `plan_placement`, `plan_path` |
| Stamp a repeated pattern | `repeat_pattern` |
| Put one receiver on a machine's drop tile | `catch_output` |
| Bridge two machines with an inserter | `insert_between` |
| If a `place_path` receipt is partial | resume from `resume_from`, clear `blocker` |

## Core Systems Implementation

### 1. Resource Mining Systems

#### Self-Fueling Coal Mining System

```python
def build_self_fueling_coal_mining_system(coal_position):
    move_to(coal_position)
    drill = place_entity(
        Prototype.BurnerMiningDrill,
        position=coal_position,
        direction=Direction.DOWN,
    )
    print(f"Placed burner mining drill at {drill.position}")

    catcher = catch_output(drill)
    print(f"Placed {catcher['status']} receiver at {catcher['catch_tile']}")

    fuel_chest = place_entity(
        Prototype.WoodenChest,
        position=Position(x=drill.position.x - 2, y=drill.position.y),
    )
    feeder = insert_between(fuel_chest, drill)
    if feeder.get("status") != "placed":
        print(f"Could not place fuel inserter: {feeder}")
    insert_item(Prototype.Coal, fuel_chest, quantity=20)
    refuel(insert_item(Prototype.Coal, drill, quantity=5))
    return drill, catcher, fuel_chest, feeder
```

### 2. Power Systems

**Power Infrastructure with steam engine**

Power typically involves:
-> Water Source + OffshorePump
-> Boiler (burning coal)
-> SteamEngine

IMPORTANT: Boiler and steam engine cannot be on water, so probe before
building. Keep at least 4 tiles between the pump and the boiler for pipes.

```python
print("I will create a power generation setup with a steam engine")
move_to(water_position)
pump = place_offshore_pump(water_position)
print(f"Placed offshore pump at {pump.position}")

boiler_position = Position(x=pump.position.x + 6, y=pump.position.y)
probe = plan_placement(Prototype.Boiler, position=boiler_position, direction=Direction.LEFT)
assert probe["placeable"], f"Boiler tile is blocked: {probe}"
boiler = place_entity(Prototype.Boiler, position=boiler_position, direction=Direction.LEFT)
insert_item(Prototype.Coal, boiler, quantity=10)
```

```python
engine_position = Position(x=boiler.position.x + 7, y=boiler.position.y)
probe = plan_placement(Prototype.SteamEngine, position=engine_position, direction=Direction.LEFT)
assert probe["placeable"], f"Steam engine tile is blocked: {probe}"
steam_engine = place_entity(
    Prototype.SteamEngine,
    position=engine_position,
    direction=Direction.LEFT,
)
print(f"Placed steam engine at {steam_engine.position}")
```

```python
pump_attach = get_entity_ports(pump)["outputs"][0]["attach_tiles"][0]
boiler_attach = get_entity_ports(boiler)["inputs"][0]["attach_tiles"][0]
water_corner = Position(x=boiler_attach["x"], y=pump_attach["y"])
place_path(
    Prototype.Pipe,
    [
        Position(x=pump_attach["x"], y=pump_attach["y"]),
        water_corner,
        Position(x=boiler_attach["x"], y=boiler_attach["y"]),
    ],
)
engine_attach = get_entity_ports(steam_engine)["inputs"][0]["attach_tiles"][0]
boiler_steam = get_entity_ports(boiler)["outputs"][0]["attach_tiles"][0]
steam_corner = Position(x=boiler_steam["x"], y=engine_attach["y"])
place_path(
    Prototype.Pipe,
    [
        Position(x=boiler_steam["x"], y=boiler_steam["y"]),
        steam_corner,
        Position(x=engine_attach["x"], y=engine_attach["y"]),
    ],
)

wait(300)
steam_engine = get_entity(Prototype.SteamEngine, steam_engine.position)
assert steam_engine.energy > 0, "Steam engine is not generating power"
print(f"Steam engine at {steam_engine.position} is generating power")
```

### 3. Automated Assembly Systems

#### Basic Assembly Line

Keep factory sections at least 20 tiles apart and leave room for inserters.

```python
assembler_position = Position(x=0, y=0)
probe = plan_placement(
    Prototype.AssemblingMachine1,
    position=assembler_position,
    direction=Direction.DOWN,
)
assert probe["placeable"], f"Assembler tile is blocked: {probe}"
assembler = place_entity(
    Prototype.AssemblingMachine1,
    position=assembler_position,
    direction=Direction.DOWN,
)
set_entity_recipe(assembler, RecipeName.CopperCable)

input_chest = place_entity(
    Prototype.WoodenChest,
    position=Position(x=assembler.position.x - 3, y=assembler.position.y),
)
input_feeder = insert_between(input_chest, assembler)
insert_item(Prototype.CopperPlate, input_chest, quantity=20)

output_chest = place_entity(
    Prototype.WoodenChest,
    position=Position(x=assembler.position.x + 3, y=assembler.position.y),
)
output_feeder = insert_between(assembler, output_chest)
refuel(input_feeder)
refuel(output_feeder)

solar = place_entity(
    Prototype.SolarPanel,
    position=Position(x=assembler.position.x, y=assembler.position.y + 8),
)
place_power_line([solar.position, assembler.position], Prototype.SmallElectricPole)

wait(900)
assembler = get_entity(Prototype.AssemblingMachine1, assembler.position)
assert assembler.energy > 0, f"Assembler at {assembler.position} has no power"
output_chest = get_entity(Prototype.WoodenChest, output_chest.position)
cables = inspect_inventory(output_chest)
assert cables[Prototype.CopperCable] > 0, "No copper cables produced"
```

### 4. Research Systems

#### Basic Research Setup

```python
def build_research_facility(power_source, lab):
    place_power_line([power_source.position, lab.position], Prototype.SmallElectricPole)
    print(f"Powered lab at {lab.position}")

    science_chest = place_entity(
        Prototype.WoodenChest,
        position=Position(x=lab.position.x + 3, y=lab.position.y),
    )
    feeder = insert_between(science_chest, lab)
    insert_item(Prototype.AutomationSciencePack, science_chest, quantity=50)
    return lab, feeder, science_chest
```

# Key Implementation Patterns

## Error Handling and Recovery

### 1. Entity Status Monitoring

```python
def monitor_entity_status(entity, expected_status):
    entity = get_entity(entity.prototype, entity.position)
    if entity.status != expected_status:
        print(f"Entity at {entity.position} has unexpected status: {entity.status}")
        return False
    return True
```

### 2. Resuming a Partial Polyline

```python
receipt = place_path(Prototype.TransportBelt, [start, corner, end])
while receipt.get("status") == "partial":
    blocker = receipt["blocker"]
    print(f"Stopped at {receipt['last_position']} by {blocker}")
    mine_entity(blocker)
    receipt = place_path(Prototype.TransportBelt, [receipt["resume_from"], corner, end])
```

## Chemical plants

Set the recipe before connecting inputs and outputs. Read each port's
`attach_tiles` and place pipes there.

```python
chemical_plant = get_entity(Prototype.ChemicalPlant, position=Position(x=0, y=0))
chemical_plant = set_entity_recipe(chemical_plant, RecipeName.HeavyOilCracking)
print(f"Set the recipe of chemical plant at {chemical_plant.position}")

storage_tank = place_entity(
    Prototype.StorageTank,
    position=Position(x=10, y=0),
)
ports = get_entity_ports(storage_tank)
attach = ports["ports"][0]["attach_tiles"][0]
place_path(
    Prototype.Pipe,
    [Position(x=attach["x"], y=attach["y"]),
     Position(x=chemical_plant.position.x + 2, y=chemical_plant.position.y)],
)
output_storage_tank = place_entity(
    Prototype.StorageTank,
    position=Position(x=-10, y=0),
)
ports = get_entity_ports(chemical_plant)
attach = ports["outputs"][0]["attach_tiles"][0]
place_path(
    Prototype.Pipe,
    [Position(x=attach["x"], y=attach["y"]),
     Position(x=output_storage_tank.position.x + 2, y=output_storage_tank.position.y)],
)
```

## Oil Refinery

Set the recipe before connecting inputs and outputs.

```python
pumpjack = get_entity(Prototype.PumpJack, position=Position(x=-50, y=0))
oil_refinery = get_entity(Prototype.OilRefinery, position=Position(x=-25, y=10))
oil_refinery = set_entity_recipe(oil_refinery, RecipeName.BasicOilProcessing)
print(f"Set the recipe of oil refinery at {oil_refinery.position}")

ports = get_entity_ports(oil_refinery)
attach = ports["inputs"][0]["attach_tiles"][0]
corner = Position(x=pumpjack.position.x, y=attach["y"])
place_path(
    Prototype.Pipe,
    [
        Position(x=pumpjack.position.x, y=pumpjack.position.y),
        corner,
        Position(x=attach["x"], y=attach["y"]),
    ],
)
print(f"Connected the pumpjack to the oil refinery")
```

## Useful statistics

Crafting speeds for solids
Iron gear wheel - 120 per 60 seconds
Copper Cable - 240 per 60 seconds
Pipe - 120 per 60 seconds
Steel plate - 3.75 per 60 seconds
Engine unit - 6 per 60 seconds
Electronic circuit - 120 per 60 seconds
Electric Engine unit - 6 per 60 seconds
Flying robot frame - 3 per 60 seconds
Sulfur - 120 per 60 seconds. Can only be produced by a chemical plant
Plastic bar - 120 per 60 seconds. Can only be produced by a chemical plant
Advanced circuit - 10 per 60 seconds
Processing unit - 6 per 60 seconds
Low density structure - 4 per 60 seconds
Copper plate - 18.75 per 60 seconds
Iron plate - 18.75 per 60 seconds
Stone brick - 18.75 per 60 seconds
Automation science packs - 12 per 60 seconds
Battery - 20 per 60 seconds. Can only be produced by a chemical plant

Crafting speeds for liquids
Sulfuric acid - 3000 per 60 seconds, can only be gotten with a chemical plant
Lubricant - 600 per 60 seconds. Can only be produced by a chemical plant
Heavy oil - 300 per 60 seconds with advanced oil processing, 1080 per 60 seconds with Coal liquefaction
Light oil - 540 per 60 seconds with advanced oil processing, 240 per 60 seconds with Coal liquefaction, 900 per 60 seconds with Heavy oil cracking
Petroleum gas - 540 per 60 seconds with Basic oil processing, 660 per 60 seconds with advanced oil processing, 120 per 60 seconds with Coal liquefaction

Raw resource extraction speeds
Burner mining drill - Mines 15 resources per 60 seconds
Electric mining drill - Mines 30 resources per 60 seconds
Pumpjack - Extracts 600 crude oil per 60 seconds

Furnace smelting speed modifiers
Stone furnace - 1 (Example: smelts 18.75 copper plates per 60 seconds)
Electronic furnace - 2 (Example: smelts 37.5 copper plates per 60 seconds)
Steel furnace - 2 (Example: smelts 37.5 copper plates per 60 seconds)

Assembling machine crafting speed modifiers
Assembling machine 1 - 0.5 (Example: Crafts 60 iron gear wheels per 60 seconds)
Assembling machine 2 - 0.75 (Example: Crafts 90 iron gear wheels per 60 seconds)
Assembling machine 3 - 1.25 (Example: Crafts 150 iron gear wheels per 60 seconds)

Oil refinery & Chemical plant crafting speed modifiers
Oil refinery - 1 (Example: Creates 540 petroleum gas per 60 seconds with Basic oil processing)
Chemical plant - 1 (Example: Creates 600 Lubricant per 60 seconds)

## TIPS WHEN CREATING STRUCTURES

- When an entity has status "WAITING_FOR_SPACE_IN_DESTINATION", it means there is no space in the drop position. For instance, a mining drill will have status WAITING_FOR_SPACE_IN_DESTINATION when the items it mines are not being collected by a furnace, chest, or transport belts at its drop position. `catch_output(drill)` places a chest on the exact catch tile.
- Make sure to always put 20+ fuel into all entities that require fuel. Use `refuel(entity)` to top up from your inventory; it picks the best fuel you carry.
- Keep it simple! Only use transport belts if you need them. Use chests and furnaces to catch the ore directly from drills with `catch_output`.
- Missed output accumulates on the ground: watch `get_entities(...).ground_items`, the `o` glyphs in `get_tile_map`, and the `item_on_ground_before`/`drop_warning` fields of `catch_output`/`place_entity` receipts, then move or fix the receiver instead of waiting for a status flip.
- Inserters put items into entities or take items away from entities; agent-facing inserter `direction` is always the DROP side. Use `insert_between(source, target)` to feed a target instead of guessing a rotation. You need to add inserters when items need to be automatically put into entities like chests, assembling machines, furnaces, boilers etc.
- Have at least 10 spaces between different factory sections.
