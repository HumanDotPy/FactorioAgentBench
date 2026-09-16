storage.actions.rotate_entity = function(player_index, x, y, direction, entity)
    local character = storage.agent_characters[player_index]
    local position = {x=x, y=y}
    local surface = character.surface

    local function table_contains(tbl, element)
        for _, value in ipairs(tbl) do
            if value == element then
                return true
            end
        end
        return false
    end

    local closest_distance = math.huge
    local closest_entity = nil
    local area = {{position.x - 0.5, position.y - 0.5}, {position.x + 0.5, position.y + 0.5}}
    local buildings = surface.find_entities_filtered{area = area, force = character.force, name = entity}

    for _, building in ipairs(buildings) do
        if building.name ~= 'character' then
            local distance = ((position.x - building.position.x) ^ 2 + (position.y - building.position.y) ^ 2) ^ 0.5
            if distance < closest_distance then
                closest_distance = distance
                closest_entity = building
            end
        end
    end

    if closest_entity == nil then
        error("No entity to rotate at the given coordinates.")
    end

    local valid_directions = {0, 4, 8, 12}

    if not table_contains(valid_directions, direction) then
        error("Invalid direction " .. direction .. " provided. Please use 0 (north), 4 (east), 8 (south), or 12 (west).")
    end

    local target_direction = storage.utils.inserter_engine_direction(closest_entity.name,
        storage.utils.get_entity_direction(closest_entity.name, direction))

    local function rotate_steps(target)
        local rotations_needed = ((target - closest_entity.direction + 16) % 16) / 4
        for _ = 1, rotations_needed do
            closest_entity.rotate()
            if closest_entity.direction == target then
                break
            end
        end
        return closest_entity.direction == target
    end

    local function assign_direction(target)
        pcall(function()
            closest_entity.direction = target
        end)
        return closest_entity.direction == target
    end

    if closest_entity.direction ~= target_direction then
        local rotated = false

        if closest_entity.type == "assembling-machine" then
            rotated = rotate_steps(target_direction)
            if not rotated then
                rotated = assign_direction(target_direction)
            end
        else
            rotated = assign_direction(target_direction)
            if not rotated then
                rotated = rotate_steps(target_direction)
            end
        end

        if not rotated then
            if closest_entity.type == "assembling-machine" then
                error("Could not rotate " .. closest_entity.name ..
                    ". Factorio 2.0 only rotates assembling machines whose recipe uses a fluid; set a fluid recipe first.")
            end
            error("Could not rotate " .. closest_entity.name .. " to the requested direction.")
        end
    end

    local serialized = storage.utils.serialize_entity(closest_entity)
    serialized = storage.utils.inserter_direction_report(serialized, direction)
    return storage.utils.attach_connection_report(serialized, closest_entity,
        storage.agent_characters[player_index])
end
