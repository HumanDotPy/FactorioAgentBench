-- Mine or remove exactly one neutral obstacle at a position. Trees and rocks
-- with mineable products are mined with the same tick/production accounting as
-- harvest_resource; productless neutral stumps, corpses and rocks are
-- destroyed. Bounded to one entity within 1.5 tiles of the requested position.
local function calculate_mining_ticks(entity)
    local mining_time = entity.prototype.mineable_properties.mining_time or 1
    -- Convert mining time (in seconds) to ticks (60 ticks per second)
    return math.ceil(mining_time * 60)
end

local function update_production_stats(force, entity_name, amount)
    -- Factorio 2.0: production_statistics is now a method requiring surface parameter
    local surface = game.surfaces[1]
    local stats = force.get_item_production_statistics(surface)
    stats.on_flow(entity_name, amount)
    storage.harvested_items = storage.harvested_items or {}
    if storage.harvested_items[entity_name] then
        storage.harvested_items[entity_name] = storage.harvested_items[entity_name] + amount
    else
        storage.harvested_items[entity_name] = amount
    end
    storage.manual_production_events = storage.manual_production_events or {}
    table.insert(storage.manual_production_events, {
        tick = game.tick,
        kind = "harvested",
        outputs = {[entity_name] = amount},
    })
end

local function distance(pos1, pos2)
    local dx, dy = pos1.x - pos2.x, pos1.y - pos2.y
    return math.sqrt(dx * dx + dy * dy)
end

-- Neutral trees, rocks and stumps/corpses only. A player corpse or other
-- force-owned entity of the same type is never removed.
local function force_name(entity)
    local ok, force = pcall(function() return entity.force end)
    if not ok or force == nil then return nil end
    local ok_name, name = pcall(function() return force.name end)
    if ok_name and name ~= nil then return name end
    if type(force) == "string" then return force end
    return nil
end

storage.actions.mine_entity = function(player_index, x, y, entity_name)
    local player = storage.agent_characters[player_index]
    if not player then
        error("Player not found")
    end
    local surface = player.surface
    if not surface then
        error("Player has no surface")
    end

    local requested = {x = tonumber(x) or 0, y = tonumber(y) or 0}
    local candidates = surface.find_entities_filtered{
        position = requested,
        radius = 1.5,
        type = {"tree", "simple-entity", "corpse"},
        limit = 16,
    }

    local nearest = nil
    local named = nil
    local skipped = {}
    for _, entity in ipairs(candidates or {}) do
        if entity.valid and force_name(entity) == "neutral" then
            local entity_distance = distance(entity.position, requested)
            if nearest == nil or entity_distance < nearest.distance then
                nearest = {entity = entity, distance = entity_distance}
            end
            if entity_name ~= nil and entity.name == entity_name
                and (named == nil or entity_distance < named.distance) then
                named = {entity = entity, distance = entity_distance}
            end
        elseif entity.valid and #skipped < 4 then
            skipped[#skipped + 1] = tostring(entity.name)
        end
    end

    local target = nil
    local refusal = nil
    if entity_name ~= nil then
        target = named
        if target == nil then
            refusal = string.format(
                "No neutral %s within 1.5 tiles of (%.1f, %.1f); refusing to mine a different entity.",
                entity_name, requested.x, requested.y
            )
        end
    else
        target = nearest
        if target == nil then
            refusal = string.format(
                "Nothing neutral to mine at (%.1f, %.1f); no tree, rock, stump or corpse within 1.5 tiles.",
                requested.x, requested.y
            )
        end
    end
    if target == nil then
        local suffix = ""
        if #skipped > 0 then
            suffix = " Found only non-neutral entities ("
                .. table.concat(skipped, ", ") .. ")."
        end
        error(refusal .. suffix)
    end

    local entity = target.entity
    local reach = player.resource_reach_distance or 2.5
    local entity_distance = distance(entity.position, player.position)
    if entity_distance > reach then
        error(string.format(
            "Entity %s at (%.1f, %.1f) is %.1f tiles away; beyond your %.1f tile reach. Move closer with move_to first.",
            entity.name, entity.position.x, entity.position.y, entity_distance, reach
        ))
    end

    -- Capture identity before mutation: entity handles become invalid after
    -- mine/destroy and must not be read again.
    local resolved_name = entity.name
    local resolved_position = {x = entity.position.x, y = entity.position.y}

    local ok_minable, minable = pcall(function() return entity.minable end)
    local products = nil
    if ok_minable and minable then
        local ok_products, product_list = pcall(function()
            return entity.prototype.mineable_properties.products
        end)
        if ok_products and type(product_list) == "table" and #product_list > 0 then
            products = product_list
        end
    end

    local items = {}
    if products ~= nil then
        local main_inventory = player.get_main_inventory()
        local inserted_items = {}
        for _, product in pairs(products) do
            local amount = product.amount or 1
            if main_inventory and main_inventory.can_insert
                and not main_inventory.can_insert({name = product.name, count = amount}) then
                for _, undo in ipairs(inserted_items) do
                    player.remove_item{name = undo.name, count = undo.count}
                end
                error(string.format(
                    "Inventory is full; cannot mine %s (%s x%d). Free space or deliver items first.",
                    resolved_name, product.name, amount
                ))
            end
            local inserted = tonumber(player.insert({name = product.name, count = amount})) or 0
            if inserted < amount then
                for _, undo in ipairs(inserted_items) do
                    player.remove_item{name = undo.name, count = undo.count}
                end
                if inserted > 0 then
                    player.remove_item{name = product.name, count = inserted}
                end
                error(string.format(
                    "Inventory could only take %d of %d %s; nothing was mined.",
                    inserted, amount, product.name
                ))
            end
            table.insert(inserted_items, {name = product.name, count = inserted})
        end

        local charged_ticks = 0
        if storage.fast then
            charged_ticks = calculate_mining_ticks(entity)
            storage.elapsed_ticks = (storage.elapsed_ticks or 0) + charged_ticks
        end

        local ok_mine, mine_error = pcall(function()
            entity.mine({ignore_minable = false, raise_destroyed = true})
        end)
        if not ok_mine then
            for _, undo in ipairs(inserted_items) do
                player.remove_item{name = undo.name, count = undo.count}
            end
            if charged_ticks > 0 then
                storage.elapsed_ticks = (storage.elapsed_ticks or 0) - charged_ticks
            end
            error("Mining " .. resolved_name .. " failed; " .. tostring(mine_error))
        end

        for _, product in ipairs(inserted_items) do
            items[product.name] = (items[product.name] or 0) + product.count
            update_production_stats(player.force, product.name, product.count)
        end
    else
        local ok_destroyable, destroyable = pcall(function()
            return entity.can_be_destroyed()
        end)
        if not ok_destroyable or not destroyable then
            error(string.format(
                "%s at (%.1f, %.1f) has no mineable products and cannot be destroyed.",
                resolved_name, resolved_position.x, resolved_position.y
            ))
        end
        entity.destroy()
    end

    return {
        name = resolved_name,
        position = resolved_position,
        items = items,
        removed = true,
    }
end
