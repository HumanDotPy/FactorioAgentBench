storage.actions.rotate_entities = function(player_index, entries, direction)
    local character = storage.agent_characters[player_index]
    if not character or not character.valid then return {error="no character"} end
    if direction ~= 0 and direction ~= 4 and direction ~= 8 and direction ~= 12 then
        return {error="direction must be 0, 4, 8, or 12"}
    end

    local function nearest(surface, position, name)
        local area = {
            {position.x - 0.5, position.y - 0.5},
            {position.x + 0.5, position.y + 0.5},
        }
        local found = surface.find_entities_filtered{area=area, force=character.force}
        local best, best_distance = nil, math.huge
        for _, entity in ipairs(found) do
            local matches_name = name == nil or name == "" or entity.name == name
            if matches_name and entity.name ~= "character" and entity.valid then
                local distance = (position.x - entity.position.x) ^ 2
                    + (position.y - entity.position.y) ^ 2
                if distance < best_distance then
                    best, best_distance = entity, distance
                end
            end
        end
        return best
    end

    local function rotate_one(entity, requested)
        local target = storage.utils.inserter_engine_direction(entity.name,
            storage.utils.get_entity_direction(entity.name, requested))
        local engine_before = entity.direction
        if engine_before ~= target then
            pcall(function() entity.direction = target end)
            if entity.direction ~= target then
                local rotations = math.floor(((target - entity.direction + 16) % 16) / 4)
                for _ = 1, rotations do
                    pcall(function() entity.rotate() end)
                    if entity.direction == target then break end
                end
            end
        end
        return entity.direction == target, engine_before
    end

    local results, failed = {}, 0
    for _, entry in ipairs(entries or {}) do
        local position = {x = tonumber(entry.x) or 0, y = tonumber(entry.y) or 0}
        local entity = nearest(character.surface, position, entry.name)
        if entity == nil then
            failed = failed + 1
            results[#results + 1] = {
                position = position, name = entry.name,
                requested_direction = direction, rotated = false,
                error = "no entity matching the request at this position",
            }
        else
            local ok, engine_before = rotate_one(entity, direction)
            local record = {
                position = {x = entity.position.x, y = entity.position.y},
                name = entity.name, entity_id = entity.unit_number,
                requested_direction = direction,
                engine_direction_before = engine_before,
                engine_direction = entity.direction, rotated = ok,
            }
            if not ok then
                failed = failed + 1
                record.error = "engine refused the rotation"
            end
            results[#results + 1] = record
        end
    end

    return {
        requested = #(entries or {}),
        rotated = #(entries or {}) - failed,
        failed = failed,
        direction = direction,
        entities = results,
    }
end
