# trace_belt

Follow a transport-belt line from any belt tile and report lane contents plus
the first place the line starts or stops. Use it whenever a belt "should" be
carrying items but nothing arrives.

## Usage

```python
# Downstream: where do these items go, and where do they stop?
result = trace_belt(Position(x=29, y=-80), max_tiles=128)
for tile in result["tiles"]:
    print(tile["position"], tile["direction"], tile["lanes"])
print("blocker:", result["blocker"])

# Upstream: where does this line come from?
source = trace_belt(Position(x=29, y=-80), upstream=True)
print("source side:", source["blocker"])
```

`blocker.reason` downstream is one of:

- `end_of_line`: the next tile has no belt (missing segment or a wrong turn).
- `blocked_by_entity`: a non-belt entity (pole, rock, chest, machine) occupies
  the next tile; `blocker.entity` names it.
- `max_tiles_reached`: the line kept going past `max_tiles`.

With `upstream=True` the walk starts at the queried belt and moves against the
flow, so the first tile is the queried belt and later tiles are its feed chain.
`blocker.reason` then is one of:

- `start_of_line`: nothing feeds the current tile (including a tree, rock, or
  machine in the predecessor tile that cannot place items onto a belt).
- `fed_by_entity`: an inserter, mining drill, or loader sits in the predecessor
  tile(s) and is the item source; `blocker.entity` names it.
- `max_tiles_reached`: the line kept going past `max_tiles`.

## Practical guidance

- Empty `lanes` everywhere plus `end_of_line` means the feed itself is empty,
  not a jam: call `trace_belt(..., upstream=True)` from a mid-line belt to find
  where the line comes from.
- A tile whose direction does not continue the previous tile's flow is the
  usual head-on/rotated-belt bug; replace that belt.
- Upstream follows straight feed first, then side-loads (left of flow, then
  right), so a `start_of_line` means the previous belt is rotated wrong or
  missing entirely.
- Pair with `get_tile_map` to see the whole area around the blocker.
