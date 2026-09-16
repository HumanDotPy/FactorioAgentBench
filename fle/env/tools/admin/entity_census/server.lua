-- Lightweight entity census: name -> {status -> count} for the player
-- force, without serializing full entity attributes. Used by the verifier's
-- per-intervention telemetry when no objective needs entity details.

local ENTITY_STATUS_NAMES = nil

local function entity_status_name(entity_status)
    if ENTITY_STATUS_NAMES == nil then
        ENTITY_STATUS_NAMES = {}
        for name, value in pairs(defines.entity_status or {}) do
            ENTITY_STATUS_NAMES[value] = name
        end
    end
    if entity_status == nil then
        return "unknown"
    end
    return ENTITY_STATUS_NAMES[entity_status] or "unknown"
end

local BUFFER_FULL = {
    waiting_for_space_in_destination = true,
    waiting_for_space_in_output = true,
    full_output = true,
    output_full = true,
}

local SOURCE_STARVED = {
    waiting_for_source_items = true,
    waiting_for_more_items = true,
    item_ingredient_shortage = true,
    fluid_ingredient_shortage = true,
    no_ingredients = true,
}

local function entity_at(surface, position)
    if not position then
        return nil
    end
    local ok, found = pcall(function()
        return surface.find_entities_filtered{
            position = {x = position.x, y = position.y},
            radius = 0.5,
            limit = 4,
        }
    end)
    if not ok or not found then
        return nil
    end
    for _, other in pairs(found) do
        if other.valid ~= false and other.name ~= "character"
            and other.type ~= "item-entity" and other.type ~= "item-on-ground" then
            return other
        end
    end
    return nil
end

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

local function product_of(entity)
    local ok, recipe = pcall(function()
        if entity.get_recipe then
            return entity.get_recipe()
        end
        return nil
    end)
    if ok and recipe and recipe.products and recipe.products[1] then
        return recipe.products[1].name
    end
    if entity.type == "mining-drill" then
        local ok_res, resources = pcall(function()
            return entity.surface.find_entities_filtered{
                area = entity.bounding_box,
                type = "resource",
                limit = 4,
            }
        end)
        if ok_res and resources then
            local best, best_amount = nil, -1
            for _, resource in pairs(resources) do
                local amount = resource.amount or 0
                if amount > best_amount then
                    best, best_amount = resource.name, amount
                end
            end
            if best then
                return best
            end
        end
    end
    return nil
end

local function inventory_of(entity)
    for _, key in ipairs({"crafter_input", "furnace_source", "chest", "fuel"}) do
        if defines and defines.inventory and defines.inventory[key] then
            local ok, inventory = pcall(function()
                return entity.get_inventory(defines.inventory[key])
            end)
            if ok and inventory then
                local contents = storage.utils.get_contents_compat(inventory)
                if contents and next(contents) ~= nil then
                    return contents
                end
            end
        end
    end
    return {}
end

storage.actions.entity_census = function(player_index)
    local character = storage.agent_characters[player_index]
    if not character or not character.valid then
        return {census = {}, total = 0}
    end
    local force = character.force
    local surface = character.surface
    local entities = surface.find_entities_filtered({force = force})
    local census = {}
    local total = 0
    local stalls = {
        by_status = {},
        by_product = {},
        by_name = {},
        buffer_full = 0,
        detail = {},
    }
    local ground_items = {}
    local ground_item_stacks = 0
    local ground_item_positions = {}
    local missing_drop_targets = {}
    local missing_drop_target_count = 0
    local missing_drop_target_keys = {}
    for _, entity in pairs(entities) do
        if entity.valid then
            if storage.utils.track_public_status then
                storage.utils.track_public_status(entity)
            end
            local name = entity.name
            local status_name = entity_status_name(entity.status)
            census[name] = census[name] or {}
            census[name][status_name] = (census[name][status_name] or 0) + 1
            total = total + 1

            local snap = describe_snap(entity)
            if entity.type == "item-entity" or entity.type == "item-on-ground" then
                local stack = entity.stack
                if stack and stack.valid_for_read then
                    ground_item_stacks = ground_item_stacks + 1
                    ground_items[stack.name] = (ground_items[stack.name] or 0)
                        + stack.count
                    if #ground_item_positions < 32 then
                        ground_item_positions[#ground_item_positions + 1] = {
                            name = stack.name,
                            count = stack.count,
                            position = {
                                x = entity.position.x,
                                y = entity.position.y,
                            },
                        }
                    end
                end
            else
                local ok_drop, drop_position = pcall(function()
                    return entity.drop_position
                end)
                if ok_drop and drop_position then
                    local drop_target = entity_at(surface, drop_position)
                    if drop_target == nil then
                        local key = name .. "|" .. tostring(entity.position.x)
                            .. "|" .. tostring(entity.position.y)
                            .. "|" .. tostring(drop_position.x)
                            .. "|" .. tostring(drop_position.y)
                        if not missing_drop_target_keys[key] then
                            missing_drop_target_keys[key] = true
                            missing_drop_target_count = missing_drop_target_count + 1
                            if #missing_drop_targets < 32 then
                                missing_drop_targets[#missing_drop_targets + 1] = {
                                    name = name,
                                    type = entity.type,
                                    entity_id = entity.unit_number,
                                    position = {
                                        x = entity.position.x,
                                        y = entity.position.y,
                                    },
                                    drop_position = {
                                        x = drop_position.x,
                                        y = drop_position.y,
                                    },
                                    tile_size = snap.tile_size,
                                    snapped_center = snap.snapped_center,
                                    center_parity = snap.center_parity,
                                }
                            end
                        end
                    end
                end

                if BUFFER_FULL[status_name] or SOURCE_STARVED[status_name] then
                    stalls.by_status[status_name] =
                        (stalls.by_status[status_name] or 0) + 1
                    stalls.by_name[name] = stalls.by_name[name] or {}
                    stalls.by_name[name][status_name] =
                        (stalls.by_name[name][status_name] or 0) + 1
                    if BUFFER_FULL[status_name] then
                        stalls.buffer_full = stalls.buffer_full + 1
                    end
                    local product = product_of(entity)
                    if product then
                        stalls.by_product[product] =
                            (stalls.by_product[product] or 0) + 1
                    end
                    if #stalls.detail < 32 then
                        local detail = {
                            name = name,
                            type = entity.type,
                            entity_id = entity.unit_number,
                            status = status_name,
                            product = product,
                            position = {
                                x = entity.position.x,
                                y = entity.position.y,
                            },
                            tile_size = snap.tile_size,
                            snapped_center = snap.snapped_center,
                            center_parity = snap.center_parity,
                        }
                        if ok_drop and drop_position then
                            detail.drop_position = {
                                x = drop_position.x,
                                y = drop_position.y,
                            }
                            local drop_target = entity_at(surface, drop_position)
                            detail.drop_target = drop_target and drop_target.name or nil
                            if detail.drop_target == nil then
                                detail.drop_empty = true
                            end
                        end
                        if entity.type == "inserter" and SOURCE_STARVED[status_name] then
                            if entity.pickup_position then
                                detail.pickup_position = {
                                    x = entity.pickup_position.x,
                                    y = entity.pickup_position.y,
                                }
                                local pickup_target =
                                    entity_at(surface, entity.pickup_position)
                                detail.pickup_target = pickup_target
                                    and pickup_target.name or nil
                                detail.source_inventory = pickup_target
                                    and inventory_of(pickup_target) or {}
                            end
                        end
                        stalls.detail[#stalls.detail + 1] = detail
                    end
                end
            end
        end
    end
    return {
        census = census,
        total = total,
        stalls = stalls,
        ground_items = ground_items,
        ground_item_stacks = ground_item_stacks,
        ground_item_positions = ground_item_positions,
        ground_items_truncated = ground_item_stacks > #ground_item_positions,
        missing_drop_targets = missing_drop_targets,
        missing_drop_target_count = missing_drop_target_count,
    }
end
