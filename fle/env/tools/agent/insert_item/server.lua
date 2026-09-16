-- Function to check if an item is a module
local function is_module(item_name)
    local item_proto = prototypes.item[item_name]
    return item_proto and item_proto.type == "module"
end

local smelting_ingredients = nil

local function is_smelting_ingredient(item_name)
    if not smelting_ingredients then
        smelting_ingredients = {}
        for _, recipe in pairs(prototypes.recipe) do
            if recipe.category == "smelting" then
                for _, ingredient in pairs(recipe.ingredients) do
                    smelting_ingredients[ingredient.name] = true
                end
            end
        end
    end
    return smelting_ingredients[item_name] == true
end

-- Function to get inventory fullness information
local function get_inventory_info(entity)
    if entity.get_inventory then
        -- Try common inventory types (Factorio 2.0: unified crafter_input for furnaces/assemblers)
        local inv = entity.get_inventory(defines.inventory.chest) or          -- For chests
                   entity.get_inventory(defines.inventory.crafter_input)      -- For furnaces, assemblers, rocket silos

        if inv then
            -- Get actual item count and inventory capacity
            local item_count = 0
            for i = 1, #inv do
                local stack = inv[i]
                if stack and stack.valid_for_read then
                    item_count = item_count + stack.count
                end
            end

            -- Calculate total capacity (slots * stack size)
            local first_slot = inv[1]
            local sample_name = (first_slot and first_slot.name) or "iron-plate"
            local sample_prototype = prototypes.item[sample_name]
            local stack_size = (sample_prototype and sample_prototype.stack_size) or 1
            local capacity = #inv * stack_size

            return string.format("(%d/%d items)", item_count, capacity)
        end
    end
    return ""
end

local function item_stack_size(item_name)
    local item_prototype = prototypes.item[item_name]
    return (item_prototype and item_prototype.stack_size) or 1
end

local function inventory_remaining_capacity(inventory, item_name)
    if not inventory then
        return nil
    end
    local slot_count = #inventory
    if slot_count == 0 then
        return nil
    end
    local stack_size = item_stack_size(item_name)
    local space = 0
    for index = 1, slot_count do
        local stack = inventory[index]
        if stack and stack.valid_for_read then
            if stack.name == item_name then
                space = space + math.max(stack_size - stack.count, 0)
            end
        else
            space = space + stack_size
        end
    end
    return space
end

local function clamp_to_capacity(attempt, capacity)
    if capacity == nil then
        return attempt
    end
    return math.min(attempt, capacity)
end

local function receiving_inventory(entity, item_name)
    local item_prototype = prototypes.item[item_name]
    local is_fuel_item = item_prototype and (item_prototype.fuel_value or 0) > 0
    if entity.burner and is_fuel_item then
        local fuel = entity.get_inventory(defines.inventory.fuel)
        if fuel then
            return fuel
        end
    end
    if entity.type == "container" or entity.type == "logistic-container" then
        local chest = entity.get_inventory(defines.inventory.chest)
        if chest then
            return chest
        end
    end
    local input = entity.get_inventory(defines.inventory.crafter_input)
    if input then
        return input
    end
    local chest = entity.get_inventory(defines.inventory.chest)
    if chest then
        return chest
    end
    if entity.burner then
        local fuel = entity.get_inventory(defines.inventory.fuel)
        if fuel then
            return fuel
        end
    end
    if entity.type == "lab" then
        local lab_input = entity.get_inventory(defines.inventory.lab_input)
        if lab_input then
            return lab_input
        end
    end
    return nil
end

storage.actions.insert_item = function(player_index, insert_item, count, x, y, target_name, replace)
    -- Ensure we have a valid character, recreating if necessary
    local player = storage.utils.ensure_valid_character(player_index)
    local position = {x=x, y=y}
    local surface = player.surface

    -- Check if player has enough items
    local item_count = player.get_item_count(insert_item)
    if item_count == 0 then
        error('\"No '..insert_item..' to insert from your inventory\"')
    end

    local closest_distance = math.huge
    local closest_entity = nil
    local area = {{position.x - 1, position.y - 1}, {position.x + 1, position.y + 1}}
    local buildings = nil

    if target_name then
        buildings = surface.find_entities_filtered{area = area, name=target_name}
    else
        buildings = surface.find_entities_filtered{area = area}
    end

    -- Function to get inventory fullness information
    --local function get_inventory_info(entity)
    --    if entity.get_inventory then
    --        local inv = entity.get_inventory(defines.inventory.chest)
    --        if inv then
    --            return string.format("(%d/%d)", #inv, #inv.get_bar())
    --        end
    --    end
    --    return ""
    --end

    -- Function to check if an item can be inserted into an entity
    local function can_insert_item(entity, item_name)
        if entity.type == "transport-belt" then
            -- All items that can be on ground can be on belts
            local item_prototype = prototypes.item[item_name]
            return item_prototype and not item_prototype.has_flag("only-in-cursor")

        elseif entity.type == "lab" then
            -- Check if the item is a science pack
            local item_prototype = prototypes.item[item_name]
            return item_prototype and item_prototype.type == "tool"

        elseif entity.type == "assembling-machine" then
            -- Check if it's a module first
            if is_module(item_name) then
                local module_inv = entity.get_module_inventory()
                return module_inv and not module_inv.is_full()
            end
            local recipe = entity.get_recipe()
            if recipe then
               -- Check if the item is an ingredient or the result of the recipe
                for _, ingredient in pairs(recipe.ingredients) do
                    if ingredient.name == item_name then
                        return true
                    end
                end
                -- Check if the item is the result of the recipe
                for _, product in pairs(recipe.products) do
                    if product.name == item_name then
                        return true
                    end
                end
                return false
            end
        elseif entity.type == "furnace" then
            -- Check if it's a fuel
            if prototypes.item[item_name].fuel_value > 0 then
                return true
            end
            -- Check furnace inventory for incompatible items (Factorio 2.0: crafter_input)
            local inventory = entity.get_inventory(defines.inventory.crafter_input)
            if inventory and not inventory.is_empty() then
                local existing_item = nil
                for i = 1, #inventory do
                    local stack = inventory[i]
                    if stack.valid_for_read then
                        existing_item = stack.name
                        break
                    end
                end
                if existing_item and existing_item ~= item_name then
                    error("\"furnace already contains " .. existing_item.." so cannot insert " .. item_name .."\"")
                end
            end
            -- Check if it's a valid ingredient for any furnace recipe
            return is_smelting_ingredient(item_name)
            ---- Check if it's a fuel
            --if prototypes.item[item_name].fuel_value > 0 then
            --    return true
            --end
            ---- Check if it's a valid ingredient for any furnace recipe
            --for _, recipe in pairs(prototypes.recipe) do
            --    if recipe.category == "smelting" then
            --        for _, ingredient in pairs(recipe.ingredients) do
            --            if ingredient.name == item_name then
            --                return true
            --            end
            --        end
            --    end
            --end
            --return false
        elseif entity.burner then
            -- Check if it's a fuel
            return prototypes.item[item_name].fuel_value > 0
        elseif entity.type == "container" or entity.type == "logistic-container" then
            return true  -- Containers can accept any item
        elseif entity.type == "beacon" then
            -- Beacons only accept modules
            if is_module(item_name) then
                local module_inv = entity.get_module_inventory()
                return module_inv and not module_inv.is_full()
            end
            return false
        end
        -- Add more entity types as needed
        return true
    end

    -- Find the closest suitable building
    for _, building in ipairs(buildings) do
        if building.name ~= 'character' and can_insert_item(building, insert_item) then
            local distance = ((position.x - building.position.x) ^ 2 + (position.y - building.position.y) ^ 2) ^ 0.5
            if distance < closest_distance then
                closest_distance = distance
                closest_entity = building
            end
        end
    end

    if closest_entity == nil then
        error("\"Could not find a nearby entity that can accept " .. insert_item.."\"")
    end

    -- Throw an error if the entity is too far away from the player
    if closest_distance > 10 then
        error("\"Entity at ("..closest_entity.position.x..", "..closest_entity.position.y..") is too far away from your position of ("..player.position.x..", "..player.position.y.."), move closer.\"")
    end

    -- Function to insert items onto a transport belt - one at a time
    local function insert_on_belt(belt, item_name, count)
        local line1 = belt.get_transport_line(1)
        local line2 = belt.get_transport_line(2)
        local inserted = 0

        for _ = 1, count do
            -- Try first line
            if line1.can_insert_at_back()
                and line1.insert_at_back({name = item_name, count = 1}) then
                inserted = inserted + 1
            elseif line2.can_insert_at_back()
                and line2.insert_at_back({name = item_name, count = 1}) then
                inserted = inserted + 1
            else
                break
            end
        end

        return inserted
    end

    -- Burner machines have a single fuel slot. Swapping fuel types means the
    -- old stack must leave the machine first: replace=true moves it back into
    -- the player inventory, otherwise fail with an actionable message.
    local replaced_fuel = nil
    local insert_prototype = prototypes.item[insert_item]
    if closest_entity.burner and insert_prototype
        and (insert_prototype.fuel_value or 0) > 0
    then
        local fuel_inventory = closest_entity.get_inventory(defines.inventory.fuel)
        if fuel_inventory and not fuel_inventory.is_empty() then
            for index = 1, #fuel_inventory do
                local stack = fuel_inventory[index]
                if stack and stack.valid_for_read and stack.name ~= insert_item then
                    local old_name = stack.name
                    local old_count = stack.count
                    if not replace then
                        error("\"fuel slot holds " .. old_count .. " " .. old_name
                            .. " so it cannot take " .. insert_item
                            .. ". Pass replace=true to swap the fuel, or extract the "
                            .. old_name .. " first.\"")
                    end
                    local main_inventory = player.get_inventory(
                        defines.inventory.character_main)
                    local fits = main_inventory and main_inventory.can_insert{
                        name = old_name, count = old_count
                    }
                    if not fits then
                        error("\"cannot replace " .. old_name
                            .. ": no room in your inventory for " .. old_count
                            .. " " .. old_name .. "\"")
                    end
                    local removed = fuel_inventory.remove{
                        name = old_name, count = old_count
                    }
                    if removed ~= old_count then
                        error("\"failed to extract " .. old_name
                            .. " from the fuel slot\"")
                    end
                    local moved = player.insert{name = old_name, count = removed}
                    if moved ~= removed then
                        fuel_inventory.insert{
                            name = old_name, count = removed - moved
                        }
                        error("\"could not move all " .. removed .. " " .. old_name
                            .. " into your inventory; the fuel slot was left unchanged\"")
                    end
                    replaced_fuel = {name = old_name, count = removed}
                    break
                end
            end
        end
    end

    local requested_count = count
    local insertable_count = math.min(count, item_count)
    local available_capacity = nil
    local remaining_capacity = nil

   -- Attempt to insert items
    local inserted = 0
    local assembler_output_insert = nil
    if closest_entity.type == "transport-belt" then
        -- For transport belts, we need to use a different method
        -- game.print("Inserting ".. insertable_count.. " items onto transport belt...")
        inserted = insert_on_belt(closest_entity, insert_item, insertable_count)
        local line1 = closest_entity.get_transport_line(1)
        local line2 = closest_entity.get_transport_line(2)
        local back_open = (line1 and line1.can_insert_at_back())
            or (line2 and line2.can_insert_at_back())
        if not back_open then
            remaining_capacity = 0
        end
    elseif closest_entity.type == "assembling-machine" then
        -- Check if inserting a module
        if is_module(insert_item) then
            local module_inv = closest_entity.get_module_inventory()
            if module_inv then
                available_capacity = inventory_remaining_capacity(module_inv, insert_item)
                insertable_count = clamp_to_capacity(insertable_count, available_capacity)
                if insertable_count > 0 then
                    inserted = module_inv.insert({name=insert_item, count=insertable_count})
                end
            else
                error("\"Assembling machine does not support modules\"")
            end
        else
            local recipe = closest_entity.get_recipe()
            if recipe then
                local is_product = false
                for _, product in pairs(recipe.products) do
                    if product.name == insert_item then
                        is_product = true
                        break
                    end
                end

                if is_product then
                    local output_inventory = closest_entity.get_output_inventory()
                    available_capacity = inventory_remaining_capacity(output_inventory, insert_item)
                    insertable_count = clamp_to_capacity(insertable_count, available_capacity)
                    if insertable_count > 0 then
                        inserted = output_inventory.insert({name=insert_item, count=insertable_count})
                    end
                    if inserted > 0 then
                        assembler_output_insert = {name=insert_item, count=inserted}
                    end
                else
                    -- Insert into input inventory (Factorio 2.0: crafter_input)
                    local input_inventory = closest_entity.get_inventory(defines.inventory.crafter_input)
                    available_capacity = inventory_remaining_capacity(input_inventory, insert_item)
                    insertable_count = clamp_to_capacity(insertable_count, available_capacity)
                    if insertable_count > 0 then
                        inserted = input_inventory.insert({name=insert_item, count=insertable_count})
                    end
                end
            else
                error("No recipe set for the assembling machine.")
            end
        end
    elseif closest_entity.type == "beacon" then
        -- Beacons only accept modules
        if is_module(insert_item) then
            local module_inv = closest_entity.get_module_inventory()
            if module_inv then
                available_capacity = inventory_remaining_capacity(module_inv, insert_item)
                insertable_count = clamp_to_capacity(insertable_count, available_capacity)
                if insertable_count > 0 then
                    inserted = module_inv.insert({name=insert_item, count=insertable_count})
                end
            else
                error("\"Beacon does not have a module inventory\"")
            end
        else
            error("\"Beacons can only accept modules\"")
        end
    else
        -- For other entities, use the normal insert method
        local receiving = receiving_inventory(closest_entity, insert_item)
        available_capacity = inventory_remaining_capacity(receiving, insert_item)
        insertable_count = clamp_to_capacity(insertable_count, available_capacity)
        if insertable_count > 0 then
            inserted = closest_entity.insert{name=insert_item, count=insertable_count}
        end
    end

    if available_capacity ~= nil then
        remaining_capacity = math.max(available_capacity - inserted, 0)
    end

    -- game.print("Inserted " .. inserted .. " items.")
    if inserted > 0 then
        -- Customer contracts certify factory output. Direct agent insertion is
        -- retained as audit telemetry but must not be confused with inserter-
        -- fed traffic when the depot drain runs on the next scenario tick.
        if storage.customer
            and storage.customer.depots
            and closest_entity.unit_number
            and storage.customer.depots[closest_entity.unit_number]
        then
            storage.customer.manual_pending = storage.customer.manual_pending or {}
            local pending = storage.customer.manual_pending[closest_entity.unit_number] or {}
            pending[insert_item] = (pending[insert_item] or 0) + inserted
            storage.customer.manual_pending[closest_entity.unit_number] = pending
        end
        -- Only remove successfully inserted items from player
        player.remove_item{name=insert_item, count=inserted}
        -- game.print("Successfully inserted " .. inserted .. " items.")
        local serialized = storage.utils.serialize_entity(closest_entity)
        serialized.inserted = inserted
        serialized.requested = requested_count
        serialized.insert_status = inserted >= requested_count and "completed" or "partial"
        if remaining_capacity ~= nil then
            serialized.remaining_capacity = remaining_capacity
        end
        if replaced_fuel then
            serialized.replaced_fuel = replaced_fuel
        end
        if assembler_output_insert then
            serialized.assembler_output_insert = assembler_output_insert
            serialized.warnings = serialized.warnings or {}
            table.insert(serialized.warnings,
                "inserted directly into the assembling-machine output inventory; "
                .. "engine production statistics were not credited")
        end
        if inserted < requested_count then
            serialized.warnings = serialized.warnings or {}
            table.insert(serialized.warnings, string.format(
                "partial insert: %d of %d %s inserted; %d did not fit or was refused",
                inserted, requested_count, insert_item,
                requested_count - inserted))
        end
        return serialized
    else
        local restore_error = nil
        if replaced_fuel then
            local fuel_inventory = closest_entity.get_inventory(defines.inventory.fuel)
            local restored = 0
            if fuel_inventory then
                restored = fuel_inventory.insert{
                    name = replaced_fuel.name, count = replaced_fuel.count
                }
            end
            if restored > 0 then
                player.remove_item{name = replaced_fuel.name, count = restored}
            end
            if restored ~= replaced_fuel.count then
                restore_error = " (fuel swap rollback incomplete: restored "
                    .. restored .. " of " .. replaced_fuel.count .. " "
                    .. replaced_fuel.name .. ")"
            end
            replaced_fuel = nil
        end
        local inventory_info = get_inventory_info(closest_entity)
        local capacity_note = ""
        if remaining_capacity ~= nil then
            capacity_note = string.format(" Remaining capacity: %d.",
                remaining_capacity)
        end
        local error_msg = string.format(
            "\"Failed to insert %s into %s (type %s) at position %s: " ..
            "nothing could be accepted (0 of %d requested).%s %s %s%s\"",
            insert_item,
            closest_entity.name,
            closest_entity.type,
            serpent.line(closest_entity.position),
            requested_count,
            capacity_note,
            inventory_info ~= "" and "Inventory is full " .. inventory_info or "Entity might not accept this item or has no available space.",
            inventory_info,
            restore_error or ""
        )
        error(error_msg)
    end
end
