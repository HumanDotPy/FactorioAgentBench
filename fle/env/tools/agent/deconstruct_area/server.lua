-- Bulk deconstruction of an axis-aligned rectangle, equivalent to dragging a
-- deconstruction planner over it. Player-force entities are removed and their
-- items returned to the character; neutral trees and rocks are included when
-- requested. Resources, ghosts, corpses, cliffs, dropped items and other
-- characters are never removed.
storage.actions.deconstruct_area = function(player_index, x1, y1, x2, y2, prototype, include_neutral, max_entities)
    local player = storage.agent_characters[player_index]
    if not player then
        return {error = "Player not found"}
    end
    local surface = player.surface
    if not surface then
        return {error = "Player has no surface"}
    end

    -- Defensive clamp; the Python client validates the same 1..2048 bounds.
    max_entities = math.min(math.max(tonumber(max_entities) or 512, 1), 2048)

    local x1n = tonumber(x1) or 0
    local y1n = tonumber(y1) or 0
    local x2n = tonumber(x2) or 0
    local y2n = tonumber(y2) or 0
    local left = math.min(x1n, x2n)
    local right = math.max(x1n, x2n)
    local top = math.min(y1n, y2n)
    local bottom = math.max(y1n, y2n)
    local query_area = {
        {math.floor(left), math.floor(top)},
        {math.floor(right) + 1, math.floor(bottom) + 1},
    }

    local skipped = {}
    local function skip(entity, reason)
        if #skipped < 32 then
            skipped[#skipped + 1] = {
                name = entity.name,
                position = {x = entity.position.x, y = entity.position.y},
                reason = reason,
            }
        end
    end

    -- Types that can never be deconstructed or yield items here. `item-entity`
    -- is the engine type of item-on-ground stacks in some Factorio versions.
    local blocked_types = {
        resource = "resource",
        ["entity-ghost"] = "ghost",
        character = "self",
        ["item-on-ground"] = "not_mineable",
        ["item-entity"] = "not_mineable",
        corpse = "not_mineable",
        cliff = "not_mineable",
    }

    local targets = {}
    local seen = {}
    local function consider(entity, kind)
        local key = entity.unit_number
        if key ~= nil then
            if seen[key] then
                return
            end
            seen[key] = true
        end
        -- Prototype mismatches are intentionally dropped, not reported.
        if prototype ~= nil and entity.name ~= prototype then
            return
        end
        local reason = blocked_types[entity.type]
        if reason ~= nil then
            skip(entity, reason)
            return
        end
        if kind == "neutral" then
            local ok, minable = pcall(function()
                return entity.minable
            end)
            if not ok or not minable then
                skip(entity, "not_mineable")
                return
            end
            local ok_products, products = pcall(function()
                return entity.prototype.mineable_properties.products
            end)
            if not ok_products or not products or #products == 0 then
                skip(entity, "not_mineable")
                return
            end
        end
        targets[#targets + 1] = {entity = entity, kind = kind}
    end

    -- Fetch one past the cap so an over-full rectangle can be reported as
    -- truncated. Player force and neutral queries are merged and deduplicated
    -- by unit_number.
    local query_limit = max_entities + 1
    local player_entities = surface.find_entities_filtered{
        area = query_area, force = player.force, limit = query_limit
    }
    for _, entity in ipairs(player_entities) do
        consider(entity, "player")
    end
    if include_neutral then
        local neutral_entities = surface.find_entities_filtered{
            area = query_area, force = "neutral", limit = query_limit
        }
        for _, entity in ipairs(neutral_entities) do
            consider(entity, "neutral")
        end
    end

    -- Sort by (y, x), then name/unit_number, so partial runs are reproducible.
    table.sort(targets, function(a, b)
        local pa, pb = a.entity.position, b.entity.position
        if pa.y ~= pb.y then
            return pa.y < pb.y
        end
        if pa.x ~= pb.x then
            return pa.x < pb.x
        end
        if a.entity.name ~= b.entity.name then
            return a.entity.name < b.entity.name
        end
        return (a.entity.unit_number or 0) < (b.entity.unit_number or 0)
    end)

    local requested = #targets
    local truncated = requested > max_entities
    local items_returned = {}
    local removed = 0
    local inventory_full = nil
    local status = "completed"
    local main_inventory = player.get_main_inventory()

    local function collect_items(entity, kind)
        local items = {}
        if kind == "neutral" then
            local products = entity.prototype.mineable_properties.products
            for _, product in pairs(products) do
                items[#items + 1] = {name = product.name, count = product.amount or 1}
            end
            return items
        end
        -- Player entities: every inventory, deduped on the numeric id because
        -- many defines.inventory names alias the same id.
        local seen_ids = {}
        for _, inventory_id in pairs(defines.inventory) do
            if type(inventory_id) == "number" and not seen_ids[inventory_id] then
                seen_ids[inventory_id] = true
                local ok, inv = pcall(function()
                    return entity.get_inventory(inventory_id)
                end)
                if ok and inv then
                    for name, count in pairs(storage.utils.get_contents_compat(inv)) do
                        items[#items + 1] = {name = name, count = count}
                    end
                end
            end
        end
        if entity.type == "transport-belt" then
            for line_index = 1, 2 do
                local ok, line = pcall(function()
                    return entity.get_transport_line(line_index)
                end)
                if ok and line then
                    for name, count in pairs(storage.utils.get_contents_compat(line)) do
                        items[#items + 1] = {name = name, count = count}
                    end
                end
            end
        end
        items[#items + 1] = {name = entity.name, count = 1}
        return items
    end

    for index = 1, math.min(#targets, max_entities) do
        local target = targets[index]
        local entity = target.entity
        if entity.valid then
            if not entity.can_be_destroyed() then
                skip(entity, "protected")
            else
                local items = collect_items(entity, target.kind)
                local full = nil
                for _, item in ipairs(items) do
                    if not main_inventory.can_insert({name = item.name, count = item.count}) then
                        full = item
                        break
                    end
                end
                if full then
                    status = "inventory_full"
                    inventory_full = {
                        name = full.name,
                        position = {x = entity.position.x, y = entity.position.y},
                    }
                    break
                end
                for _, item in ipairs(items) do
                    player.insert(item)
                    items_returned[item.name] = (items_returned[item.name] or 0) + item.count
                end
                pcall(function()
                    entity.destroy{raise_destroy=false, do_cliff_correction=false}
                end)
                removed = removed + 1
            end
        end
    end

    return {
        status = status,
        area = {
            left = math.floor(left),
            top = math.floor(top),
            right = math.floor(right),
            bottom = math.floor(bottom),
        },
        removed = removed,
        requested = requested,
        items_returned = items_returned,
        skipped = skipped,
        truncated = truncated,
        inventory_full = inventory_full,
        tick = game.tick,
    }
end
