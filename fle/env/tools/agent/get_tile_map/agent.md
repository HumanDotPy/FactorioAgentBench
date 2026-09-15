# get_tile_map

Render a compact tile/entity map around any point. This is the "step back and
look at the target" primitive: use it before placing a build and immediately
after a placement or belt path stops short.

## Usage

```python
tile_map = get_tile_map(Position(x=29, y=-82), radius=12)
for row in tile_map['rows']:
    print(row)
for entity in tile_map['entities']:
    print(entity['name'], entity['position'], entity.get('direction'))
```

Rows are top (north) to bottom, left (west) to right; each character is one
tile. Belts draw their flow direction (`^>v<`), `P` is an electric pole, `*`
an ore tile, `~` water, `#` blocked terrain, and machines use their initial
(`A` assembler, `F` furnace, `D` drill, `L` lab, `B` boiler, `G` engine,
`p` pump, `C` chest, `I`/`i` inserter, `|` pipe). Neutral obstacles that block
placement have their own glyphs: `t` tree, `R` rock, `s` stump, and `@` marks
the character.

## Practical guidance

- When a `place_path`/`place_entity` call reports a blocker, render the map
  around `blocker.position` to see the whole obstruction in context. Trees,
  rocks and stumps are exactly what block belt and pole routing, and they now
  appear in the rows instead of blurring into blocked terrain.
- Clear one obstacle with a targeted deconstruct/mine action; `deconstruct_area`
  with `include_neutral=True` clears a rectangle and returns tree/rock products.
- `entities` carries exact positions, directions and statuses for anything the
  glyphs compress; prefer it when alignment matters.
- The structured list is capped at 128 entities and `entities_truncated` marks
  the cap; shrink `radius` if you need certainty.
