storage.actions.pickup_entity = function(player_index, x, y, entity, quality)
    -- Ensure we have a valid character, recreating if necessary
    local player = storage.utils.ensure_valid_character(player_index)
    local position = {x=x, y=y}
    local surface = player.surface
    local success = false
    rendering.draw_circle{only_in_alt_mode=true, width = 0.5, color = {r = 0, g = 1, b = 0}, surface = player.surface, radius = 0.25, filled = false, target = position, time_to_live = 12000}

    -- Debug print
    -- game.print("Starting pickup attempt for " .. entity .. " at (" .. x .. ", " .. y .. ")")

    -- Function to check if player can receive items
    local function can_receive_items(items_to_check)
        local main_inventory = player.get_main_inventory()
        -- Check each item individually
        for _, item in pairs(items_to_check) do
            if not main_inventory.can_insert({name = item.name, count = item.count}) then
                return false
            end
        end
        return true
    end

    local function destroy_and_verify(target)
        local ok = pcall(function()
            target.destroy{raise_destroy=false, do_cliff_correction=false}
        end)
        return ok and not target.valid
    end

    -- Function to pick up and add entity to player's inventory
    local function pickup_placed_entity(entities)
        for _, ent in pairs(entities) do
            if ent.valid and ent.name == entity then
                -- game.print("Found valid placed entity: " .. ent.name)

                -- Contract delivery chests and other protected entities must
                -- fail without changing inventory. Previously the tool added
                -- the entity and all of its contents before this check, so a
                -- rejected pickup duplicated items.
                if not ent.can_be_destroyed() then
                    error("Cannot pick up protected " .. ent.name)
                end

                -- Collect all items that need to be inserted
                local items_to_insert = {}

                -- Add entity products
                --local products = ent.prototype.mineable_properties.products
                --if products ~= nil then
                --    for _, product in pairs(products) do
                --        table.insert(items_to_insert, {name=product.name, count=product.amount})
                --    end
                --end

                -- Add all entity inventories if applicable. This covers chests,
                -- lab input, assembling machine input/output, furnace
                -- source/result/fuel, module slots and similar. Previously only
                -- chest contents were preserved, so picking up a lab destroyed
                -- its science packs.
                --
                -- Many names in ``defines.inventory`` alias the same numeric
                -- inventory id, and each ``get_inventory`` call returns a fresh
                -- handle, so dedupe on the id itself to avoid counting the same
                -- inventory (and duplicating its items) once per alias.
                local seen_inventory_ids = {}
                for _, inventory_id in pairs(defines.inventory) do
                    if type(inventory_id) == "number"
                        and not seen_inventory_ids[inventory_id] then
                        seen_inventory_ids[inventory_id] = true
                        local ok, inv = pcall(function() return ent.get_inventory(inventory_id) end)
                        if ok and inv then
                            local contents = storage.utils.get_contents_compat(inv)
                            for name, count in pairs(contents) do
                                table.insert(items_to_insert, {name=name, count=count})
                            end
                        end
                    end
                end

                -- Add transport belt contents if applicable
                if ent.type == "transport-belt" then
                    -- Check line 1
                    local line1 = ent.get_transport_line(1)
                    local contents1 = storage.utils.get_contents_compat(line1)
                    for name, count in pairs(contents1) do
                        table.insert(items_to_insert, {name=name, count=count})
                    end

                    -- Check line 2
                    local line2 = ent.get_transport_line(2)
                    local contents2 = storage.utils.get_contents_compat(line2)
                    for name, count in pairs(contents2) do
                        table.insert(items_to_insert, {name=name, count=count})
                    end
                end

                -- Add the entity itself
                table.insert(items_to_insert, {name=ent.name, count=1})

                -- Check if player can receive all items
                if not can_receive_items(items_to_insert) then
                    error("Inventory is full")
                end

                local inserted_items = {}
                for _, item in pairs(items_to_insert) do
                    local inserted = player.insert(item)
                    if inserted > 0 then
                        table.insert(inserted_items, {name=item.name, count=inserted})
                    end
                    if inserted < item.count then
                        for _, undo in ipairs(inserted_items) do
                            player.remove_item{name=undo.name, count=undo.count}
                        end
                        error("Inventory is full")
                    end
                end

                if not destroy_and_verify(ent) then
                    for _, undo in ipairs(inserted_items) do
                        player.remove_item{name=undo.name, count=undo.count}
                    end
                    error("Could not remove " .. ent.name .. "; nothing was picked up")
                end

                -- game.print("Picked up placed "..ent.name)
                local picked_up = {}
                for _, item in ipairs(inserted_items) do
                    picked_up[item.name] = (picked_up[item.name] or 0) + item.count
                end
                return {status = "completed", picked_up = picked_up, leftovers = {}}
            end
        end
        return false
    end

    local function set_ground_stack_count(item, stack_name, stack_quality, remaining)
        local ground_position = {x = item.position.x, y = item.position.y}
        local ok = pcall(function()
            item.stack.count = remaining
        end)
        if ok and item.valid and item.stack.count == remaining then
            return true, false
        end
        local ok_destroy = pcall(function()
            item.destroy{raise_destroy=false}
        end)
        if not ok_destroy or item.valid then
            return false, false
        end
        local created = surface.create_entity{
            name = "item-on-ground",
            position = ground_position,
            stack = {name = stack_name, count = remaining, quality = stack_quality},
        }
        return created ~= nil, true
    end

    local function pickup_ground_item(ground_items)
        local picked = 0
        local matched = 0
        local remove_failure = nil
        local leftovers = {}
        local lost = {}
        local picked_up = {}
        local stacks = {}
        for index = 1, #ground_items do
            stacks[index] = ground_items[index]
        end
        for _, item in ipairs(stacks) do
            local stack = item.valid and item.stack or nil
            if stack and stack.name then
                local stack_name = stack.name
                local stack_quality = nil
                if stack.quality ~= nil and stack.quality.name ~= nil then
                    stack_quality = stack.quality.name
                end
                local matches = entity == nil or stack_name == entity
                if matches and entity ~= nil and quality ~= nil then
                    matches = (stack_quality or "normal") == quality
                end
                if matches then
                    -- game.print("Found valid ground item: " .. stack_name)
                    matched = matched + 1
                    local item_position = {x=item.position.x, y=item.position.y}
                    local count = stack.count
                    local inserted = player.insert{
                        name=stack_name, count=count, quality=stack_quality}
                    if inserted > 0 then
                        picked = picked + inserted
                        picked_up[stack_name] = (picked_up[stack_name] or 0)
                            + inserted
                    end
                    local remaining = count - inserted
                    if remaining > 0 then
                        local recorded = inserted == 0
                        local item_gone = false
                        if not recorded then
                            recorded, item_gone = set_ground_stack_count(
                                item, stack_name, stack_quality, remaining)
                        end
                        if recorded then
                            table.insert(leftovers, {
                                name = stack_name,
                                count = remaining,
                                position = item_position,
                            })
                        elseif item_gone then
                            table.insert(lost, {
                                name = stack_name,
                                count = remaining,
                                position = item_position,
                            })
                        else
                            player.remove_item{
                                name=stack_name, count=inserted,
                                quality=stack_quality}
                            picked = picked - inserted
                            picked_up[stack_name] = picked_up[stack_name]
                                - inserted
                            table.insert(leftovers, {
                                name = stack_name,
                                count = count,
                                position = item_position,
                            })
                        end
                    elseif not destroy_and_verify(item) then
                        player.remove_item{
                            name=stack_name, count=inserted,
                            quality=stack_quality}
                        picked = picked - inserted
                        picked_up[stack_name] = picked_up[stack_name] - inserted
                        remove_failure = "Could not remove " .. stack_name
                            .. " at (" .. item_position.x .. ", " .. item_position.y
                            .. "); nothing was picked up"
                        table.insert(leftovers, {
                            name = stack_name,
                            count = count,
                            position = item_position,
                        })
                    end
                end
            end
        end
        if matched == 0 then
            return false
        end
        if picked <= 0 then
            if remove_failure then
                error(remove_failure)
            end
            local first = leftovers[1]
            error("Cannot pick up " .. (entity or (first and first.name) or "items")
                .. " - inventory is full (" .. (first and first.count or 0)
                .. " left on the ground)")
        end
        local requested = "all"
        if entity ~= nil then
            requested = {name = entity}
            if quality ~= nil then
                requested.quality = quality
            end
        end
        return {
            status = (#leftovers > 0 or #lost > 0) and "partial" or "completed",
            requested = requested,
            picked_up = picked_up,
            leftovers = leftovers,
            lost = lost,
        }
    end

    local player_entities = {}
    if entity ~= nil then
        player_entities = surface.find_entities_filtered{
            name=entity,
            position=position,
            radius=0.707,
            force="player"
        }
    end
    -- game.print("Found " .. #player_entities .. " placed entities")

    local ground_items = surface.find_entities_filtered{
        name="item-on-ground",
        position=position,
        radius=0.707
    }
    -- game.print("Found " .. #ground_items .. " ground items")

    -- Try to pick up placed entities first, if any exist
    if #player_entities > 0 then
        success = pickup_placed_entity(player_entities)
        if success then
            -- game.print("Successfully picked up placed entity")
            return success
        end
    end

    -- Only try ground items if we haven't succeeded with placed entities
    if not success and #ground_items > 0 then
        success = pickup_ground_item(ground_items)
        if success then
            -- game.print("Successfully picked up ground item")
            return success
        end
    end

    if not success then
        if entity == nil then
            error("No items on the ground at ("..x..", "..y..") to pick up.")
        end
        if #player_entities > 0 then
            error("Could not pick up "..entity)
        end
        if #ground_items > 0 then
            error("No ground stack matching '"..entity.."' at ("..x..", "..y..")")
        end
        error("Couldn't find "..entity.." at position ("..x..", "..y..") to pick up.")
    end

    return success
end
