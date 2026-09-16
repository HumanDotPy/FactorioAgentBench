-- Library for serializing items in Factorio
-- Based on code from playerManager and trainTeleports
-- Updated for Factorio 2.0

-- Factorio 2.0 API method names (no backwards compatibility needed)
local supports_bar = "supports_bar"
local get_bar = "get_bar"
local set_bar = "set_bar"

-- Version helper function (kept for potential future use)
local function version_to_table(version)
    local t = {}
    for p in string.gmatch(version, "%d+") do
        t[#t + 1] = tonumber(p)
    end
    return t
end

-- Always returns true for Factorio 2.0 as all modern features are supported
local function version_ge(comp)
    return true  -- Factorio 2.0 supports all features
end

local has_create_grid = version_ge("1.1.7")

local function round(value)
    return storage.utils.round(value)
end

-- Add this helper function at the top level
local function is_fluid_handler(entity_type)
    return entity_type == "boiler" or
           entity_type == "offshore-pump" or
           entity_type == "pump" or
           entity_type == "generator" or
           entity_type == "oil-refinery" or
    	   entity_type == "chemical-plant"
           --entity_type == "pipe" or
           --entity_type == "pipe-to-ground"
end

local recursive_serialize = {}

local function serialize_equipment_grid(grid)
    local serialized = {}
    local processed = {}
    for y = 0, grid.height - 1 do
        for x = 0, grid.width - 1 do
            local equipment = grid.get({x, y})
            if equipment ~= nil then
                local pos = equipment.position
                local combined_pos = pos.x + pos.y * grid.width + 1
                if not processed[combined_pos] then
                    processed[combined_pos] = true
                    local entry = {
                        n = equipment.name,
                        p = {pos.x, pos.y},
                    }
                    if equipment.quality and equipment.quality.name ~= "normal" then
                        entry.q = equipment.quality.name
                    end
                    if equipment.shield > 0 then entry.s = equipment.shield end
                    if equipment.energy > 0 then entry.e = equipment.energy end
                    if equipment.burner then
                        local burner = equipment.burner
                        entry.i = recursive_serialize.serialize_inventory(burner.inventory)
                        entry.r = recursive_serialize.serialize_inventory(burner.burnt_result_inventory)
                        if burner.currently_burning then
                            entry.b = burner.currently_burning.name
                            entry.f = burner.remaining_burning_fuel
                        end
                    end
                    table.insert(serialized, entry)
                end
            end
        end
    end
    return serialized
end

recursive_serialize.serialize_item_stack = function(slot, entry)
    if
        slot.is_blueprint
        or slot.is_blueprint_book
        or slot.is_upgrade_item
        or slot.is_deconstruction_item
        or slot.is_item_with_tags
    then
        local call_success, call_return = pcall(slot.export_stack)
        if not call_success then
            print("Error: '" .. call_return .. "' thrown exporting '" .. slot.name .. "'")
        else
            entry.e = call_return
        end

        return
    end

    entry.n = slot.name
    entry.c = slot.count
    if slot.quality and slot.quality.name ~= "normal" then
        entry.q = slot.quality.name
    end
    if slot.health < 1 then entry.h = slot.health end
    local durability_ok, durability = pcall(function() return slot.durability end)
    if durability_ok and durability then entry.d = durability end
    if slot.type == "ammo" then entry.a = slot.ammo end
    if slot.is_item_with_label then
        local label = {}
        if slot.label then label.t = slot.label end
        if slot.label_color then label.c = slot.label_color end
        label.a = slot.allow_manual_label_change
        entry.l = label
    end

    if slot.grid then
        entry.g = serialize_equipment_grid(slot.grid)
    end

    if slot.is_item_with_inventory then
        local sub_inventory = slot.get_inventory(defines.inventory.item_main)
        entry.i = recursive_serialize.serialize_inventory(sub_inventory)
    end
end

recursive_serialize.serialize_inventory = function(inventory)
    local serialized = {i = {}}
    if not inventory then return serialized end

    if inventory[supports_bar] and inventory[supports_bar]() then
        local bar = inventory[get_bar]()
        if bar and bar > 0 then
            serialized.b = bar
        end
    end

    local previous_index = 0
    local previous_serialized = nil
    for i = 1, #inventory do
        local item = {}
        local slot = inventory[i]
        if inventory.supports_filters and inventory.supports_filters() then
            local filter = inventory.get_filter(i)
            if filter then item.f = filter end
        end

        if slot and slot.valid_for_read then
            recursive_serialize.serialize_item_stack(slot, item)
        end

        if item.n or item.f or item.e then
            local item_serialized = helpers.table_to_json(item)
            if item_serialized == previous_serialized then
                local previous_item = serialized.i[#serialized.i]
                previous_item.r = (previous_item.r or 0) + 1
                previous_index = i
            else
                if i ~= previous_index + 1 then
                    item.s = i
                end

                previous_index = i
                previous_serialized = item_serialized
                table.insert(serialized.i, item)
            end
        else
            previous_index = 0
            previous_serialized = nil
        end
    end

    return serialized
end

recursive_serialize.deserialize_item_stack = function(slot, entry)
    if entry.e then
        local success = slot.import_stack(entry.e)
        if success == 1 then
            print("Error: import of '" .. entry.e .. "' succeeded with errors")
        elseif success == -1 then
            print("Error: import of '" .. entry.e .. "' failed")
        end

        return
    end

    local item_stack = {
        name = entry.n,
        count = entry.c,
    }
    if entry.h then item_stack.health = entry.h end
    if entry.d then item_stack.durability = entry.d end
    if entry.a then item_stack.ammo = entry.a end
    if entry.q and prototypes.quality and prototypes.quality[entry.q] then
        item_stack.quality = entry.q
    end

    local call_success, call_return = pcall(slot.set_stack, item_stack)
    if not call_success then
        print("Error: '" .. call_return .. "' thrown setting stack ".. serpent.line(entry))

    elseif not call_return then
        print("Error: Failed to set stack " .. serpent.line(entry))

    else
        if entry.l then
            -- TODO test this with AAI's unit-remote-control
            local label = entry.l
            if label.t then slot.label = label.t end
            if label.c then slot.label_color = label.c end
            slot.allow_manual_label_change = label.a
        end
        if entry.g then
            if slot.grid then
                recursive_serialize.deserialize_equipment_grid(slot.grid, entry.g)
            elseif slot.type == "item-with-entity-data" and has_create_grid then
                slot.create_grid()
                recursive_serialize.deserialize_equipment_grid(slot.grid, entry.g)
            else
                print("Error: Attempt to deserialize equipment grid on an unsupported entity")
            end
        end
        if entry.i then
            local sub_inventory = slot.get_inventory(defines.inventory.item_main)
            recursive_serialize.deserialize_inventory(sub_inventory, entry.i)
        end
    end
end

recursive_serialize.deserialize_inventory = function(inventory, serialized)
    if serialized.b and inventory[supports_bar]() then
        inventory[set_bar](serialized.b)
    end

    local last_slot_index = 0
    for _, entry in ipairs(serialized.i) do
        local base_index = entry.s or last_slot_index + 1

        local repeat_count = entry.r or 0
        for offset = 0, repeat_count do
            -- XXX what if the inventory is smaller on this instance?
            local index = base_index + offset
            local slot = inventory[index]
            if entry.f then
                local call_success, call_return = pcall(inventory.set_filter, index, entry.f)
                if not call_success then
                    print("Error: '" .. call_return .. "' thrown setting filter " .. entry.f)

                elseif not call_return then
                    print("Error: Failed to set filter " .. entry.f)
                end
            end

            if entry.n or entry.e then
                recursive_serialize.deserialize_item_stack(slot, entry)
            end
        end
        last_slot_index = base_index + repeat_count
    end
end


recursive_serialize.deserialize_equipment_grid = function(grid, serialized)
    grid.clear()
    for _, entry in ipairs(serialized) do
        local definition = {
            name = entry.n,
            position = entry.p,
        }
        if entry.q and prototypes.quality and prototypes.quality[entry.q] then
            definition.quality = entry.q
        end
        local equipment = grid.put(definition)
        if equipment then
            if entry.s then equipment.shield = entry.s end
            if entry.e then equipment.energy = entry.e end
            if entry.i then
                local burner = equipment.burner
                if burner then
                    local burning = entry.b
                    if type(burning) == "table" then burning = burning.n end
                    if burning and prototypes.item[burning] then
                        burner.currently_burning = prototypes.item[burning]
                    end
                    if entry.f then burner.remaining_burning_fuel = entry.f end
                    if entry.r then
                        recursive_serialize.deserialize_inventory(burner.burnt_result_inventory, entry.r)
                    end
                    recursive_serialize.deserialize_inventory(burner.inventory, entry.i)
                end
            end
        end
    end
end

local function serialize_fluidbox(fluidbox)
    local serialized = {
        length = #fluidbox,
    }
    if fluidbox.owner and fluidbox.owner.name then
        serialized[fluidbox.owner] = fluidbox.owner.name
    end

    -- Serialize each fluid box
    serialized.fluidboxes = {}
    for i = 1, #fluidbox do
        local box = fluidbox[i]
        local prototype = fluidbox.get_prototype(i)
        local connections = fluidbox.get_connections(i)
        local filter = fluidbox.get_filter(i)
        -- Factorio 2.0: get_flow removed, get_fluid_system_id -> get_fluid_segment_id
        local locked_fluid = fluidbox.get_locked_fluid(i)
        local fluid_segment_id = fluidbox.get_fluid_segment_id(i)

        local serialized_box = {
            prototype = prototype and prototype.object_name or nil,
            capacity = fluidbox.get_capacity(i),
            connections = {},
            filter = filter,
            flow = 0,  -- Factorio 2.0: get_flow no longer exists
            locked_fluid = locked_fluid,
            fluid_system_id = fluid_segment_id,
        }

        -- Serialize fluid
        if box then
            serialized_box.fluid = {
                name = box.name,
                amount = box.amount,
                temperature = box.temperature,
            }
        end

        -- Serialize connections (check validity of connection owner)
        for _, connection in pairs(connections) do
            if connection.owner and connection.owner.valid and connection.owner.name then
                table.insert(serialized_box.connections, "\""..connection.owner.name .. "\"")
            end
        end

        serialized.fluidboxes[i] = serialized_box
    end

    return serialized
end

-- Helper function to get relative direction of neighbor
local function get_neighbor_direction(entity, neighbor)
    local dx = neighbor.position.x - entity.position.x
    local dy = neighbor.position.y - entity.position.y

    -- Determine primary direction based on which delta is larger
    if math.abs(dx) > math.abs(dy) then
        return dx > 0 and defines.direction.east or defines.direction.west
    else
        return dy > 0 and defines.direction.south or defines.direction.north
    end
end

-- Helper function to expand a bounding box by a given amount
local function expand_box(box, amount)
    return {
        left_top = {
            x = box.left_top.x - amount,
            y = box.left_top.y - amount
        },
        right_bottom = {
            x = box.right_bottom.x + amount,
            y = box.right_bottom.y + amount
        }
    }
end

local function serialize_neighbours(entity)
    local neighbours = {}

    -- Get entity's prototype collision box
    local prototype = prototypes.entity[entity.name]
    local collision_box = prototype.collision_box

    -- Create a slightly larger search box
    local search_box = expand_box(collision_box, 0.707) -- Expand by 0.5 tiles

    -- Convert to world coordinates
    local world_box = {
        left_top = {
            x = entity.position.x + search_box.left_top.x,
            y = entity.position.y + search_box.left_top.y
        },
        right_bottom = {
            x = entity.position.x + search_box.right_bottom.x,
            y = entity.position.y + search_box.right_bottom.y
        }
    }

    -- Find entities within the expanded collision box
    local nearby = entity.surface.find_entities_filtered{
        area = world_box
    }

    -- Process each nearby entity
    for _, neighbor in pairs(nearby) do
        -- Skip if invalid, same entity, or no unit number
        if neighbor.valid and neighbor.unit_number and neighbor.unit_number ~= entity.unit_number then
            table.insert(neighbours, {
                unit_number = neighbor.unit_number,
                direction = get_neighbor_direction(entity, neighbor),
                name = "\""..neighbor.name.."\"",
                position = neighbor.position
                --type = neighbor.type
            })
        end
    end

    return neighbours
end

local function add_burner_inventory(serialized, burner)
    local fuel_inventory = burner.inventory
    if fuel_inventory and #fuel_inventory > 0 then
        serialized.fuel_inventory = {}
        serialized.remaining_fuel = 0
        for i = 1, #fuel_inventory do
            local item = fuel_inventory[i]
            if item and item.valid_for_read then

                table.insert(serialized.fuel_inventory, {name = "\""..item.name.."\"", count = item.count})
                serialized.remaining_fuel = serialized.remaining_fuel + item.count
            end
        end
    end
end

local function get_entity_direction(entity, direction)

    if direction == nil then
        return defines.direction.north
    end

    return direction
end

-- Agent-facing inserter directions name the DROP side, while the engine
-- stores the PICKUP side (live 2.0.77: direction=4 picks east and drops west).
-- This is the single documented 180-degree boundary between the two
-- conventions. It is self-inverse and identity for non-inserter prototypes.
local function inserter_engine_direction(entity_name, direction)
    if type(direction) ~= "number" then
        return direction
    end
    local prototype = prototypes.entity[entity_name]
    if prototype == nil or prototype.type ~= "inserter" then
        return direction
    end
    return (direction + 8) % 16
end

local direction_side_names = {
    [defines.direction.north] = "north",
    [defines.direction.east] = "east",
    [defines.direction.south] = "south",
    [defines.direction.west] = "west",
}

local function position_side(origin, point)
    local dx = point.x - origin.x
    local dy = point.y - origin.y
    if math.abs(dx) >= math.abs(dy) then
        if dx >= 0 then return defines.direction.east end
        return defines.direction.west
    end
    if dy >= 0 then return defines.direction.south end
    return defines.direction.north
end

local function inserter_source_item(source)
    local names = {}
    local inventory_defines = {
        defines.inventory.chest,
        defines.inventory.furnace_source,
        defines.inventory.assembling_machine_input,
        defines.inventory.crafter_input,
        defines.inventory.fuel,
    }
    for _, inventory_define in ipairs(inventory_defines) do
        if inventory_define then
            local ok, inventory = pcall(function()
                return source.get_inventory(inventory_define)
            end)
            if ok and inventory then
                local contents_ok, contents = pcall(storage.utils.get_contents_compat, inventory)
                if contents_ok then
                    for name, _ in pairs(contents or {}) do
                        names[#names + 1] = name
                    end
                end
            end
        end
    end
    local ok, line = pcall(function() return source.get_transport_line(1) end)
    if ok and line then
        local contents_ok, contents = pcall(storage.utils.get_contents_compat, line)
        if contents_ok then
            for name, _ in pairs(contents or {}) do
                names[#names + 1] = name
            end
        end
    end
    table.sort(names)
    return names[1]
end

-- When an inserter reports waiting_for_source_items, attach the tile and
-- entity it is actually trying to pick from so the status is self-explanatory.
local function inserter_pickup_look(entity, pickup_position)
    local tile = {x = math.floor(pickup_position.x) + 0.5,
        y = math.floor(pickup_position.y) + 0.5}
    local look = {tile = tile}
    local found = nil
    local ground = nil
    local ok, candidates = pcall(function()
        return entity.surface.find_entities_filtered{position = tile, radius = 0.45}
    end)
    if ok and candidates then
        for _, candidate in ipairs(candidates) do
            if candidate.valid and candidate ~= entity then
                if candidate.type == "item-entity" then
                    if not ground then
                        local stack = candidate.stack
                        ground = {
                            name = stack and stack.name or candidate.name,
                            count = stack and stack.count or 1,
                        }
                    end
                elseif not found then
                    found = candidate
                end
            end
        end
    end
    if ground then
        look.item = ground.name
        look.ground_count = ground.count
    end
    if found then
        look.entity = {
            name = found.name,
            type = found.type,
            position = {x = found.position.x, y = found.position.y},
            entity_id = found.unit_number,
            status = storage.utils.entity_status_names(found.status),
        }
        if not look.item then
            look.item = inserter_source_item(found)
        end
    end
    return look
end

-- Helper function to check if a position is valid (not colliding with water or other impassable tiles)
local invalid_tiles = {
    ["water"] = true,
    ["deepwater"] = true,
    ["water-green"] = true,
    ["deepwater-green"] = true,
    ["water-shallow"] = true,
    ["water-mud"] = true,
}

local function is_valid_connection_point(surface, position)
    -- Get the tile at the position
    local tile = surface.get_tile(position.x, position.y)

    -- Return false if the tile is invalid, true otherwise
    return not invalid_tiles[tile.name]
end

local reverse_entity_status = nil

storage.utils.entity_status_names = function(entity_status)
    local s = entity_status
    if not s then return '"unknown"' end
    if type(s) == "string" then return '"' .. s .. '"' end

    if not reverse_entity_status then
        reverse_entity_status = {}
        for k, v in pairs(defines.entity_status) do
            reverse_entity_status[v] = k
        end
    end

    local name = reverse_entity_status[s]
    if name then return '"' .. name .. '"' end

    return '"unknown"'
end

storage.utils.get_entity_direction = get_entity_direction
storage.utils.inserter_engine_direction = inserter_engine_direction

-- Placement/rotation receipts use this to confirm that a requested drop side
-- matches the built geometry; mismatch is a direction-convention bug.
storage.utils.inserter_direction_report = function(serialized, requested_direction)
    if serialized == nil or serialized.drop_side == nil then
        return serialized
    end
    if type(requested_direction) ~= "number" then
        return serialized
    end
    local requested = requested_direction % 16
    if serialized.drop_side ~= requested then
        serialized.direction_warning =
            "requested " .. (direction_side_names[requested] or tostring(requested))
            .. " as the inserter drop side, but the drop tile is "
            .. (direction_side_names[serialized.drop_side] or tostring(serialized.drop_side))
            .. " of the entity; agent-facing inserter directions name the drop side"
    end
    return serialized
end

storage.utils.serialize_item_stack = recursive_serialize.serialize_item_stack
storage.utils.deserialize_item_stack = recursive_serialize.deserialize_item_stack
storage.utils.serialize_inventory = recursive_serialize.serialize_inventory
storage.utils.deserialize_inventory = recursive_serialize.deserialize_inventory
storage.utils.serialize_equipment_grid = serialize_equipment_grid
storage.utils.deserialize_equipment_grid = recursive_serialize.deserialize_equipment_grid

storage.utils.serialize_recipe = function(recipe)
    local function serialize_number(num)
        if num == math.huge then
            return "inf"
        elseif num == -math.huge then
            return "-inf"
        else
            return num
        end
    end
    if not recipe then return nil end

    local ingredients = {}
    for _, ingredient in pairs(recipe.ingredients) do
        table.insert(ingredients, {
            name = '"' .. ingredient.name .. '"',
            amount = serialize_number(ingredient.amount),
            type = '"' .. ingredient.type .. '"'
        })
    end

    local products = {}
    for _, product in pairs(recipe.products) do
        table.insert(products, {
            name = '"' .. product.name .. '"',
            amount = serialize_number(product.amount),
            type = '"' .. product.type .. '"',
            probability = product.probability and serialize_number(product.probability) or 1
        })
    end

    return {
        name = '"' .. recipe.name .. '"',
        category = '"' .. recipe.category .. '"',
        enabled = recipe.enabled,
        energy = serialize_number(recipe.energy),
        ingredients = ingredients,
        products = products
    }
end

storage.utils.serialize_entity = function(entity)

    if entity == nil then
        return {}
    end

    -- Check if entity is still valid (hasn't been destroyed/removed)
    if not entity.valid then
        error("Cannot serialize entity: LuaEntity is no longer valid (entity may have been destroyed or removed)")
    end
    storage.entity_handles = storage.entity_handles or {}
    if entity.unit_number then storage.entity_handles[entity.unit_number] = entity end
    local direction = inserter_engine_direction(entity.name, entity.direction or 0)


    --game.print("Serialized direction: ", {skip=defines.print_skip.never})
    local serialized = {
        id = entity.unit_number,
        name = "\""..entity.name.."\"",
        position = entity.position,
        direction = direction,
        health = entity.health,
        energy = entity.energy,
        type = "\""..entity.type.."\"",
        status = storage.utils.entity_status_names(entity.status)
    }

    if entity.grid then
        serialized.grid = serialize_equipment_grid(entity.grid)
    end
    --game.print(serpent.line(entity.get_inventory(defines.inventory.turret_ammo)))
    serialized.warnings = storage.utils.get_issues(entity)

    local inventory_types = {
        {name = "fuel", define = defines.inventory.fuel},
        {name = "burnt_result", define = defines.inventory.burnt_result},
        {name = "inventory", define = defines.inventory.chest},
        {name = "furnace_source", define = defines.inventory.furnace_source},
        {name = "furnace_result", define = defines.inventory.furnace_result},
        {name = "furnace_modules", define = defines.inventory.furnace_modules},
        {name = "assembling_machine_input", define = defines.inventory.assembling_machine_input},
        {name = "assembling_machine_output", define = defines.inventory.assembling_machine_output},
        {name = "assembling_machine_modules", define = defines.inventory.assembling_machine_modules},
        {name = "lab_input", define = defines.inventory.lab_input},
        {name = "lab_modules", define = defines.inventory.lab_modules},
        {name = "turret_ammo", define = defines.inventory.turret_ammo}
    }

    for _, inv_type in ipairs(inventory_types) do
        local inventory = entity.get_inventory(inv_type.define)
        if inventory then
            serialized[inv_type.name] = storage.utils.get_contents_compat(inventory)
        end
    end

    -- Add dimensions of the entity
    local prototype = prototypes.entity[entity.name]
    local collision_box = prototype.collision_box
    serialized.dimensions = {
        width = math.abs(collision_box.right_bottom.x - collision_box.left_top.x),
        height = math.abs(collision_box.right_bottom.y - collision_box.left_top.y),
    }
    serialized.neighbours = serialize_neighbours(entity)

    -- Add input and output locations if the entity is a transport belt
    if entity.type == "transport-belt" or entity.type == "underground-belt" then
        local x, y = entity.position.x, entity.position.y

        -- Initialize positions with default offsets based on belt direction
        local input_offset = {
            [defines.direction.north] = {x = 0, y = 1},
            [defines.direction.south] = {x = 0, y = -1},
            [defines.direction.east] = {x = -1, y = 0},
            [defines.direction.west] = {x = 1, y = 0}
        }

        local output_offset = {
            [defines.direction.north] = {x = 0, y = -1},
            [defines.direction.south] = {x = 0, y = 1},
            [defines.direction.east] = {x = 1, y = 0},
            [defines.direction.west] = {x = -1, y = 0}
        }

        -- Set input position based on upstream connections
        local input_pos = {x = x, y = y}
        if #entity.belt_neighbours["inputs"] > 0 then
            -- Use the position of the first connected input belt (check validity first)
            local input_belt = entity.belt_neighbours["inputs"][1]
            if input_belt and input_belt.valid then
                input_pos = {x = input_belt.position.x, y = input_belt.position.y}
            else
                -- Fallback to default offset if neighbor is invalid
                local offset = input_offset[entity.direction]
                input_pos.x = x + offset.x
                input_pos.y = y + offset.y
            end
        else
            -- No input connection, use default offset
            local offset = input_offset[entity.direction]
            input_pos.x = x + offset.x
            input_pos.y = y + offset.y
        end
        serialized.input_position = input_pos

        -- Set output position based on downstream connections
        local output_pos = {x = x, y = y}
        if #entity.belt_neighbours["outputs"] > 0 then
            -- Use the position of the first connected output belt (check validity first)
            local output_belt = entity.belt_neighbours["outputs"][1]
            if output_belt and output_belt.valid then
                output_pos = {x = output_belt.position.x, y = output_belt.position.y}
            else
                -- Fallback to default offset if neighbor is invalid
                local offset = output_offset[entity.direction]
                output_pos.x = x + offset.x
                output_pos.y = y + offset.y
            end
        else
            -- No output connection, use default offset
            local offset = output_offset[entity.direction]
            output_pos.x = x + offset.x
            output_pos.y = y + offset.y
        end
        serialized.output_position = output_pos

        -- Store the belt's own position
        serialized.position = {x = x, y = y}

        -- Handle belt contents and status
        local line1 = entity.get_transport_line(1)
        local line2 = entity.get_transport_line(2)

        -- Calculate if belt is full at the output
        local is_full = not line1.can_insert_at_back() and not line2.can_insert_at_back()

        serialized.belt_status = {
            status = storage.utils.entity_status_names(is_full and defines.entity_status.full_output or defines.entity_status.normal)
        }

        -- Get and merge contents from both lines
        serialized.inventory = {}
        local line1_contents = storage.utils.get_contents_compat(line1)
        local line2_contents = storage.utils.get_contents_compat(line2)

        -- Set terminus and source flags based on connections
        serialized.is_terminus = #entity.belt_neighbours["outputs"] == 0
        serialized.is_source = #entity.belt_neighbours["inputs"] == 0

        serialized.inventory['left'] = {}
        serialized.inventory['right'] = {}

        -- Merge contents from both belt lines
        for item_name, count in pairs(line1_contents) do
            serialized.inventory['left'][item_name] = (serialized.inventory['left'][item_name] or 0) + count
        end
        for item_name, count in pairs(line2_contents) do
            serialized.inventory['right'][item_name] = (serialized.inventory['right'][item_name] or 0) + count
        end

        -- Add warning if belt is full
        if not serialized.warnings then
            serialized.warnings = {}
        end
        if is_full then
            table.insert(serialized.warnings, "Belt output is full")
        end

        -- Special handling for underground belts
        if entity.type == "underground-belt" then
            serialized.is_input = entity.belt_to_ground_type == "input"
            -- Check validity of underground belt neighbor before accessing properties
            local neighbour_valid = entity.neighbours ~= nil and entity.neighbours.valid
            if serialized.is_input then
                serialized.is_terminus = not neighbour_valid
            else
                serialized.is_source = not neighbour_valid
            end
            if neighbour_valid then
                serialized.connected_to = entity.neighbours.unit_number
            end
        end
    end

    serialized.id = entity.unit_number
    -- Special handling for power poles
    if entity.type == "electric-pole" then
        local stats = entity.electric_network_statistics
        local flow_rate = 0
        if stats and stats.get_flow_count then
            for name in pairs(stats.input_counts or {}) do
                flow_rate = flow_rate + (stats.get_flow_count{
                    name = name,
                    category = "input",
                    precision_index = defines.flow_precision_index.one_minute,
                    count = false
                } or 0)
            end
        end
        serialized.flow_rate = flow_rate
    end

    -- Add input and output positions if the entity is a splitter
    if entity.type == "splitter" then
        -- Initialize positions based on entity center
        local x, y = entity.position.x, entity.position.y

        -- Calculate the offset for left/right positions (0.5 tiles)
        local lateral_offset = 0.5

        if entity.direction == defines.direction.north then
            -- Input positions (south side)
            serialized.input_positions = {
                {x = x - lateral_offset, y = y + 1},
                {x = x + lateral_offset, y = y + 1}
            }
            -- Output positions (north side)
            serialized.output_positions = {
                {x = x - lateral_offset, y = y - 1},
                {x = x + lateral_offset, y = y - 1}
            }
        elseif entity.direction == defines.direction.south then
            -- Input positions (north side)
            serialized.input_positions = {
                {x = x + lateral_offset, y = y - 1},
                {x = x - lateral_offset, y = y - 1}
            }
            -- Output positions (south side)
            serialized.output_positions = {
                {x = x + lateral_offset, y = y + 1},
                {x = x - lateral_offset, y = y + 1}
            }
        elseif entity.direction == defines.direction.east then
            -- Input positions (west side)
            serialized.input_positions = {
                {x = x - 1, y = y - lateral_offset},
                {x = x - 1, y = y + lateral_offset}
            }
            -- Output positions (east side)
            serialized.output_positions = {
                {x = x + 1, y = y - lateral_offset},
                {x = x + 1, y = y + lateral_offset}
            }
        elseif entity.direction == defines.direction.west then
            -- Input positions (east side)
            serialized.input_positions = {
                {x = x + 1, y = y + lateral_offset},
                {x = x + 1, y = y - lateral_offset}
            }
            -- Output positions (west side)
            serialized.output_positions = {
                {x = x - 1, y = y + lateral_offset},
                {x = x - 1, y = y - lateral_offset}
            }
        end

        -- Get the contents of both output lines
        serialized.inventory = {
            storage.utils.get_contents_compat(entity.get_transport_line(1)),
            storage.utils.get_contents_compat(entity.get_transport_line(2))
        }
    end

    -- Add input and output locations if the entity is an inserter
    if entity.type == "inserter" then
        serialized.pickup_position = entity.pickup_position
        serialized.drop_position = entity.drop_position

        ---- round to the nearest 0.5
        serialized.pickup_position.x = round(serialized.pickup_position.x * 2 ) / 2
        serialized.pickup_position.y = round(serialized.pickup_position.y * 2 ) / 2
        serialized.drop_position.x = round(serialized.drop_position.x * 2 ) / 2
        serialized.drop_position.y = round(serialized.drop_position.y * 2 ) / 2

        serialized.pickup_side = position_side(entity.position, serialized.pickup_position)
        serialized.drop_side = position_side(entity.position, serialized.drop_position)
        serialized.pickup_side_name = direction_side_names[serialized.pickup_side]
        serialized.drop_side_name = direction_side_names[serialized.drop_side]

        if entity.status == defines.entity_status.waiting_for_source_items then
            serialized.status_reason = {
                looking_at = inserter_pickup_look(entity, serialized.pickup_position),
            }
        end

        local burner = entity.burner
        if burner then
            add_burner_inventory(serialized, burner)
        end
    end

    -- Add input and output locations if the entity is a pipe
    if entity.type == "pipe" then
        serialized.connections = {}
        local fluid_name = nil
        for _, connection in pairs(entity.fluidbox.get_pipe_connections(1)) do
            table.insert(serialized.connections, connection.position)
        end
        local contents_count = 0
        -- Factorio 2.0: get_fluid_system_contents -> get_fluid_segment_contents
        local segment_contents = entity.fluidbox.get_fluid_segment_contents(1)
        if segment_contents then
            for name, count in pairs(segment_contents) do
                contents_count = contents_count + count
                fluid_name = "\""..name.."\""
            end
        end
        serialized.contents = contents_count
        serialized.fluid = fluid_name
        -- Factorio 2.0: get_fluid_system_id -> get_fluid_segment_id, get_flow removed
        serialized.fluidbox_id = entity.fluidbox.get_fluid_segment_id(1)
        serialized.flow_rate = 0
    end

    -- Add input and output locations if the entity is a pipe-to-ground
    if entity.type == "pipe-to-ground" then
        serialized.connections = {}
        local fluid_name = nil
        for _, connection in pairs(entity.fluidbox.get_pipe_connections(1)) do
            table.insert(serialized.connections, connection.position)
        end
        local contents_count = 0
        -- Factorio 2.0: get_fluid_system_contents -> get_fluid_segment_contents
        local segment_contents = entity.fluidbox.get_fluid_segment_contents(1)
        if segment_contents then
            for name, count in pairs(segment_contents) do
                contents_count = contents_count + count
                fluid_name = "\""..name.."\""
            end
        end
        -- Factorio 2.0: get_fluid_system_id -> get_fluid_segment_id, get_flow removed
        serialized.fluidbox_id = entity.fluidbox.get_fluid_segment_id(1)
        serialized.flow_rate = 0
        serialized.contents = contents_count
        serialized.fluid = fluid_name
        serialized.connection_points =
            storage.utils.get_pipe_to_ground_connection_points(entity)
    end

    -- Add input and output locations if the entity is a pump
    if entity.type == "pump" then
        local input_connections = entity.fluidbox.get_connections(1)
        local output_connections = entity.fluidbox.get_connections(2)
        if input_connections and input_connections[1] then
            serialized.input_position = input_connections[1].position
        end
        if output_connections and output_connections[1] then
            serialized.output_position = output_connections[1].position
        end
        serialized.connection_points = storage.utils.get_pump_connection_points(entity)
    end

    -- Add the current research to the lab
    if entity.name == "lab" then
        if storage.agent_characters[1].force.current_research ~= nil then
            serialized.research = storage.agent_characters[1].force.current_research.name
        else
            serialized.research = nil
        end
    end

    if entity.name == "oil-refinery" then
        local x, y = entity.position.x, entity.position.y
        serialized.input_connection_points = {}
        serialized.output_connection_points = {}

        local recipe = entity.get_recipe()
        local mappings = storage.utils.get_refinery_fluid_mappings(entity, recipe)
        if mappings then
            serialized.input_connection_points = mappings.inputs
            serialized.output_connection_points = mappings.outputs
        end
    end

    if entity.name == "chemical-plant" then
        local x, y = entity.position.x, entity.position.y
        serialized.input_connection_points = {}
        serialized.output_connection_points = {}

        local recipe = entity.get_recipe()
        local mappings = storage.utils.get_chemical_plant_fluid_mappings(entity, recipe)
        if mappings then
            serialized.input_connection_points = mappings.inputs
            serialized.output_connection_points = mappings.outputs
        end

        -- Filter out any invalid connection points
        local filtered_input_points = {}
        for _, point in ipairs(serialized.input_connection_points) do
            if is_valid_connection_point(entity.surface, point) then
                table.insert(filtered_input_points, point)
            end
        end
        serialized.input_connection_points = filtered_input_points

        -- Filter out any invalid connection points
        local filtered_output_points = {}
        for _, point in ipairs(serialized.output_connection_points) do
            if is_valid_connection_point(entity.surface, point) then
                table.insert(filtered_output_points, point)
            end
        end
        serialized.output_connection_points = filtered_output_points

    end


    if entity.type == "storage-tank" then
        -- Get and filter connection points
        local connection_points = storage.utils.get_storage_tank_connection_points(entity)
        local filtered_points = {}

        -- Filter out invalid connection points (e.g., those in water)
        for _, point in ipairs(connection_points) do
            if is_valid_connection_point(entity.surface, point) then
                table.insert(filtered_points, point)
            end
        end

        -- Add connection points to serialized data
        serialized.connection_points = filtered_points

        -- Add fluid box information
        if entity.fluidbox and #entity.fluidbox > 0 then
            local fluid = entity.fluidbox[1]
            if fluid then
                serialized.fluid = string.format("\"%s\"", fluid.name)
                serialized.fluid_amount = fluid.amount
                serialized.fluid_temperature = fluid.temperature
                -- Factorio 2.0: get_fluid_system_id -> get_fluid_segment_id
                serialized.fluid_system_id = entity.fluidbox.get_fluid_segment_id(1)
            end
        end

        -- Add warning if some connection points were filtered
        if #filtered_points < #connection_points then
            if not serialized.warnings then
                serialized.warnings = {}
            end
            table.insert(serialized.warnings, "\"some connection points were filtered due to being blocked by water\"")
        end
    end


    if entity.type == "assembling-machine" then
        local x, y = entity.position.x, entity.position.y
        serialized.connection_points = {}

        -- Assembling machine connection points are similar to chemical plants
        if entity.direction == defines.direction.north then
            table.insert(serialized.connection_points,
                    {x = x, y = y - 2
                    })
        elseif entity.direction == defines.direction.south then
            table.insert(serialized.connection_points,
                    {x = x, y = y + 2
                    })
        elseif entity.direction == defines.direction.east then
            table.insert(serialized.connection_points,
                    {x = x + 2, y = y
                    })
        elseif entity.direction == defines.direction.west then
            table.insert(serialized.connection_points,
                    {x = x - 2, y = y
                    })
        end
    end
    -- Add tile dimensions of the entity
    serialized.tile_dimensions = {
        tile_width = prototype.tile_width,
        tile_height = prototype.tile_height,
    }

    if entity.type == "mining-drill" then
        serialized.drop_position = {
            x = entity.drop_position.x,
            y = entity.drop_position.y
        }
        serialized.drop_position.x = round(serialized.drop_position.x * 2) / 2
        serialized.drop_position.y = round(serialized.drop_position.y * 2) / 2
        -- game.print("Mining drill drop position: " .. serpent.line(serialized.drop_position))

        -- Get the mining area
        local prototype = prototypes.entity[entity.name]
        local mining_area = 1
        if prototype.mining_drill_radius then
            mining_area = prototype.mining_drill_radius * 2
        end

        local position = entity.position

        -- Initialize resources table
        serialized.resources = {}

        -- Calculate the area to check based on mining drill radius
        local start_x = position.x - mining_area/2
        local start_y = position.y - mining_area/2
        local end_x = position.x + mining_area/2
        local end_y = position.y + mining_area/2

        local resources = game.surfaces[1].find_entities_filtered{
            area = {{start_x, start_y}, {end_x, end_y}},
            type = "resource",
        }

        for _, resource in pairs(resources) do
            -- Check resource validity before accessing properties
            if resource.valid then
                if not serialized.resources[resource.name] then
                    serialized.resources[resource.name] = {
                        name = "\""..resource.name.."\"",
                        count = 0,
                    }
                end

                -- Add the resource amount and position
                serialized.resources[resource.name].count = serialized.resources[resource.name].count + resource.amount
            end
        end


        -- Convert resources table to array for consistent ordering
        local resources_array = {}
        for _, resource_data in pairs(serialized.resources) do
            table.insert(resources_array, resource_data)
        end
        serialized.resources = resources_array

        -- Add mining status
        if #resources_array == 0 then
            serialized.status = storage.utils.entity_status_names(defines.entity_status.no_minable_resources)
            if not serialized.warnings then serialized.warnings = {} end
            table.insert(serialized.warnings, "\"nothing to mine\"")
        end

        -- Add burner info if applicable
        local burner = entity.burner
        if burner then
            add_burner_inventory(serialized, burner)
        end
    end

    -- Add recipes if the entity is a crafting machine
    if entity.type == "assembling-machine" or entity.type == "furnace" then
        if entity.get_recipe() then
            serialized.recipe = storage.utils.serialize_recipe(entity.get_recipe())
        end
    end

    -- Add fluid input point if the entity is a boiler
    if entity.type == "boiler" then
        local burner = entity.burner
        if burner then
            add_burner_inventory(serialized, burner)
        end

        --local direction = entity.direction
        local x, y = entity.position.x, entity.position.y

        if entity.direction == defines.direction.north then
            -- game.print("Boiler direction is north")
            serialized.connection_points = {{x = x - 2, y = y + 0.5}, {x = x + 2, y = y + 0.5}}
            serialized.steam_output_point = {x = x, y = y - 1.5}
        elseif entity.direction == defines.direction.south then
            -- game.print("Boiler direction is south")
            serialized.connection_points = {{x = x - 2, y = y - 0.5}, {x = x + 2, y = y - 0.5}}
            serialized.steam_output_point = {x = x, y = y + 1.5}
        elseif entity.direction == defines.direction.east then
            -- game.print("Boiler direction is east")
            serialized.connection_points = {{x = x - 0.5, y = y - 2}, {x = x - 0.5, y = y + 2}}
            serialized.steam_output_point = {x = x + 1.5, y = y}
        elseif entity.direction == defines.direction.west then
            -- game.print("Boiler direction is west")
            serialized.connection_points = {{x = x + 0.5, y = y - 2}, {x = x + 0.5, y = y + 2}}
            serialized.steam_output_point = {x = x - 1.5, y = y}
        end
    end

    if entity.name == "heat-exchanger" then
        serialized.connection_points =
            storage.utils.get_heat_exchanger_connection_points(entity)
    end

    if entity.type == "rocket-silo" then
        -- Basic rocket silo properties
        serialized.rocket_parts = 0  -- Will be updated with actual count
        serialized.rocket_progress = 0.0  -- Will be updated with actual progress
        -- Factorio 2.0: launch_count removed (no longer available on LuaEntity)

        -- Get part construction progress using the direct entity property (Factorio 2.0 compatible)
        serialized.rocket_parts = entity.rocket_parts or 0
        local parts_required = entity.prototype.rocket_parts_required or 100
        serialized.rocket_progress = (serialized.rocket_parts / parts_required) * 100.0

        -- Get input inventories for rocket components
        local rocket_inventory = {
            rocket_part = entity.get_inventory(defines.inventory.rocket_silo_input),
            result = entity.get_inventory(defines.inventory.rocket_silo_output)
        }

        -- Serialize the component inventories
        for name, inventory in pairs(rocket_inventory) do
            if inventory and not inventory.is_empty() then
                serialized[name .. "_inventory"] = storage.utils.get_contents_compat(inventory)
            end
        end

        -- Update status based on rocket state
        if serialized.rocket_parts < parts_required and serialized.rocket_parts > 0 then
            serialized.status = storage.utils.entity_status_names(defines.entity_status.preparing_rocket_for_launch)
        end

        -- Add warnings based on state
        if not serialized.warnings then
            serialized.warnings = {}
        end
        if serialized.rocket_parts < parts_required and serialized.rocket_parts > 0 then
            table.insert(serialized.warnings, "\"waiting for rocket parts\"")
        end
    end

    -- Factorio 2.0: solar panels no longer have electric_output_flow_limit property
    -- Solar panel power output is now determined by prototype settings (performance_at_day/night)

    if entity.type == 'accumulator' then
        --serialized.energy_source = entity.energy_source
        --serialized.power_usage = entity.power_usage
        --serialized.emissions = entity.emissions
        serialized.energy = entity.energy
    end

    if entity.type == "generator" then
        serialized.connection_points = storage.utils.get_generator_connection_positions(entity)
        serialized.energy_generated_last_tick = entity.energy_generated_last_tick
        --serialized.power_production = entity.power_production
    end

    if entity.name == "pumpjack" then
        serialized.connection_points = storage.utils.get_pumpjack_connection_points(entity)
    end

    -- Add fuel and input ingredients if the entity is a furnace or burner
    if entity.type == "furnace" or entity.type == "burner" then
        local burner = entity.burner
        if burner then
            add_burner_inventory(serialized, burner)
        end
        local input_inventory = entity.get_inventory(defines.inventory.furnace_source)
        if input_inventory and #input_inventory > 0 then
            serialized.input_inventory = {}
            for i = 1, #input_inventory do
                local item = input_inventory[i]
                if item and item.valid_for_read then
                    table.insert(serialized.input_inventory, {name = "\""..item.name.."\"", count = item.count})
                end
            end
        end
    end

    -- Add fluid box if the entity is an offshore pump
    if entity.type == "offshore-pump" then
        serialized.connection_points = storage.utils.get_offshore_pump_connection_points(entity)
    end

    -- If entity has a fluidbox
    if entity.fluidbox then
        local fluid_box = entity.fluidbox
        if fluid_box and #fluid_box > 0 then
            serialized.fluid_box = {}
            for i = 1, #fluid_box do
                -- game.print("Fluid!")
                local fluid = fluid_box[i]
                if fluid then
                    table.insert(serialized.fluid_box, {name = "\""..fluid.name.."\"", amount = fluid.amount, temperature = fluid.temperature})
                end
            end
        end
    end

    -- Add fluid handler status check
    if is_fluid_handler(entity.type) then
        -- Check if the entity has a fluidbox
        if not entity.fluidbox or #entity.fluidbox == 0 then
            serialized.status = storage.utils.entity_status_names("not_connected")
            if not serialized.warnings then
                serialized.warnings = {}
            end
            table.insert(serialized.warnings, "\"missing fluid connection\"")
        else
            -- Additional fluid-specific checks
            local fluid_systems = {}
            local has_fluid = false
            local fluid_contents = nil
            for i = 1, #entity.fluidbox do
                if entity.fluidbox[i] then
                    -- Factorio 2.0: get_fluid_system_id -> get_fluid_segment_id
                    local system_id = entity.fluidbox.get_fluid_segment_id(i)
                    if system_id then
                        table.insert(fluid_systems, system_id)
                    end
                    has_fluid = true
                    fluid_contents =  "\""..entity.fluidbox[i].name.."\""
                    break
                end
            end
            serialized.fluid_systems = fluid_systems

            if not has_fluid then
                serialized.status = storage.utils.entity_status_names("not_connected")
                if not serialized.warnings then
                    serialized.warnings = {}
                end
                table.insert(serialized.warnings, "\"no fluid present in connections\"")
            else
                serialized.fluid = fluid_contents
            end
            --serialized.fluidbox = serialize_fluidbox(entity.fluidbox)
        end
    end

    if entity.electric_network_id then
        serialized.electrical_id = entity.electric_network_id
    end

    -- Post-process connection points if they exist
    if serialized.connection_points then
        local original_point_count = #serialized.connection_points
        local filtered_points = {}
        for _, point in ipairs(serialized.connection_points) do
            if is_valid_connection_point(entity.surface, point) then
                table.insert(filtered_points, point)
            end
        end

        -- Update connection points or remove if all were filtered
        if #filtered_points > 0 then
            serialized.connection_points = filtered_points
        else
            serialized.connection_points = nil
        end

        if #filtered_points < original_point_count then
            if not serialized.warnings then
                serialized.warnings = {}
            end
            table.insert(serialized.warnings, "\"some connection points were filtered due to being blocked by water\"")
        end
    end

    -- Handle special case for boilers which have separate steam output points
    if serialized.steam_output_point then
        if not is_valid_connection_point(entity.surface, serialized.steam_output_point) then
            serialized.steam_output_point = nil
            if not serialized.warnings then
                serialized.warnings = {}
            end
            table.insert(serialized.warnings, "\"steam output point was filtered due to being blocked by water\"")
        end
    end

    return serialized
end

script.on_nth_tick(60, function()
    local handles = storage.entity_handles
    if not handles then return end
    for unit_number, entity in pairs(handles) do
        if not entity.valid then handles[unit_number] = nil end
    end
end)
