local function describe_snap(entity)
    local width, height
    local ok_box, box = pcall(function() return entity.bounding_box end)
    if ok_box and box and box.left_top and box.right_bottom then
        width = box.right_bottom.x - box.left_top.x
        height = box.right_bottom.y - box.left_top.y
    end
    if not width or width <= 0 or not height or height <= 0 then
        local ok_proto, prototype = pcall(function() return entity.prototype end)
        if ok_proto and prototype then
            if not width or width <= 0 then
                width = prototype.tile_width or prototype.size
            end
            if not height or height <= 0 then
                height = prototype.tile_height or prototype.size
            end
        end
    end
    local px = tonumber(entity.position.x) or 0
    local py = tonumber(entity.position.y) or 0
    return {
        tile_size = {width = width, height = height},
        snapped_center = {x = math.floor(px) + 0.5, y = math.floor(py) + 0.5},
        center_parity = {
            x = math.abs(math.floor(px * 2 + 0.5) % 2),
            y = math.abs(math.floor(py * 2 + 0.5) % 2),
        },
    }
end

local function is_item_entity(entity)
    return entity.type == "item-entity" or entity.type == "item-on-ground"
end

storage.actions.get_entities = function(player_index, radius, entity_names_json, position_x, position_y)
    local player = storage.utils.ensure_valid_character(player_index)

    local position
    if position_x and position_y then
        position = {x = tonumber(position_x), y = tonumber(position_y)}
    else
        position = player.position
    end

    radius = tonumber(radius) or 5
    local entity_names = helpers.json_to_table(entity_names_json) or {}
    local area = {
        {position.x - radius, position.y - radius},
        {position.x + radius, position.y + radius}
    }

    local query = {area = area}
    if entity_names and #entity_names > 0 then
        query.name = entity_names
    end
    local entities = player.surface.find_entities_filtered(query)

    local result = {}
    local characters_skipped = 0
    local other_forces = 0
    local skipped = 0
    local other_force_names = {}

    for _, entity in ipairs(entities) do
        if not entity.valid then
            skipped = skipped + 1
        else
            local ok_force, force = pcall(function() return entity.force end)
            if not ok_force then
                skipped = skipped + 1
            elseif force ~= player.force then
                other_forces = other_forces + 1
                local name = force and force.name or "unknown"
                other_force_names[name] = true
            elseif entity.name == 'character' then
                characters_skipped = characters_skipped + 1
            elseif is_item_entity(entity) then
            else
                local ok, serialized = pcall(function()
                    return storage.utils.serialize_entity(entity)
                end)
                if ok and serialized then
                    local snap = describe_snap(entity)
                    serialized.tile_size = snap.tile_size
                    serialized.snapped_center = snap.snapped_center
                    serialized.center_parity = snap.center_parity
                    table.insert(result, serialized)
                else
                    skipped = skipped + 1
                end
            end
        end
    end

    local ground_items = {}
    local ground_item_totals = {}
    local ground_item_stacks = 0
    local ok_ground, ground_entities = pcall(function()
        return player.surface.find_entities_filtered({area = area, type = "item-entity"})
    end)
    if ok_ground and ground_entities then
        for _, item in pairs(ground_entities) do
            if item.valid ~= false then
                local ok_stack, stack = pcall(function() return item.stack end)
                if ok_stack and stack and stack.valid_for_read then
                    ground_item_stacks = ground_item_stacks + 1
                    ground_item_totals[stack.name] =
                        (ground_item_totals[stack.name] or 0) + stack.count
                    if #ground_items < 32 then
                        ground_items[#ground_items + 1] = {
                            name = stack.name,
                            count = stack.count,
                            position = {x = item.position.x, y = item.position.y},
                        }
                    end
                end
            end
        end
        table.sort(ground_items, function(a, b)
            if a.position.y ~= b.position.y then
                return a.position.y < b.position.y
            end
            if a.position.x ~= b.position.x then
                return a.position.x < b.position.x
            end
            return a.name < b.name
        end)
    end

    local force_list = {}
    for name in pairs(other_force_names) do
        force_list[#force_list + 1] = name
    end
    table.sort(force_list)

    return {
        entities = result,
        ground_items = ground_items,
        ground_item_totals = ground_item_totals,
        ground_item_stacks = ground_item_stacks,
        ground_items_truncated = ground_item_stacks > #ground_items,
        other_forces = other_forces,
        other_force_names = force_list,
        characters_skipped = characters_skipped,
        skipped = skipped,
    }
end
