# belt_line_report

One-call audit of a whole belt line. It reuses `trace_belt` (upstream to find the
line start, then downstream to the end) and reports gaps, dead ends and
mis-directed corners, so a `place_path` line can be checked without walking it
tile by tile.

## Usage

```python
report = belt_line_report(Position(x=29, y=-80))
print(report["status"], report["total_tiles"])
for gap in report["gaps"]:
    print("gap after", gap["after"], "resumes at", gap["resumes_at"])
for tile in report["mis_directed"]:
    print("reversed", tile["position"], tile["direction"])
for dead_end in report["dead_ends"]:
    print("ends at", dead_end["position"], dead_end["reason"])
print(report["next_step"])
```

## Parameters

- `position`: any belt tile in the line.
- `max_tiles`: walk limit per direction, 1-256 (default 128).
- `gap_probe_tiles`: how far past a dead end to look for a detached
  continuation, 0-8 (default 4). Each probed tile costs one `trace_belt` call.

## Return fields

- `status`: `clean` (continuous, no reversed flow) or `issues`.
- `total_tiles`, `start`, `end`, `line_start`, `query`.
- `corners`: every tile where flow changes axis.
- `gaps`: `{after, resumes_at, missing}` when the line stops on open ground and
  another belt resumes within `gap_probe_tiles`.
- `dead_ends`: the terminal tile with `reason` (`end_of_line`,
  `blocked_by_entity`, `blocked_by_reversed_belt`, ...), the blocking `entity`
  when present, and `next_tile`.
- `mis_directed`: tiles whose flow reverses the line (or a reversed belt
  detected at the next tile).
- `blocker`, `source`: the raw downstream/upstream `trace_belt` blockers.
- `next_step`: a plain-language follow-up (`rotate_entities`, fill the gap, or
  inspect the dead end).

`place_path` partial receipts point here after clearing a blocker; prefer this
report over re-tracing the line manually.
