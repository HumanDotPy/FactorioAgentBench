-- move_to

-- Register the tick handler when the module is loaded
    script.on_nth_tick(1, function(event)
        if not storage.fast and storage.walking_queues then
            storage.actions.update_walking_queues()
        end
    end)

--local function get_direction(from_pos, to_pos)
--    local dx = to_pos.x - from_pos.x
--    local dy = to_pos.y - from_pos.y
--    if dx == 0 and dy == 0 then
--        return nil
--    elseif math.abs(dx) > math.abs(dy) then
--        return dx > 0 and defines.direction.east or defines.direction.west
--    else
--        return dy > 0 and defines.direction.south or defines.direction.north
--    end
--end


local WALKABLE_ENTITY_TYPES = {
    ["transport-belt"] = true,
    ["underground-belt"] = true,
    ["splitter"] = true,
    ["lane-splitter"] = true,
    ["loader"] = true,
    ["linked-belt"] = true,
}

local function start_block_reason(player)
    if not player or not player.valid then
        return "no_character"
    end
    local surface = player.surface
    local box = player.prototype.collision_box
    local margin = 0.05
    local area = {
        {player.position.x + box.left_top.x - margin,
         player.position.y + box.left_top.y - margin},
        {player.position.x + box.right_bottom.x + margin,
         player.position.y + box.right_bottom.y + margin},
    }
    local blockers = surface.find_entities_filtered{
        area = area, collision_mask = "player", limit = 4
    }
    for _, entity in ipairs(blockers or {}) do
        if entity.valid and entity ~= player
            and not WALKABLE_ENTITY_TYPES[entity.type] then
            return entity.name
        end
    end
    local tile = surface.get_tile(player.position.x, player.position.y)
    if tile and tile.collides_with("player") then
        return "terrain"
    end
    return nil
end

local function unstick_character(player, attempts)
    local origin = {x = player.position.x, y = player.position.y}
    local reason = start_block_reason(player)
    if not reason then
        return {moved = false, steps = 0, reason = "start_free",
            position = {x = origin.x, y = origin.y}}
    end
    local steps = 0
    local limit = math.max(1, tonumber(attempts) or 1)
    while steps < limit do
        local escape = storage.utils.escape_character_to_free_tile
        if not escape then
            reason = "escape_unavailable"
            break
        end
        local stepped = escape(player, nil, nil, origin)
        if not stepped then
            break
        end
        steps = steps + 1
        reason = start_block_reason(player)
        if not reason then
            break
        end
    end
    return {moved = steps > 0, steps = steps,
        reason = reason or "start_free",
        position = {x = player.position.x, y = player.position.y}}
end

local WALKABLE_FALLBACK_LIMIT = 8

local function tile_is_walkable(surface, tile_x, tile_y)
    local tile = surface.get_tile(tile_x, tile_y)
    if not tile or tile.collides_with("player") then
        return false
    end
    local blockers = surface.find_entities_filtered{
        position = {x = tile_x + 0.5, y = tile_y + 0.5},
        radius = 0.45, collision_mask = "player", limit = 1
    }
    return not (blockers and #blockers > 0)
end

local function nearest_walkable(player, x, y, radius)
    if not player or not player.valid or x == nil or y == nil then
        return {status = "invalid"}
    end
    local surface = player.surface
    local scan = math.max(1, math.min(math.floor(tonumber(radius) or 8), 32))
    local base_x, base_y = math.floor(x), math.floor(y)
    local candidates = {}
    local order = 0
    for dx = -scan, scan do
        for dy = -scan, scan do
            local tile_x, tile_y = base_x + dx, base_y + dy
            local px, py = tile_x + 0.5, tile_y + 0.5
            local ox, oy = px - x, py - y
            order = order + 1
            candidates[#candidates + 1] = {
                x = px, y = py, tile_x = tile_x, tile_y = tile_y,
                distance = math.sqrt(ox * ox + oy * oy), order = order,
            }
        end
    end
    table.sort(candidates, function(a, b)
        if math.abs(a.distance - b.distance) > 1e-9 then
            return a.distance < b.distance
        end
        return a.order < b.order
    end)
    local walkable = {}
    for _, candidate in ipairs(candidates) do
        if tile_is_walkable(surface, candidate.tile_x, candidate.tile_y) then
            walkable[#walkable + 1] = {
                x = candidate.x, y = candidate.y,
                distance = math.floor(candidate.distance * 100 + 0.5) / 100,
            }
            if #walkable >= WALKABLE_FALLBACK_LIMIT then
                break
            end
        end
    end
    if #walkable == 0 then
        return {status = "none", requested = {x = x, y = y}, scanned_radius = scan}
    end
    return {status = "ok", requested = {x = x, y = y}, scanned_radius = scan,
        candidates = walkable}
end

storage.actions.move_to = function(player_index, path_handle, trailing_entity, is_trailing, stop_distance)
    -- Ensure we have a valid character, recreating if necessary
    local player = storage.utils.ensure_valid_character(player_index)
    if path_handle == "__position__" then
        return {x = player.position.x, y = player.position.y}
    elseif path_handle == "__nearest_walkable__" then
        return nearest_walkable(player, tonumber(trailing_entity),
            tonumber(is_trailing), tonumber(stop_distance))
    elseif path_handle == "__unstick__" then
        return unstick_character(player, stop_distance)
    elseif path_handle == "__status__" then
        local queue = storage.walking_queues and storage.walking_queues[player_index]
        local interrupt = nil
        if queue then
            for _, event in ipairs(storage.semantic_events or {}) do
                if event.tick >= (queue.start_tick or game.tick) then interrupt = event.type end
            end
        end
        return {active = queue ~= nil and queue.current_target ~= nil,
            x = player.position.x, y = player.position.y, tick = game.tick,
            stop_reason = queue and queue.stop_reason or "arrived", event=interrupt}
    elseif path_handle == "__cancel__" then
        player.walking_state = {walking = false}
        if storage.walking_queues then storage.walking_queues[player_index] = nil end
        return {active=false, x=player.position.x, y=player.position.y, stop_reason="cancelled"}
    end
    local path = storage.paths[path_handle]
    local surface = player.surface

    -- Check if path is valid
    if not path then
        error("Invalid path: nil for path_handle=" .. tostring(path_handle) .. " (path not yet computed or request_path failed - race condition likely)")
    elseif type(path) == "string" then
        error("Invalid path: " .. path .. " for path_handle=" .. tostring(path_handle))
    elseif type(path) ~= "table" or #path == 0 then
        error("Invalid path: " .. serpent.line(path) .. " for path_handle=" .. tostring(path_handle))
    end

    -- If fast mode is disabled, set up walking queue
    if not storage.fast then
        -- Initialize walking queue if it doesn't exist
        if not storage.walking_queues then
            storage.walking_queues = {}
        end

        -- Create or clear existing queue for this player
        if not storage.walking_queues[player_index] then
            storage.walking_queues[player_index] = {
                positions = {},
                current_target = nil,
                trailing_entity = trailing_entity,
                is_trailing = is_trailing,
                stop_distance = stop_distance or 0,
                final_target = path[#path].position,
                stop_reason = nil,
                start_tick = game.tick,
                last_progress_tick = game.tick,
                last_position = {x = player.position.x, y = player.position.y}
            }
        else
            storage.walking_queues[player_index].positions = {}
            storage.walking_queues[player_index].current_target = nil
            storage.walking_queues[player_index].trailing_entity = trailing_entity
            storage.walking_queues[player_index].is_trailing = is_trailing
            storage.walking_queues[player_index].stop_distance = stop_distance or 0
            storage.walking_queues[player_index].final_target = path[#path].position
            storage.walking_queues[player_index].stop_reason = nil
            storage.walking_queues[player_index].start_tick = game.tick
            storage.walking_queues[player_index].last_progress_tick = game.tick
            storage.walking_queues[player_index].best_distance = nil
            storage.walking_queues[player_index].last_position = {x = player.position.x, y = player.position.y}
        end

        -- Follow the pathfinder's segments, not a diagonal-then-cardinal shortcut
        -- toward a distant waypoint. Dense steering targets preserve clearance.
        local previous = player.position
        for _, point in ipairs(path) do
            local dx = point.position.x - previous.x
            local dy = point.position.y - previous.y
            local steps = math.max(1, math.ceil(math.sqrt(dx*dx + dy*dy) / 0.5))
            for step=1,steps do
                table.insert(storage.walking_queues[player_index].positions,
                    {x=previous.x + dx*step/steps, y=previous.y + dy*step/steps})
            end
            previous = point.position
        end

        -- Start walking to first position
        if #storage.walking_queues[player_index].positions > 0 then
            local target = storage.walking_queues[player_index].positions[1]
            storage.walking_queues[player_index].current_target = target
            player.walking_state = {
                walking = true,
                direction = storage.utils.get_direction(player.position, target)
            }
        end

        return player.position
    end

    local function rotate_entity(entity, direction)
        if not direction then return end
        local cardinal = direction - (direction % 4)
        local orientation = entity.type == "inserter" and (cardinal + 8) % 16 or cardinal
        for _ = 1, 4 do
            if entity.direction == orientation then return end
            local previous = entity.direction
            local rotated = pcall(function() entity.rotate() end)
            if not rotated or entity.direction == previous then return end
        end
    end

    local function place(place_position, direction)
        if storage.utils.can_place_entity(player, trailing_entity, place_position, direction) then
            if player.get_item_count(trailing_entity) > 0 then
                local created = surface.create_entity{name=trailing_entity, position=place_position, direction=direction, force=player.force, player=player, build_check_type=defines.build_check_type.manual, fast_replace=true}
                if created then
                    player.remove_item({name=trailing_entity, count=1})
                end
                return created
            else
                local inv_contents = storage.utils.format_inventory_for_error(player)
                error("\"No ".. trailing_entity .." in the inventory. Current inventory: " .. inv_contents .. "\"")
            end
        elseif surface.can_fast_replace{name=trailing_entity, position=place_position, direction=direction, force=player.force} then
            local existing_entity = surface.find_entity(trailing_entity, place_position)
            if existing_entity and existing_entity.direction ~= direction then
                rotate_entity(existing_entity, direction)
            end
            return existing_entity
        end
        return nil
    end

    local function place_diagonal(from_pos, to_pos, is_leading)
        local dx = to_pos.x - from_pos.x
        local dy = to_pos.y - from_pos.y
        local mid_pos = {x = from_pos.x , y = to_pos.y }

        local dir_x = dx > 0 and defines.direction.east or defines.direction.west
        local dir_y = dy > 0 and defines.direction.south or defines.direction.north

        if is_leading then
            place(to_pos, (dir_x + 8) % 16)

            local corner_dir
            if (dx > 0 and dy > 0) or (dx < 0 and dy < 0) then
                corner_dir = dir_x
            else
                corner_dir = dir_y
            end

            if dx == 1 and dy == 1 then
                corner_dir = defines.direction.east
            end

            place(mid_pos, (corner_dir + 8) % 16)
        else
            place(from_pos, dir_y)

            local corner_dir
            if (dx > 0 and dy > 0) or (dx < 0 and dy < 0) then
                corner_dir = dir_y
            else
                corner_dir = dir_x
            end

            if dx == 1 and dy == 1 then
                corner_dir = defines.direction.east
            end

            place(mid_pos, corner_dir)
        end
    end

    if is_trailing == 1 or is_trailing == 0 then
        if prototypes.entity[trailing_entity] == nil then
            error('No entity exists that can be laid')
        end
    end

    local prev_belt = nil
    local prev_pos = player.position
    for i = 1, #path do
        local current_position = player.position
        local target_position = path[i].position

        -- Calculate and accumulate movement ticks before teleporting
        storage.elapsed_ticks = storage.elapsed_ticks + storage.utils.calculate_movement_ticks(player, prev_pos, target_position)


        local direction = storage.utils.get_direction(prev_pos, target_position)

        if not direction then
            goto continue
        end

        local new_belt
        if is_trailing == 1 then
             if math.abs(prev_pos.x - target_position.x) == 1 and math.abs(prev_pos.y - target_position.y) == 1 then
                --game.print("Placing diagonal belt at " .. serpent.line(prev_pos) .. " to " .. serpent.line(target_position))
                place_diagonal(prev_pos, target_position, false)
            else
                --game.print("Placing at direction: " .. direction .. " Current position: " .. serpent.line(prev_pos) .. " Target position: " .. serpent.line(target_position))
                new_belt = place(prev_pos, direction)
                if prev_belt then
                    rotate_entity(prev_belt, storage.utils.get_direction(prev_belt.position, prev_pos))
                end
            end
            player.teleport(target_position)
        elseif is_trailing == 0 then
            if math.abs(prev_pos.x - target_position.x) == 1 and math.abs(prev_pos.y - target_position.y) == 1 then
                place_diagonal(prev_pos, target_position, true)
            else
                -- game.print("Placing at direction: " .. direction .. " Current position: " .. serpent.line(prev_pos) .. " Target position: " .. serpent.line(target_position))
                new_direction = (direction + 8) % 16
                new_belt = place(target_position, new_direction)
                if prev_belt then
                    rotate_entity(prev_belt, storage.utils.get_direction(prev_belt.position, current_position))
                end
            end
            player.teleport(target_position)
        else
            player.teleport(target_position)
        end
        prev_belt = new_belt
        prev_pos = target_position
        ::continue::
    end

    return player.position
end

-- Add this new function to handle the walking queue updates
-- This should be called on every tick
storage.actions.update_walking_queues = function()
    if not storage.walking_queues then return end

    for player_index, queue in pairs(storage.walking_queues) do
        -- Ensure we have a valid character, recreating if necessary
        local player = storage.utils.ensure_valid_character(player_index)
        if not player or not queue.current_target then goto continue end

        local final_distance = queue.final_target and ((player.position.x - queue.final_target.x)^2 +
                         (player.position.y - queue.final_target.y)^2)^0.5 or math.huge
        if final_distance <= (queue.stop_distance or 0) then
            player.walking_state = {walking = false}
            queue.positions = {}
            queue.current_target = nil
            queue.stop_reason = "arrived"
            goto continue
        end

        local distance = ((player.position.x - queue.current_target.x)^2 +
                         (player.position.y - queue.current_target.y)^2)^0.5

        -- A requested point can itself be occupied (for example, the Position
        -- returned for a tree). Do not steer into its collision box forever.
        -- This detects physical progress only; it does not choose a new route
        -- or alter the model's requested destination.
        if not queue.best_distance or distance < queue.best_distance - 0.05 then
            queue.best_distance = distance
            queue.last_progress_tick = game.tick
        elseif game.tick - (queue.last_progress_tick or game.tick) >= 180 then
            player.walking_state = {walking = false}
            local stepped = nil
            if storage.utils.escape_character_to_free_tile then
                stepped = storage.utils.escape_character_to_free_tile(
                    player, nil, nil, queue.final_target)
            end
            queue.positions = {}
            queue.current_target = nil
            if stepped then
                queue.stop_reason = "escaped"
            else
                queue.stop_reason = "blocked_no_progress"
            end
            goto continue
        end

        -- If player is close enough to current target
        -- Stay inside the pathfinder's clearance margin at obstacle corners.
        -- A one-tile shortcut can cut straight through a tree collision box.
        if distance < 0.25 then
            -- Remove the current position from queue
            table.remove(queue.positions, 1)

            -- If there are more positions, start walking to next one
            if #queue.positions > 0 then
                queue.current_target = queue.positions[1]
                queue.last_progress_tick = game.tick
                queue.best_distance = nil
                player.walking_state = {
                    walking = true,
                    direction = storage.utils.get_direction_with_diagonals(player.position, queue.current_target)
                }
            else
                -- Queue is empty, stop walking
                player.walking_state = {walking = false}
                queue.current_target = nil
                queue.stop_reason = "arrived"
            end
        else
            -- Update walking direction to current target
            player.walking_state = {
                walking = true,
                direction = storage.utils.get_direction_with_diagonals(player.position, queue.current_target)
            }
        end

        ::continue::
    end
end

storage.actions.clear_walking_queue = function(player_index)
    if storage.walking_queues and storage.walking_queues[player_index] then
        storage.walking_queues[player_index] = nil
    end
end

storage.actions.get_walking_queue_length = function(player_index)
    if storage.walking_queues and storage.walking_queues[player_index] then
        return #storage.walking_queues[player_index].positions
    end
    return 0
end
