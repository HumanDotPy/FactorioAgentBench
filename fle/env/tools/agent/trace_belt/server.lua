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
    local BELT_TYPES = {["transport-belt"] = true, ["underground-belt"] = true}

    local function is_belt(entity)
        return entity ~= nil and BELT_TYPES[entity.type] == true
    end

    local function is_ground_belt(entity)
        return entity ~= nil and entity.type == "transport-belt"
    end

    local function is_underground_belt(entity)
        return entity ~= nil and entity.type == "underground-belt"
    end

    local found = surface.find_entities_filtered{
        position = position, radius = 0.71,
        type = {"transport-belt", "underground-belt"}, limit = 1
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
            name = entity.name,
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
            if is_belt(entity) then
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

    local function receives_from(belt_entity, source_position)
        local vector = vectors[belt_entity.direction]
        if not vector then
            return false
        end
        local behind = offset(belt_entity.position, {-vector[1], -vector[2]})
        if behind.x == source_position.x and behind.y == source_position.y then
            return true
        end
        local left = offset(belt_entity.position, {vector[2], -vector[1]})
        local right = offset(belt_entity.position, {-vector[2], vector[1]})
        return (left.x == source_position.x and left.y == source_position.y)
            or (right.x == source_position.x and right.y == source_position.y)
    end

    local function find_underground(origin_position, direction, vector, name, wanted_kind)
        local reach = 9
        if prototypes and prototypes.entity then
            local prototype = prototypes.entity[name]
            if prototype and prototype.max_distance then
                reach = math.max(1, math.floor(prototype.max_distance))
            end
        end
        for distance = 1, reach do
            local probe = offset(origin_position, {vector[1] * distance, vector[2] * distance})
            local candidate = at_tile(probe)
            if is_underground_belt(candidate) then
                if candidate.name == name
                    and candidate.direction == direction
                    and candidate.belt_to_ground_type == wanted_kind then
                    return candidate
                end
                return nil
            end
        end
        return nil
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
            local advanced = false
            if is_ground_belt(behind_belt) and output_feeds(behind_belt, current.position) then
                predecessor = behind_belt
            elseif is_underground_belt(behind_belt)
                and behind_belt.belt_to_ground_type == "output"
                and behind_belt.direction == current.direction then
                local entrance = find_underground(
                    behind_belt.position, current.direction,
                    {-vector[1], -vector[2]}, behind_belt.name, "input"
                )
                if entrance then
                    tiles[#tiles + 1] = describe(behind_belt)
                    if #tiles >= max_tiles then
                        blocker = {
                            position = {x = entrance.position.x, y = entrance.position.y},
                            reason = "max_tiles_reached",
                        }
                        break
                    end
                    current = entrance
                    advanced = true
                end
            end
            if not advanced then
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
                            is_ground_belt(side_belts[index])
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
            end
        else
            local next_position = offset(current.position, vector)
            local next_belt, other = at_tile(next_position)
            if is_ground_belt(next_belt) and receives_from(next_belt, current.position) then
                current = next_belt
            elseif is_underground_belt(next_belt)
                and next_belt.belt_to_ground_type == "input"
                and next_belt.direction == current.direction then
                local output = find_underground(
                    next_belt.position, current.direction, vector,
                    next_belt.name, "output"
                )
                if output then
                    tiles[#tiles + 1] = describe(next_belt)
                    if #tiles >= max_tiles then
                        blocker = {
                            position = {x = output.position.x, y = output.position.y},
                            reason = "max_tiles_reached",
                        }
                        break
                    end
                    current = output
                else
                    blocker = {
                        position = next_position,
                        reason = "blocked_by_entity",
                        entity = entity_receipt(next_belt),
                    }
                    break
                end
            elseif next_belt then
                blocker = {
                    position = next_position,
                    reason = "blocked_by_reversed_belt",
                    entity = entity_receipt(next_belt),
                }
                break
            else
                blocker = {
                    position = next_position,
                    reason = other and "blocked_by_entity" or "end_of_line",
                }
                if other then
                    blocker.entity = entity_receipt(other)
                end
                break
            end
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
