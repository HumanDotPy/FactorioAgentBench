local ib_direction_vectors = {
    [0] = {x = 0, y = -1},
    [4] = {x = 1, y = 0},
    [8] = {x = 0, y = 1},
    [12] = {x = -1, y = 0},
}
local ib_cardinals = {0, 4, 8, 12}
local ib_attempt_limit = 32
local ib_rejection_limit = 8

local function ib_tile_key(x, y)
    return x .. "," .. y
end

local function ib_tiles(entity)
    local prototype = prototypes.entity[entity.name]
    local width = prototype and prototype.tile_width or 1
    local height = prototype and prototype.tile_height or 1
    local position = entity.position
    local min_x = math.floor(position.x - width / 2 + 0.5)
    local min_y = math.floor(position.y - height / 2 + 0.5)
    local tiles = {}
    for tx = min_x, min_x + width - 1 do
        for ty = min_y, min_y + height - 1 do
            tiles[ib_tile_key(tx, ty)] = {x = tx, y = ty}
        end
    end
    return tiles
end

local function ib_describe(entity)
    return {
        name = entity.name,
        position = {x = entity.position.x, y = entity.position.y},
        entity_id = entity.unit_number,
    }
end

local function ib_find_entity(surface, requested, exclude)
    local best = nil
    local best_distance = math.huge
    local function consider(candidate)
        if candidate == nil or not candidate.valid or candidate == exclude then
            return
        end
        if candidate.type == "character" or candidate.type == "item-entity"
            or candidate.type == "entity-ghost" then
            return
        end
        local dx = candidate.position.x - requested.x
        local dy = candidate.position.y - requested.y
        local distance = dx * dx + dy * dy
        if distance < best_distance then
            best = candidate
            best_distance = distance
        end
    end
    for _, candidate in ipairs(surface.find_entities_filtered{
        position = requested, radius = 0.5}) do
        consider(candidate)
    end
    if best == nil then
        for _, candidate in ipairs(surface.find_entities_filtered{
            position = requested, radius = 1.5}) do
            consider(candidate)
        end
    end
    return best
end

local function ib_min_tile_gap(source_tiles, target_tiles)
    local best = math.huge
    local best_diagonal = false
    for _, source in pairs(source_tiles) do
        for _, target in pairs(target_tiles) do
            local dx = math.abs(source.x - target.x)
            local dy = math.abs(source.y - target.y)
            local manhattan = dx + dy
            if manhattan < best then
                best = manhattan
                best_diagonal = dx >= 1 and dy >= 1
            end
        end
    end
    return best, best_diagonal
end

local function ib_rotate_offset(offset, direction)
    local x = offset.x or offset[1] or 0
    local y = offset.y or offset[2] or 0
    local angle = direction * math.pi / 8
    local c, s = math.cos(angle), math.sin(angle)
    return {x = x * c - y * s, y = x * s + y * c}
end

local function ib_normalise_offset(offset, fallback_x, fallback_y)
    if offset == nil then
        return {x = fallback_x, y = fallback_y}
    end
    return {
        x = offset.x or offset[1] or fallback_x,
        y = offset.y or offset[2] or fallback_y,
    }
end

local function ib_inserter_offsets(prototype)
    return ib_normalise_offset(prototype.inserter_pickup_position, 0, -1),
        ib_normalise_offset(prototype.inserter_drop_position, 0, 1)
end

local function ib_reach(pickup, drop)
    local reach = math.max(math.abs(pickup.x), math.abs(pickup.y),
        math.abs(drop.x), math.abs(drop.y))
    return math.max(1, math.ceil(reach) + 1)
end

local function ib_candidates(source_tiles, target_tiles, reach, player_position)
    local seen = {}
    local candidates = {}
    for _, source in pairs(source_tiles) do
        for dx = -reach, reach do
            for dy = -reach, reach do
                if dx ~= 0 or dy ~= 0 then
                    local x = source.x + dx
                    local y = source.y + dy
                    local key = ib_tile_key(x, y)
                    if not seen[key] and not source_tiles[key]
                        and not target_tiles[key] then
                        seen[key] = true
                        candidates[#candidates + 1] = {x = x, y = y}
                    end
                end
            end
        end
    end
    table.sort(candidates, function(a, b)
        local ax = a.x + 0.5 - player_position.x
        local ay = a.y + 0.5 - player_position.y
        local bx = b.x + 0.5 - player_position.x
        local by = b.y + 0.5 - player_position.y
        local da = ax * ax + ay * ay
        local db = bx * bx + by * by
        if da ~= db then
            return da < db
        end
        if a.x ~= b.x then
            return a.x < b.x
        end
        return a.y < b.y
    end)
    return candidates
end

storage.actions.insert_between = function(player_index, inserter, source_x, source_y, target_x, target_y)
    local player = storage.utils.ensure_valid_character(player_index)
    local surface = player.surface

    local prototype = prototypes.entity[inserter]
    if prototype == nil then
        local name = inserter:gsub(" ", "_"):gsub("-", "_")
        error(name .. " isn't a valid entity prototype. Did you make a typo?")
    end
    if prototype.type ~= "inserter" then
        error(inserter .. " is a " .. prototype.type
            .. "; insert_between places an inserter between two entities")
    end

    local source = ib_find_entity(surface, {x = source_x, y = source_y}, nil)
    if source == nil then
        return {status = "impossible",
            reason = "no entity found at the source position (" .. source_x
                .. ", " .. source_y .. ")"}
    end
    local source_tiles = ib_tiles(source)
    local target = ib_find_entity(surface, {x = target_x, y = target_y}, source)
    if target == nil then
        if source_tiles[ib_tile_key(math.floor(target_x), math.floor(target_y))] then
            return {status = "impossible",
                reason = "source and target resolve to the same entity at ("
                    .. target_x .. ", " .. target_y
                    .. "); pass two different entities or positions"}
        end
        return {status = "impossible",
            reason = "no entity found at the target position (" .. target_x
                .. ", " .. target_y .. ")"}
    end
    local target_tiles = ib_tiles(target)
    local pickup_offset, drop_offset = ib_inserter_offsets(prototype)
    local reach = ib_reach(pickup_offset, drop_offset)
    local candidates = ib_candidates(source_tiles, target_tiles, reach, player.position)

    local attempts = 0
    local rejections = {}
    local global_failure = nil

    for _, candidate in ipairs(candidates) do
        if attempts >= ib_attempt_limit or global_failure then
            break
        end
        for _, direction in ipairs(ib_cardinals) do
            local engine_direction = storage.utils.inserter_engine_direction(inserter, direction)
            local pickup = ib_rotate_offset(pickup_offset, engine_direction)
            local drop = ib_rotate_offset(drop_offset, engine_direction)
            local pickup_tile = {
                x = candidate.x + 0.5 + pickup.x,
                y = candidate.y + 0.5 + pickup.y,
            }
            local drop_tile = {
                x = candidate.x + 0.5 + drop.x,
                y = candidate.y + 0.5 + drop.y,
            }
            local pickup_x = math.floor(pickup_tile.x)
            local pickup_y = math.floor(pickup_tile.y)
            local drop_x = math.floor(drop_tile.x)
            local drop_y = math.floor(drop_tile.y)
            if source_tiles[ib_tile_key(pickup_x, pickup_y)]
                and target_tiles[ib_tile_key(drop_x, drop_y)] then
                attempts = attempts + 1
                local ok, receipt = pcall(storage.actions.place_entity, player_index,
                    inserter, direction, candidate.x + 0.5, candidate.y + 0.5, true)
                if ok and type(receipt) == "table" and not receipt.error then
                    return {
                        status = "placed",
                        source = ib_describe(source),
                        target = ib_describe(target),
                        inserter = inserter,
                        tile = {x = candidate.x + 0.5, y = candidate.y + 0.5},
                        direction = direction,
                        pickup_tile = {x = pickup_x + 0.5, y = pickup_y + 0.5},
                        drop_tile = {x = drop_x + 0.5, y = drop_y + 0.5},
                        attempts = attempts,
                        entity = receipt,
                    }
                end
                local reason
                if ok then
                    reason = receipt and (receipt.reason or receipt.error) or "placement_rejected"
                else
                    reason = tostring(receipt)
                end
                if string.find(reason, "inventory", 1, true)
                    or string.find(reason, "too far away", 1, true)
                    or string.find(reason, "isn't something that exists", 1, true) then
                    global_failure = reason
                    break
                end
                if #rejections < ib_rejection_limit then
                    rejections[#rejections + 1] = {
                        tile = {x = candidate.x + 0.5, y = candidate.y + 0.5},
                        direction = direction,
                        reason = reason,
                    }
                end
            end
        end
    end

    local source_description = ib_describe(source)
    local target_description = ib_describe(target)
    if global_failure then
        return {
            status = "impossible",
            reason = global_failure,
            source = source_description,
            target = target_description,
            inserter = inserter,
            attempts = attempts,
            rejections = rejections,
        }
    end

    local reason
    if attempts == 0 then
        local gap, diagonal = ib_min_tile_gap(source_tiles, target_tiles)
        if gap == 1 then
            reason = source.name .. " and " .. target.name
                .. " are edge-adjacent: an inserter picks from one tile and drops on the"
                .. " opposite tile, so it needs an empty tile between the pickup and the"
                .. " drop; move one entity one tile further apart, or use a belt, or use"
                .. " place_between with an explicit tile"
        elseif diagonal then
            reason = source.name .. " and " .. target.name
                .. " are diagonally adjacent: an inserter's pickup and drop tiles are"
                .. " opposite orthogonal neighbours, so it cannot bridge a corner; use"
                .. " two inserters with a belt between them"
        else
            local pickup_span = math.max(1, math.floor(math.max(
                math.abs(pickup_offset.x), math.abs(pickup_offset.y)) + 0.5))
            local drop_span = math.max(1, math.floor(math.max(
                math.abs(drop_offset.x), math.abs(drop_offset.y)) + 0.5))
            reason = "no inserter tile can reach a " .. source.name .. " tile and a "
                .. target.name .. " tile simultaneously (closest tiles are " .. gap
                .. " apart); this inserter picks " .. pickup_span .. " tile(s) and drops "
                .. drop_span .. " tile(s) on opposite sides of its own tile, so separate"
                .. " the entities by " .. (pickup_span + drop_span)
                .. " tiles on one axis with every tile between them free"
        end
    else
        reason = attempts .. " candidate inserter tile(s) were geometrically valid but"
            .. " could not be placed (first reason: "
            .. (rejections[1] and rejections[1].reason or "unknown") .. ")"
    end

    return {
        status = "impossible",
        reason = reason,
        source = source_description,
        target = target_description,
        inserter = inserter,
        attempts = attempts,
        rejections = rejections,
    }
end
