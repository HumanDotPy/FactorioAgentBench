local CATCH_DROP_TYPES = "mining drills (burner-mining-drill, electric-mining-drill) and inserters (burner-inserter, inserter, fast-inserter, stack-inserter, filter-inserter)"

local function catch_accepts_items(entity)
    if entity.type == "transport-belt" or entity.type == "underground-belt"
        or entity.type == "splitter" or entity.type == "inserter"
        or entity.type == "loader" or entity.type == "linked-belt" then
        return true
    end
    local ok, accepts = pcall(function()
        local inventory_defines = {
            defines.inventory.chest,
            defines.inventory.furnace_source,
            defines.inventory.assembling_machine_input,
            defines.inventory.crafter_input,
        }
        for _, inventory_define in ipairs(inventory_defines) do
            if inventory_define and entity.get_inventory(inventory_define) then
                return true
            end
        end
        return false
    end)
    return ok and accepts or false
end

local function catch_sort_entries(entries)
    table.sort(entries, function(a, b)
        local ua = a.entity_id or math.huge
        local ub = b.entity_id or math.huge
        if ua ~= ub then
            return ua < ub
        end
        if a.position.x ~= b.position.x then
            return a.position.x < b.position.x
        end
        return a.position.y < b.position.y
    end)
end

local function catch_resolve_source(player, source_id, x, y)
    if source_id ~= nil and storage.entity_handles then
        local candidate = storage.entity_handles[source_id]
        if candidate and candidate.valid then
            return candidate
        end
    end
    if x == nil or y == nil then
        return nil
    end
    local origin = {x = x, y = y}
    local source, best = nil, nil
    for _, candidate in ipairs(player.surface.find_entities_filtered{
        position = origin, radius = 1.5, limit = 32}) do
        if candidate.valid and candidate.drop_position then
            local dx = candidate.position.x - origin.x
            local dy = candidate.position.y - origin.y
            local distance = math.sqrt(dx * dx + dy * dy)
            if best == nil or distance < best then
                source, best = candidate, distance
            end
        end
    end
    return source
end

local function catch_footprint(entity)
    local width = entity.prototype.tile_width or 1
    local height = entity.prototype.tile_height or 1
    local position = entity.position
    local left = position.x - width / 2
    local top = position.y - height / 2
    return {
        left_top = {x = left, y = top},
        right_bottom = {x = left + width, y = top + height},
    }, width, height
end

local function catch_parity(width, height)
    if width % 2 == 0 and height % 2 == 0 then
        return "corner"
    end
    if width % 2 == 1 and height % 2 == 1 then
        return "center"
    end
    return "mixed"
end

storage.actions.catch_output = function(player_index, source_id, prototype, x, y)
    local player = storage.utils.ensure_valid_character(player_index)
    local surface = player.surface
    if not surface then
        return {status = "source_missing", error = "player has no surface"}
    end

    local source = catch_resolve_source(player, source_id, x, y)
    if not source then
        return {status = "source_missing",
            error = "no live machine found for the given entity handle or position; "
                .. "pass an Entity from get_entities/resolve_entity or a live Position"}
    end
    if not source.drop_position then
        return {status = "no_drop_position",
            error = "\"" .. source.name .. "\" has no drop_position; entities with one: "
                .. CATCH_DROP_TYPES}
    end

    local drop = source.drop_position
    local catch = {x = math.floor(drop.x) + 0.5, y = math.floor(drop.y) + 0.5}
    local footprint, width, height = catch_footprint(source)
    local source_summary = {
        entity_id = source.unit_number,
        name = source.name,
        position = {x = source.position.x, y = source.position.y},
        drop_position = {x = drop.x, y = drop.y},
        footprint = footprint,
        tile_size = {width = width, height = height},
        parity = catch_parity(width, height),
    }

    local blockers, output_tiles = {}, {}
    local ground_items, ground_by_item = 0, {}
    for _, candidate in ipairs(surface.find_entities_filtered{
        position = catch, radius = 0.5, limit = 32}) do
        if candidate.valid and candidate ~= source then
            if candidate.type == "item-entity" then
                local stack = candidate.stack
                local name = stack and stack.name or candidate.name
                local count = stack and stack.count or 1
                ground_items = ground_items + count
                ground_by_item[name] = (ground_by_item[name] or 0) + count
            else
                blockers[#blockers + 1] = {
                    name = candidate.name,
                    type = candidate.type,
                    position = {x = candidate.position.x, y = candidate.position.y},
                    entity_id = candidate.unit_number,
                    accepts_items = catch_accepts_items(candidate),
                }
            end
        end
    end
    catch_sort_entries(blockers)

    for _, candidate in ipairs(surface.find_entities_filtered{
        position = catch, radius = 2.5, limit = 48}) do
        if candidate.valid and candidate ~= source and candidate.drop_position then
            local candidate_drop = candidate.drop_position
            local tile = {
                x = math.floor(candidate_drop.x) + 0.5,
                y = math.floor(candidate_drop.y) + 0.5,
            }
            if tile.x == catch.x and tile.y == catch.y then
                output_tiles[#output_tiles + 1] = {
                    name = candidate.name,
                    position = {x = candidate.position.x, y = candidate.position.y},
                    drop_position = {x = candidate_drop.x, y = candidate_drop.y},
                    entity_id = candidate.unit_number,
                }
            end
        end
    end
    catch_sort_entries(output_tiles)

    local warnings = {}
    local status = "ready"
    local receiver = nil
    for _, blocker in ipairs(blockers) do
        if blocker.accepts_items then
            receiver = blocker
            break
        end
    end
    if receiver then
        status = "already_receiver"
        warnings[#warnings + 1] = "catch tile (" .. catch.x .. ", " .. catch.y
            .. ") already holds " .. receiver.name .. " at (" .. receiver.position.x
            .. ", " .. receiver.position.y .. ") which accepts items; nothing was placed"
    elseif #blockers > 0 then
        status = "blocked"
        local blocker = blockers[1]
        warnings[#warnings + 1] = "catch tile (" .. catch.x .. ", " .. catch.y
            .. ") is occupied by " .. blocker.name .. " at (" .. blocker.position.x
            .. ", " .. blocker.position.y
            .. "), another machine's body/footprint rather than a receiver; clear it before catching this output"
    elseif #output_tiles > 0 then
        status = "blocked"
        local owner = output_tiles[1]
        warnings[#warnings + 1] = "catch tile (" .. catch.x .. ", " .. catch.y
            .. ") is the output tile of " .. owner.name .. " at (" .. owner.position.x
            .. ", " .. owner.position.y
            .. "); placing a receiver there would block that machine's drop, and the engine rejects the build"
    end
    if ground_items > 0 then
        warnings[#warnings + 1] = tostring(ground_items)
            .. " item(s) already on the ground at the catch tile before placement; "
            .. "they do not block construction but should be picked up"
    end

    local placed, placement = nil, nil
    if status == "ready" then
        local ok, result = pcall(storage.actions.place_entity, player_index,
            prototype, 0, catch.x, catch.y, true)
        if not ok then
            status = "placement_failed"
            placement = {error = tostring(result)}
            warnings[#warnings + 1] = "engine placement raised: " .. tostring(result)
        elseif type(result) ~= "table" then
            status = "placement_failed"
            placement = result
            warnings[#warnings + 1] = "engine placement returned " .. tostring(result)
        elseif result.error then
            status = result.reason or "placement_rejected"
            placement = result
            warnings[#warnings + 1] = "engine manual build check rejected the catch tile: "
                .. tostring(result.reason or "placement_rejected")
        else
            status = "placed"
            local position = result.position
            placed = {
                entity_id = result.id,
                name = result.name,
                position = {
                    x = (position and position.x) or catch.x,
                    y = (position and position.y) or catch.y,
                },
            }
            if result.drop_warning then
                warnings[#warnings + 1] = result.drop_warning
            end
        end
    end

    return {
        status = status,
        source = source_summary,
        drop_position = {x = drop.x, y = drop.y},
        catch_tile = catch,
        placed = placed,
        item_on_ground_before = ground_items,
        item_on_ground = ground_by_item,
        blockers = blockers,
        output_tiles = output_tiles,
        placement = placement,
        warnings = warnings,
        tick = game.tick,
    }
end
