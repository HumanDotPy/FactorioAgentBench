# get_fluid_network

Inspect the fluid segment connected to any pipe, tank, pump, or fluid machine.
This is the "look inside the pipe" primitive: report the fluid, how much is
there, the segment capacity, the fill ratio, and which entities share it.
Read-only; it never changes the factory.

## Usage

```python
network = get_fluid_network(Position(x=29, y=-82))
print(network["fluid"], network["amount"], "/", network["capacity"])

detailed = get_fluid_network(Position(x=29, y=-82), include_members=True)
for member in detailed["members"]:
    print(member["name"], member["type"], member["position"])
```

`entity` is the seed resolved at the queried position and `segment_id`
identifies the connected fluid segment (`None` for isolated buffers such as
fluid wagons). `fluid` is the single fluid in the segment, `amount` and
`capacity` are in fluid units, and `fill_ratio` is `amount / capacity` (0 when
capacity is 0). `pipe_count`, `tank_count`, `pump_count`, and `machine_count`
count the segment members by type; `entities_truncated` marks a walk stopped
at `max_entities`.

## Practical guidance

- Query any pipe, tank, pump, or machine fluidbox in the network; every member
  reports the same segment state.
- When a machine reports no fluid, query it directly: a machine box with no
  segment id reports only its own buffer amount and capacity.
- Use `include_members=True` to see which machines and pipes share the fluid
  (capped at 64 entries) before connecting or disconnecting anything.
- `max_entities` defaults to 512 and is capped at 4096; raise it only for very
  large networks.
- This reports physical state only: no production, consumption, or starvation
  information.
