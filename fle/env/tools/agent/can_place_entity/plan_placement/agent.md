# plan_placement

Read-only placement probe. Nothing is built, consumed or mutated; the engine's
manual build check decides `placeable` and the rotated collision footprint is
reported when the answer is no. Use it instead of `place_entity(exact=False)`,
which is rejected by the `semantic-motor-v1` action profile.

## Usage

```python
report = plan_placement(Prototype.StoneFurnace, Position(x=-5, y=0))
if report["placeable"] and report["within_reach"] and report["inventory_count"]:
    place_entity(Prototype.StoneFurnace, position=Position(x=-5, y=0), exact=True)
else:
    print(report["reason"], report["blocked_by"], report["footprint"])
```

## Parameters

- `entity`: prototype to probe.
- `position`: tile to test.
- `direction`: agent-facing direction (inserters name the drop side, matching
  `place_entity`).

## Return fields

- `placeable`: engine verdict from the manual build check.
- `within_reach`: whether the character's build distance covers `position`.
- `inventory_count`: how many of the entity are in the character inventory.
- `prototype`, `position`, `direction`, `engine_direction`, `building`.
- When blocked: `reason` (`occupied`, `terrain_collision`,
  `no_minable_resources`, or `engine_rules_or_route_obstruction`), `footprint`,
  `blocked_by`, `overlapping_entities`, `colliding_tiles`.

`blocked_by` comes from the rotated collision footprint, so diagonal and
wide collision shapes (for example an 8x8 crash-site wreck) are reported even
though a point probe at the tile centre would miss them. `placeable` is
evidence, not a reservation: the world can change before `place_entity` runs.
