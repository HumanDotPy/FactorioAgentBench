local function calculate_position(direction, ref_pos, ref_entity, gap, entity_to_place)
    local new_pos = {x = ref_pos.x, y = ref_pos.y}
    local effective_gap = gap or 0

    local ref_width, ref_height
    if ref_entity then
        if ref_entity.type == "inserter" then
            ref_width, ref_height = 1, 1
        else
            local ref_orientation = ref_entity.direction
            if ref_orientation == defines.direction.east or ref_orientation == defines.direction.west then
                ref_width = ref_entity.prototype.tile_height
                ref_height = ref_entity.prototype.tile_width
            else
                ref_width = ref_entity.prototype.tile_width
                ref_height = ref_entity.prototype.tile_height
            end
        end
    else
        ref_width = 1
        ref_height = 1
    end

    local entity_prototype = prototypes.entity[entity_to_place]
    local entity_width, entity_height
    if direction == 1 or direction == 3 then
        entity_width = entity_prototype.tile_height
        entity_height = entity_prototype.tile_width
    else
        entity_width = entity_prototype.tile_width
        entity_height = entity_prototype.tile_height
    end

    if direction == 0 then
        new_pos.y = new_pos.y - (math.ceil(ref_height + entity_height) / 2 + effective_gap)
    elseif direction == 1 then
        new_pos.x = new_pos.x + (math.ceil(ref_width + entity_width) / 2 + effective_gap)
    elseif direction == 2 then
        new_pos.y = new_pos.y + (math.ceil(ref_height + entity_height) / 2 + effective_gap)
    else
        new_pos.x = new_pos.x - (math.ceil(ref_width + entity_width) / 2 + effective_gap)
    end

    new_pos.x = math.ceil(new_pos.x * 2) / 2
    new_pos.y = math.ceil(new_pos.y * 2) / 2

    return new_pos
end

local function validate_mining_drill_placement(surface, position, prototype)
    if prototype.type ~= "mining-drill" then
        return true
    end

    local radius = 2.5
    local radius_ok, prototype_radius = pcall(function()
        return prototype.mining_drill_radius
    end)
    if radius_ok and prototype_radius then
        radius = prototype_radius
    end
    local area = {
        {position.x - radius, position.y - radius},
        {position.x + radius, position.y + radius}
    }

    local resources = surface.find_entities_filtered({
        area = area,
        type = "resource"
    })

    return #resources > 0
end

local function rotated_footprint(position, box, direction)
    local angle = (direction or 0) * math.pi / 8
    local c, s = math.cos(angle), math.sin(angle)
    local left, top, right, bottom = math.huge, math.huge, -math.huge, -math.huge
    for _, x in ipairs({box.left_top.x, box.right_bottom.x}) do
        for _, y in ipairs({box.left_top.y, box.right_bottom.y}) do
            local rx, ry = position.x + x * c - y * s, position.y + x * s + y * c
            left, top = math.min(left, rx), math.min(top, ry)
            right, bottom = math.max(right, rx), math.max(bottom, ry)
        end
    end
    return {left_top = {x = left, y = top}, right_bottom = {x = right, y = bottom}}
end

storage.actions.place_entity_next_to = function(player_index, entity, ref_x, ref_y, direction, gap)
    local player = storage.utils.ensure_valid_character(player_index)
    local ref_position = {x = ref_x, y = ref_y}
    local surface = player.surface

    local function table_contains(tbl, element)
        for _, value in ipairs(tbl) do
            if value == element then
                return true
            end
        end
        return false
    end

    local valid_directions = {0, 4, 8, 12}

    if not table_contains(valid_directions, direction) then
        error("Invalid direction " .. direction .. " provided. Please use 0 (north), 4 (east), 8 (south), or 12 (west).")
    end

    local prototype = prototypes.entity[entity]
    if prototype == nil then
        local name = entity:gsub(" ", "_"):gsub("-", "_")
        error(name .. " isn't a valid entity prototype. Did you make a typo?")
    end

    local inventory = player.get_main_inventory()
    if not inventory or inventory.get_item_count(entity) < 1 then
        local inv_contents = storage.utils.format_inventory_for_error(player)
        error("Not enough " .. entity .. " in inventory. Current inventory: " .. inv_contents)
    end

    local internal_direction = direction / 4

    local ref_entities = surface.find_entities_filtered({
        area = {{ref_x - 0.5, ref_y - 0.5}, {ref_x + 0.5, ref_y + 0.5}},
        type = {"character", "resource"},
        invert = true
    })
    local ref_entity = #ref_entities > 0 and ref_entities[1] or nil

    local new_position = calculate_position(internal_direction, ref_position, ref_entity, gap, entity)
    local orientation = storage.utils.inserter_engine_direction(entity,
        storage.utils.get_entity_direction(entity, direction))

    local can_build = storage.utils.can_place_entity(player, entity, new_position, orientation)
    local character_moved = false

    if not can_build then
        local diagnostic = nil
        if storage.utils.spatial_diagnostics then
            diagnostic = storage.utils.spatial_diagnostics(
                surface, new_position, prototype.collision_box, orientation,
                prototype.collision_mask, nil, prototype)
        end

        local footprint = diagnostic and diagnostic.footprint
            or rotated_footprint(new_position, prototype.collision_box, orientation)

        local character_blocking = false
        if diagnostic then
            for _, entry in ipairs(diagnostic.overlapping_entities or {}) do
                if entry.type == "character" and entry.entity_id ~= nil
                    and entry.entity_id == player.unit_number then
                    character_blocking = true
                end
            end
        else
            for _, entity in ipairs(surface.find_entities_filtered({
                area = footprint,
                type = "character"
            })) do
                if entity.unit_number ~= nil and entity.unit_number == player.unit_number then
                    character_blocking = true
                end
            end
        end

        if character_blocking then
            local escaped = storage.utils.escape_character_to_free_tile(
                player, footprint, new_position, nil)
            if escaped and storage.utils.can_place_entity(player, entity, new_position, orientation) then
                can_build = true
                character_moved = true
            end
        end

        if not can_build then
            return {
                error = true,
                reason = "placement_rejected",
                prototype = entity,
                position = new_position,
                direction = direction,
                diagnostics = diagnostic,
            }
        end
    end

    if not validate_mining_drill_placement(surface, new_position, prototype) then
        return {
            error = true,
            reason = "no_minable_resources",
            prototype = entity,
            position = new_position,
            direction = direction,
        }
    end

    local new_entity = surface.create_entity({
        name = entity,
        position = new_position,
        force = player.force,
        direction = orientation,
        move_stuck_players = true,
    })

    if not new_entity then
        return {
            error = true,
            reason = "creation_rejected",
            prototype = entity,
            position = new_position,
            direction = direction,
        }
    end

    local removed = inventory.remove({name = entity, count = 1})
    if removed ~= 1 then
        new_entity.destroy()
        return {
            error = true,
            reason = "inventory_removal_failed",
            prototype = entity,
            position = new_position,
            direction = direction,
        }
    end

    local serialized = storage.utils.serialize_entity(new_entity)
    serialized = storage.utils.inserter_direction_report(serialized, direction)
    serialized.placement_feedback = {
        reason = character_moved
            and "the agent character occupied the requested tile and stepped aside; the entity was placed at the requested position and direction"
            or "the entity was placed at the requested position and direction",
        optimal = not character_moved,
        auto_oriented = false,
    }
    return storage.utils.attach_connection_report(serialized, new_entity, player)
end
