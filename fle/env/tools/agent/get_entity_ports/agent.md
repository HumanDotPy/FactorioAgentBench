# get_entity_ports

Read the live fluid connection ports of an entity and whether each port is
connected. This is the "where do pipes attach?" primitive: use it before
connecting water, steam or oil so the pipe lands on the right face instead of
a guess.

## Usage

```python
ports = get_entity_ports(boiler)
for port in ports["ports"]:
    print(port["flow_direction"], port["x"], port["y"],
          port.get("connected"), port.get("attach_tiles"))
print("inputs:", ports["inputs"], "outputs:", ports["outputs"])
```

Each port entry has `x`, `y`, `fluidbox_index`, `flow_direction` (`input`,
`output` or `input-output`), `connection_type` (`normal`, `linked`, ...) and,
when the runtime exposes it, `direction` (the face the port opens onto).
`inputs` keeps the `input` ports, `outputs` the `output` ports, and `ports`
keeps all of them.

Connection truth:

- `connected` is `true` when a live neighbour joins this port, `false` when it
  is open, and absent when the runtime cannot resolve it.
- Connected ports carry `peers`: `[{entity_id, name, position}, ...]`.
- Open ports carry `attach_tiles`: the tile(s) where a connector (normally a
  pipe) makes the connection, best candidate first. `attach_tiles` is empty
  when the tile is blocked; clear the obstacle or pick another route.

## Practical guidance

- Port coordinates are the fluidbox connection points and usually sit *inside*
  the machine body. Do not try to place a pipe at the port coordinate itself:
  place it at the port's `attach_tiles` entry.
- A boiler reports both fluidboxes: water ports at its first box (typically
  `input-output` on two opposite faces) and one steam `output` port on its
  second box. Water ports face the short ends; rotating the boiler moves them.
- A steam engine reports two `input-output` ports; an offshore pump reports a
  single `output` that faces away from the water.
- An entity with no fluidbox (assembler, furnace, pole) returns empty lists -
  that is not an error.
- Ports are read from the live entity, so call this after rotating or
  connecting: the result reflects the entity's current state, not a stale
  snapshot.
- Placement and rotation receipts include the same report under `fluid`, and
  machines get explicit `warnings` for open ports with their attach tile.
