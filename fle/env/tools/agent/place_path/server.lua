storage.actions.place_path = function() return true end

storage.actions.plan_path = function(player_index, entity, tiles)
    local player = storage.agent_characters[player_index]
    if not player then
        error("Player not found")
    end
    local prototype = prototypes.entity[entity]
    if prototype == nil then
        local name = tostring(entity):gsub(" ", "_"):gsub("-", "_")
        error(name .. " isn't a valid entity prototype. Did you make a typo?")
    end

    local entries = {}
    local blocked = 0
    for _, tile in ipairs(tiles or {}) do
        local position = {x = tile.x, y = tile.y}
        local direction = tile.direction
        if direction == nil then
            direction = defines.direction.north
        end
        local engine_direction = storage.utils.inserter_engine_direction(entity,
            storage.utils.get_entity_direction(entity, direction))
        local placeable = storage.utils.can_place_entity(
            player, entity, position, engine_direction)
        local entry = {
            position = position,
            direction = direction,
            engine_direction = engine_direction,
            placeable = placeable,
        }
        if not placeable then
            blocked = blocked + 1
            local diagnostic = storage.utils.spatial_diagnostics(
                player.surface, position, prototype.collision_box,
                engine_direction, prototype.collision_mask, nil, prototype)
            entry.reason = diagnostic.reason
            entry.footprint = diagnostic.footprint
            entry.blocked_by = diagnostic.blocked_by
            entry.overlapping_entities = diagnostic.overlapping_entities
            entry.colliding_tiles = diagnostic.colliding_tiles
        end
        entries[#entries + 1] = entry
    end

    return {
        prototype = entity,
        placeable = blocked == 0,
        requested = #entries,
        blocked = blocked,
        tiles = entries,
    }
end
