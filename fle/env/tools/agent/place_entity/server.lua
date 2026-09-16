local function pe_accepts_items(entity)
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

local function pe_attach_drop_report(serialized, built)
    if not built.drop_position then
        return serialized
    end
    local drop = built.drop_position
    local catch = {x = math.floor(drop.x) + 0.5, y = math.floor(drop.y) + 0.5}
    local entities = {}
    local ground_by_item = {}
    local ground_items = 0
    for _, candidate in ipairs(built.surface.find_entities_filtered{
        position = catch, radius = 0.5}) do
        if candidate.valid and candidate ~= built then
            if candidate.type == "item-entity" then
                local stack = candidate.stack
                local name = stack and stack.name or candidate.name
                local count = stack and stack.count or 1
                ground_items = ground_items + count
                ground_by_item[name] = (ground_by_item[name] or 0) + count
            else
                entities[#entities + 1] = {
                    name = candidate.name,
                    type = candidate.type,
                    position = {x = candidate.position.x, y = candidate.position.y},
                    entity_id = candidate.unit_number,
                    input_inventory = pe_accepts_items(candidate),
                }
            end
        end
    end
    serialized.drop_report = {
        drop = {x = drop.x, y = drop.y},
        catch = catch,
        entities = entities,
        ground_items = ground_items,
        ground_by_item = ground_by_item,
    }
    return serialized
end

local function pe_drop_tile_hint(surface, footprint, position)
    if not footprint or not footprint.left_top or not footprint.right_bottom then
        return nil
    end
    local left = footprint.left_top.x
    local top = footprint.left_top.y
    local right = footprint.right_bottom.x
    local bottom = footprint.right_bottom.y
    local left_tile = math.floor(left)
    local top_tile = math.floor(top)
    local right_tile = math.ceil(right) - 1
    local bottom_tile = math.ceil(bottom) - 1
    local hints = {}
    for _, entity in ipairs(surface.find_entities_filtered{
        area = {{left - 1, top - 1}, {right + 1, bottom + 1}}, limit = 32}) do
        if entity.valid and entity.drop_position then
            local drop = entity.drop_position
            local tile = {x = math.floor(drop.x) + 0.5, y = math.floor(drop.y) + 0.5}
            local drop_tile_x = math.floor(drop.x)
            local drop_tile_y = math.floor(drop.y)
            if drop_tile_x >= left_tile and drop_tile_x <= right_tile
                and drop_tile_y >= top_tile and drop_tile_y <= bottom_tile then
                hints[#hints + 1] = {
                    name = entity.name,
                    position = {x = entity.position.x, y = entity.position.y},
                    drop_position = {x = drop.x, y = drop.y},
                    catch_tile = tile,
                    entity_id = entity.unit_number,
                }
            end
        end
    end
    table.sort(hints, function(a, b)
        local da, db = 0, 0
        if position then
            local ax, ay = a.position.x - position.x, a.position.y - position.y
            local bx, by = b.position.x - position.x, b.position.y - position.y
            da = ax * ax + ay * ay
            db = bx * bx + by * by
        end
        if da ~= db then
            return da < db
        end
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
    local hint = hints[1]
    if hint then
        hint.message = hint.name .. " at (" .. hint.position.x .. ", "
            .. hint.position.y .. ") outputs to (" .. hint.catch_tile.x .. ", "
            .. hint.catch_tile.y
            .. "); the rejected footprint covers another machine's output tile, so the engine refuses the build"
    end
    return hint
end

local function character_only_blocker(diagnostic, player)
    local blocked = diagnostic and diagnostic.blocked_by
    if not blocked or blocked.prototype ~= "character" then
        return false
    end
    if player and player.unit_number and blocked.entity_id
        and blocked.entity_id ~= player.unit_number then
        return false
    end
    if #(diagnostic.colliding_tiles or {}) > 0 then
        return false
    end
    for _, other in ipairs(diagnostic.overlapping_entities or {}) do
        if other.prototype ~= "character" then
            return false
        end
    end
    return true
end

storage.actions.place_entity = function(player_index, entity, direction, x, y, exact)
    -- Ensure we have a valid character, recreating if necessary
    local player = storage.utils.ensure_valid_character(player_index)
    local position = {x = x, y = y}

    if not direction then
        direction = 0
    end

    local entity_direction = storage.utils.inserter_engine_direction(entity,
        storage.utils.get_entity_direction(entity, direction))

    -- Common validation functions
    local function validate_distance()
        local max_distance = player.reach_distance or player.build_distance
        local dx = player.position.x - x
        local dy = player.position.y - y or 0
        local distance = math.sqrt(dx * dx + dy * dy)

        if distance > max_distance then
            error("\"The target position is too far away to place the entity. The player position is " ..
                  player.position.x .. ", " .. player.position.y ..
                  " and the target position is " .. x .. ", " .. y ..
                  ". The distance is " .. string.format("%.2f", distance) ..
                  " and the max distance is " .. max_distance .. ". Move closer.\"")
        end
    end

    local function validate_entity()
        if prototypes.entity[entity] == nil then
            local name = entity:gsub(" ", "_"):gsub("-", "_")
            error("\""..name .. " isn't something that exists. Did you make a typo?\"")
        end
    end

    local function validate_inventory()
        local count = player.get_item_count(entity)
        if count == 0 then
            local name = entity:gsub(" ", "_"):gsub("-", "_")
            local inv_contents = storage.utils.format_inventory_for_error(player)
            error("\"No " .. name .. " in inventory. Current inventory: " .. inv_contents .. "\"")
        end
    end

    -- Explicit planner-assisted ablation only; canonical callers require exact.
    local function assisted_place()
        local chosen = position
        if not storage.utils.can_place_entity(player, entity, chosen, entity_direction) then
            chosen = nil
            if entity == "offshore-pump" then
                local finder = storage.utils.find_offshore_pump_position
                if finder then
                    local found = finder(player, position, entity_direction)
                    if found then chosen = found.position; entity_direction = found.direction end
                end
            else
                for radius=1,10 do
                    for dx=-radius,radius do
                        for dy=-radius,radius do
                            if math.abs(dx)==radius or math.abs(dy)==radius then
                                local candidate = {x=x+dx,y=y+dy}
                                if storage.utils.can_place_entity(player,entity,candidate,entity_direction) then
                                    chosen = candidate; break
                                end
                            end
                        end
                        if chosen then break end
                    end
                    if chosen then break end
                end
            end
        end
        if not chosen then error("No suitable assisted placement near requested position") end
        local built = player.surface.create_entity{name=entity,position=chosen,
            direction=entity_direction,force=player.force,raise_built=true}
        if not built then error("Assisted placement rejected by engine") end
        player.remove_item{name=entity,count=1}
        local serialized = pe_attach_drop_report(storage.utils.serialize_entity(built), built)
        serialized = storage.utils.inserter_direction_report(serialized, direction)
        return storage.utils.attach_connection_report(serialized, built, player)
    end

    -- Main execution flow
    validate_distance()
    validate_entity()
    validate_inventory()
    if exact then
        local prototype = prototypes.entity[entity]
        local function placement_diagnostics()
            return storage.utils.spatial_diagnostics(player.surface, position,
                prototype.collision_box, entity_direction,
                prototype.collision_mask, nil, prototype)
        end
        local character_moved = false
        if not storage.utils.can_place_entity(player, entity, position, entity_direction) then
            local diagnostic = placement_diagnostics()
            if character_only_blocker(diagnostic, player) then
                local stepped = storage.utils.escape_character_to_free_tile(
                    player, diagnostic.footprint, position, nil)
                if stepped then
                    if storage.utils.can_place_entity(player, entity, position, entity_direction) then
                        character_moved = true
                    else
                        diagnostic = placement_diagnostics()
                    end
                end
            end
            if not character_moved then
                return {error=true, reason="placement_rejected", prototype=entity,
                    position=position, direction=direction,
                    engine_direction=entity_direction, diagnostics=diagnostic,
                    drop_tile_hint=pe_drop_tile_hint(player.surface,
                        diagnostic.footprint, position)}
            end
        end
        local built
        for _, ghost in ipairs(player.surface.find_entities_filtered{
            type="entity-ghost", ghost_name=entity, position=position, force=player.force}) do
            if ghost.position.x == position.x and ghost.position.y == position.y
                and ghost.direction == entity_direction and ghost.quality.name == "normal" then
                -- Manual construction over a matching blueprint ghost preserves
                -- recipes, circuits, schedules and item-request proxies natively.
                local _, revived = ghost.revive{raise_revive=true}
                built = revived
                break
            end
        end
        if not built then
            built = player.surface.create_entity{name=entity, position=position,
                direction=entity_direction, force=player.force, raise_built=true}
        end
        if not built then
            return {error=true,reason="creation_rejected",prototype=entity,position=position,
                direction=direction, engine_direction=entity_direction}
        end
        player.remove_item{name=entity,count=1}
        local serialized = storage.utils.serialize_entity(built)
        if character_moved then
            serialized.recovered = "character_moved"
            serialized.character_position = {x=player.position.x, y=player.position.y}
        end
        serialized = pe_attach_drop_report(serialized, built)
        serialized = storage.utils.inserter_direction_report(serialized, direction)
        return storage.utils.attach_connection_report(serialized, built, player)
    end

    -- Placement itself is a single player action. Travel time is paid by the
    -- semantic controller before this call; do not schedule an artificial
    -- one-second delay that can overwrite another on_nth_tick handler.
    return assisted_place()
end
