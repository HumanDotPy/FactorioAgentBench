storage.actions.can_place_entity = function(player_index, entity, direction, x, y)
    local player = storage.agent_characters[player_index]
    if not player then
        error("Player not found")
    end
    if prototypes.entity[entity] == nil then
        local name = entity:gsub(" ", "_"):gsub("-", "_")
        error(name .. " isn't a valid entity prototype. Did you make a typo?")
    end

    if direction == nil then
        direction = defines.direction.north
    end
    local entity_direction = storage.utils.inserter_engine_direction(entity,
        storage.utils.get_entity_direction(entity, direction))

    local position = {x = x, y = y}
    local dx = player.position.x - x
    local dy = player.position.y - y
    local distance = math.sqrt(dx * dx + dy * dy)
    local max_distance = player.reach_distance or player.build_distance
    if distance > max_distance then
        return false
    end

    if player.get_item_count(entity) == 0 then
        return false
    end

    if not storage.utils.can_place_entity(player, entity, position, entity_direction) then
        return false
    end
    return true
end

storage.actions.plan_placement = function(player_index, entity, direction, x, y)
    local player = storage.agent_characters[player_index]
    if not player then
        error("Player not found")
    end
    local prototype = prototypes.entity[entity]
    if prototype == nil then
        local name = entity:gsub(" ", "_"):gsub("-", "_")
        error(name .. " isn't a valid entity prototype. Did you make a typo?")
    end

    if direction == nil then
        direction = defines.direction.north
    end
    local entity_direction = storage.utils.inserter_engine_direction(entity,
        storage.utils.get_entity_direction(entity, direction))

    local position = {x = x, y = y}
    local placeable = storage.utils.can_place_entity(
        player, entity, position, entity_direction)
    local dx = player.position.x - x
    local dy = player.position.y - y
    local distance = math.sqrt(dx * dx + dy * dy)
    local max_distance = player.reach_distance or player.build_distance

    local result = {
        prototype = entity,
        position = position,
        direction = direction,
        engine_direction = entity_direction,
        building = prototype.type,
        placeable = placeable,
        within_reach = distance <= max_distance,
        inventory_count = player.get_item_count(entity),
    }
    if not placeable then
        local diagnostic = storage.utils.spatial_diagnostics(player.surface, position,
            prototype.collision_box, entity_direction, prototype.collision_mask, nil,
            prototype)
        result.reason = diagnostic.reason
        result.footprint = diagnostic.footprint
        result.blocked_by = diagnostic.blocked_by
        result.overlapping_entities = diagnostic.overlapping_entities
        result.colliding_tiles = diagnostic.colliding_tiles
    end
    return result
end
