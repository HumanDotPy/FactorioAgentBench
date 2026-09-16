storage.actions.get_entity = function(player_index, entity, x, y)
    -- Ensure we have a valid character, recreating if necessary
    local player = storage.utils.ensure_valid_character(player_index)
    local position = {x=x, y=y}

    if prototypes.entity[entity] == nil then
        local name = entity:gsub(" ", "_"):gsub("-", "_")
        error(name .. " isnt something that exists. Did you make a typo? ")
    end

    local prototype = prototypes.entity[entity]
    local width = prototype.tile_width or 1
    local height = prototype.tile_height or 1
    if not prototype.tile_width or not prototype.tile_height then
        local collision_box = prototype.collision_box
        if collision_box and collision_box.left_top and collision_box.right_bottom then
            width = math.max(collision_box.right_bottom.x - collision_box.left_top.x, 1)
            height = math.max(collision_box.right_bottom.y - collision_box.left_top.y, 1)
        end
    end

    local epsilon = 0.01
    local target_area = {
        {position.x - width / 2 - epsilon, position.y - height / 2 - epsilon},
        {position.x + width / 2 + epsilon, position.y + height / 2 + epsilon}
    }
    local entities = player.surface.find_entities_filtered{area = target_area, name = entity}

    local function contains(box, px, py)
        return box and box.left_top and box.right_bottom
            and px >= box.left_top.x and px <= box.right_bottom.x
            and py >= box.left_top.y and py <= box.right_bottom.y
    end

    local closest_distance = math.huge
    local closest_entity = nil
    local containing_distance = math.huge
    local containing_entity = nil

    for _, building in ipairs(entities) do
        if building.name ~= 'character' then
            local ok_box, box = pcall(function() return building.bounding_box end)
            if not ok_box then box = nil end
            local distance = ((position.x - building.position.x) ^ 2 +
                            (position.y - building.position.y) ^ 2) ^ 0.5
            if contains(box, position.x, position.y) and distance < containing_distance then
                containing_distance = distance
                containing_entity = building
            end
            if distance < closest_distance then
                closest_distance = distance
                closest_entity = building
            end
        end
    end

    local chosen = containing_entity or closest_entity

    if chosen ~= nil then
        local serialized = storage.utils.serialize_entity(chosen)
        --local entity_json = game.table_to_json(serialized)-- game.table_to_json(entity
        return serialized
    else
        error("\"No entity of type " .. entity .. " found at the specified position.\"")
    end
end
