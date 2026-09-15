-- Follow a transport belt downstream or upstream and report lane contents plus
-- the first blocker. Bounded and read-only: never mutates the belt or the
-- character.
storage.actions.trace_belt = function(player_index, x, y, max_tiles, upstream)
    max_tiles = math.min(math.max(tonumber(max_tiles) or 64, 1), 256)
    upstream = upstream == true
    local character = storage.agent_characters[player_index]
    local surface = character.surface
    local position = {x = tonumber(x), y = tonumber(y)}
    local dirs = {[0] = "north", [4] = "east", [8] = "south", [12] = "west"}
    local vectors = {[0] = {0, -1}, [4] = {1, 0}, [8] = {0, 1}, [12] = {-1, 0}}

    local found = surface.find_entities_filtered{
        position = position, radius = 0.71, name = "transport-belt", limit = 1
    }
    local belt = found and found[1]
    if not belt then
        return {error = "no transport-belt at the requested position"}
    end

    local function lanes(entity)
        local result = {}
        for index = 1, 2 do
            local ok, line = pcall(function() return entity.get_transport_line(index) end)
            if ok and line then
                local items = {}
                for _, item in ipairs(line.get_contents() or {}) do
                    items[#items + 1] = {name = item.name, count = item.count}
                end
                result[#result + 1] = {index = index, items = items}
            end
        end
        return result
    end

    local function describe(entity)
        return {
            position = {x = entity.position.x, y = entity.position.y},
            direction = dirs[entity.direction] or tostring(entity.direction),
            active = entity.active,
            lanes = lanes(entity),
        }
    end

    local function offset(tile_position, vector)
        return {
            x = tile_position.x + vector[1],
            y = tile_position.y + vector[2],
        }
    end

    local function at_tile(tile_position)
        local entities = surface.find_entities_filtered{
            area = {
                {tile_position.x - 0.5, tile_position.y - 0.5},
                {tile_position.x + 0.5, tile_position.y + 0.5},
            },
            limit = 8,
        }
        local belt_here = nil
        local other = nil
        for _, entity in ipairs(entities or {}) do
            if entity.name == "transport-belt" then
                if not belt_here then belt_here = entity end
            elseif entity.name ~= "item-on-ground" and entity.type ~= "resource" then
                if not other then other = entity end
            end
        end
        return belt_here, other
    end

    local function output_feeds(belt_entity, target_position)
        local vector = vectors[belt_entity.direction]
        if not vector then
            return false
        end
        local output = offset(belt_entity.position, vector)
        return output.x == target_position.x and output.y == target_position.y
    end

    local function entity_receipt(entity)
        return {
            name = entity.name,
            type = entity.type,
            entity_id = entity.unit_number,
            position = {x = entity.position.x, y = entity.position.y},
        }
    end

    -- Upstream, only entities that can actually place items onto a belt count
    -- as a source. A tree or rock in the predecessor tile is not feeding the
    -- line, so it must not be reported as one.
    local feeder_types = {
        inserter = true,
        ["mining-drill"] = true,
        loader = true,
    }
    local function is_belt_feeder(entity)
        return entity ~= nil and feeder_types[entity.type] == true
    end

    local tiles = {}
    local blocker = nil
    local current = belt
    for _ = 1, max_tiles do
        tiles[#tiles + 1] = describe(current)
        local vector = vectors[current.direction] or {0, 0}
        if upstream then
            local behind_position = offset(current.position, {-vector[1], -vector[2]})
            local behind_belt, behind_other = at_tile(behind_position)
            local predecessor = nil
            if behind_belt and output_feeds(behind_belt, current.position) then
                predecessor = behind_belt
            end
            -- Side-load probes use a fixed order: left of flow, then right.
            local side_positions = {
                offset(current.position, {vector[2], -vector[1]}),
                offset(current.position, {-vector[2], vector[1]}),
            }
            local side_belts = {}
            local side_others = {}
            if not predecessor then
                for index, side_position in ipairs(side_positions) do
                    side_belts[index], side_others[index] = at_tile(side_position)
                end
                for index = 1, 2 do
                    if
                        side_belts[index]
                        and output_feeds(side_belts[index], current.position)
                    then
                        predecessor = side_belts[index]
                        break
                    end
                end
            end
            if predecessor then
                current = predecessor
            else
                local other = nil
                local other_position = behind_position
                local candidates = {
                    {behind_other, behind_position},
                    {side_others[1], side_positions[1]},
                    {side_others[2], side_positions[2]},
                }
                for _, candidate in ipairs(candidates) do
                    if is_belt_feeder(candidate[1]) then
                        other = candidate[1]
                        other_position = candidate[2]
                        break
                    end
                end
                blocker = {
                    position = {x = other_position.x, y = other_position.y},
                    reason = other and "fed_by_entity" or "start_of_line",
                }
                if other then
                    blocker.entity = entity_receipt(other)
                end
                break
            end
        else
            local next_position = offset(current.position, vector)
            local next_belt, other = at_tile(next_position)
            if not next_belt then
                blocker = {
                    position = next_position,
                    reason = other and "blocked_by_entity" or "end_of_line",
                }
                if other then
                    blocker.entity = entity_receipt(other)
                end
                break
            end
            current = next_belt
        end
    end
    if blocker == nil then
        blocker = {
            position = {x = current.position.x, y = current.position.y},
            reason = "max_tiles_reached",
        }
    end
    return {
        start = {x = belt.position.x, y = belt.position.y},
        tiles = tiles,
        total_tiles = #tiles,
        blocker = blocker,
    }
end
