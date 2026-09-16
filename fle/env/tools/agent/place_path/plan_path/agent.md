# plan_path

Read-only corridor check for a `place_path`-style polyline. Nothing is built,
mined or picked up; the engine's manual build check decides each tile and the
blocker's footprint is reported per blocked tile.

Use it before spending belts on a line, or to decide where `place_path`
will stop. `place_path` remains the authoritative builder: plan first, then
build with `place_path`.

## Usage

```python
report = plan_path(Position(x=0, y=0), Position(x=30, y=0), width=2)
print(report["status"], report["blocked"], "of", report["requested"])
for tile in report["blockers"]:
    print(tile["position"], tile["reason"], tile["blocked_by"])
```

## Parameters

- `start`, `end`: endpoints of an axis-aligned straight corridor; a corner must
  be supplied explicitly, exactly like `place_path`. Direct diagonal segments
  are rejected.
- `width`: number of parallel lanes, 1-8. Lanes extend to the right of travel
  (`+y` for `Direction.RIGHT`, `-y` for `LEFT`, `-x` for `DOWN`, `+x` for `UP`).
- `prototype`: entity probed on each tile (default `Prototype.TransportBelt`).

## Return fields

- `status`: `clear` (every tile placeable) or `blocked`.
- `requested`, `blocked`, `placeable`: tile counts and the aggregate verdict.
- `tiles`: every probed tile with `position`, `direction`,
  `engine_direction`, `placeable` and, when blocked, `reason`, `footprint`,
  `blocked_by`, `overlapping_entities`, `colliding_tiles`.
- `blockers`: the subset of `tiles` that failed, for direct iteration.
- `start`, `end`, `width`: the echoed request.

`blocked_by` is the nearest overlapping entity, computed from the rotated
collision footprint rather than a point probe, so wide or diagonal collision
shapes (for example an 8x8 crash-site wreck) are reported correctly. A blocked
tile is evidence, not a verdict: `place_path` performs the final engine check.
