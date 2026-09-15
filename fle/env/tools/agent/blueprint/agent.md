# blueprint

Blueprints are native construction plans. `place` creates ghosts; it does not
build entities or consume materials. Build matching ghosts manually with
`place_entity`, or let construction robots use available network materials.
Recipes, settings, wires and item requests are retained by Factorio.

```python
# Capture entities, tiles, modules, wires, station names and trains.
blueprint('save', 'iron-line', 10, 10, radius=16)
blueprint('list')
blueprint('get', 'iron-line')                 # Full native exchange string
blueprint('inspect', 'iron-line')             # Full editable native JSON

# Create or edit a design using a native document or exchange string.
blueprint('import', 'new-design', {'blueprint': {
    'item': 'blueprint', 'version': 562949958467584,
    'entities': [{'entity_number': 1, 'name': 'transport-belt',
                  'position': {'x': 0.5, 'y': 0.5}, 'direction': 4}]
}})
design = blueprint('inspect', 'new-design')
design['blueprint']['label'] = 'Eastbound belt'
blueprint('edit', 'new-design', design)

# Native placement: cardinal direction 0/4/8/12; normal, forced, superforced.
blueprint('place', 'iron-line', 40, 20, direction=4, build_mode='normal')
blueprint('ghosts', 40, 20, radius=32, offset=0)
# Receipt gives created_ghosts and up to 128 positions; zero can mean collision
# or that the plan already exists. Inspect ghosts before assuming construction.

# Books retain complete native metadata; select zero-based entry indices.
blueprint('place', 'my-book', 40, 20, book_path=[2, 0])
# Imported native planners mark/cancel construction orders.
blueprint('apply', 'upgrade-belts', 40, 20, radius=16)
blueprint('apply', 'clear-area', 40, 20, radius=16, cancel=True)
blueprint('delete', 'new-design')
```

`import`/`edit` replace the complete document, preserving unspecified engine
fields only when retained in that document. Use inspect → edit for changes to
an existing design. The engine rejects invalid documents before saving. The
codec accepts blueprints, nested books, upgrade planners and deconstruction
planners. Import/inspect/get do not modify world entities.

For unrestricted experiments use the direct `factorio_reference_world` MCP tool:
create → execute native Lua → run exact ticks → capture to a library name →
place in the real factory. This is a separate process with all research and free
native construction. Only designs transfer back. See the
[workshop contract](../../../../../docs/architecture/blueprint-workshop.md).

The library is lease-scoped by default and checkpointed. An explicitly supplied
lineage/generation scope uses shared durable storage. Reference worlds are owned
by the lease and released with it. Capture is bounded to a radius in (0,128].
There is no geometric flip convenience argument in the headless API; native
JSON remains editable, including entity mirror settings.
