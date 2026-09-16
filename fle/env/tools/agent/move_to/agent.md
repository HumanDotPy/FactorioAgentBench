# move_to

`move_to(position, stop_distance=0)` walks to the requested position and returns
the actual final Position. Open tiles are exact (within the engine's small
arrival tolerance). Occupied destinations are not silently replaced: when the
exact target is occupied (for example a boiler, chest, or machine body) the
walk resolves to the nearest walkable tile inside a bounded radius (8 tiles,
deterministic nearest-first order) and reports the Position actually reached
plus the distance to the requested target in the move receipt. The call fails
only when no reachable walkable tile is in range, naming the requested target
and the scanned radius.

```python
coal_pos = nearest(Resource.Coal)
move_to(coal_pos)  # Open resource ground is walkable.
move_to(furnace.position, stop_distance=3)  # Explicit approach radius.
move_to(boiler.position)  # Resolves to the nearest walkable tile instead.
move_to(belt.position)  # Belt tiles are walkable; no stepping off is needed.
```

Interaction actions auto-approach within their own reach, so separate movement
is normally unnecessary before harvesting, inserting, or building. Avoid walking
onto a planned building footprint before placing it.

Belts, underground belts, splitters, and loaders do not collide with the
character. A walk may start on or cross them, and the bounded unstick steps the
character off a tile only when a non-walkable entity or terrain genuinely
blocks it. Inside a program, read `player_position` (a Position) to check where
the character is, then use `get_entities(position=player_position, radius=1)`
or `get_tile_map(player_position, radius=1)` to see what it is standing on.

Failed path searches report the requested goal, radius, and bounded collision
context at the start and goal. Water tiles and overlapping entities are local
evidence; the path may also be obstructed farther away. A stalled walk first
attempts a bounded local escape to a validated free adjacent tile; when that
succeeds the call returns the reached Position. When no free step exists it
fails without returning unverified alternatives. Choose another destination
or an explicit `stop_distance` after inspecting the failure.
