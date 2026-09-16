# get_power_network

Read the electric network state at any point, the same raw numbers a player
sees when clicking an electric pole. This is the "is the grid actually
working" primitive: use it before connecting or expanding power, and after a
build to confirm machines are on the network you expect.

## Usage

```python
power = get_power_network(Position(x=29, y=-82), window_seconds=60)
print(power["network_id"], power["statistics_available"])
print("production W:", power["production_w"])
for consumer in power["by_consumer"]:
    print(consumer["prototype"], consumer["watts"], consumer["count"])
```

The tool resolves the pole or connected machine at `position`, then reads the
statistics of the electric network it belongs to. `by_producer` and
`by_consumer` break the totals down per prototype (`watts`, `count`), and
`storage` reports accumulator charge per prototype. Values are physical
readings, not a score: nothing here is a satisfaction rating and no
recommendation is returned.

## Practical guidance

- `window_seconds` selects the averaging window and must be one of 5, 60, 600
  or 3600.
- Set `include_members=True` to also list the poles on the network
  (`pole_count`, `members['poles']`); the scan is bounded, and `truncated`
  marks a capped result.
- Each breakdown list is capped at 64 entries, sorted by `watts`/`charge`
  descending. The `generator_count`/`consumer_count` totals still cover the
  whole network even when a list is capped.
- If nothing electric is found, the tool raises an error describing the
  position instead of returning a partial report.
