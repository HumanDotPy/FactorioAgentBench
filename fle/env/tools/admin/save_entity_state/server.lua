-- Helper to ensure all numbers are serializable
local function serialize_number(num)
    if num == math.huge then
        return "inf"
    elseif num == -math.huge then
        return "-inf"
    else
        return tostring(num)
    end
end

-- Helper to serialize position to fixed format
local function serialize_position(pos)
    return {
        x = serialize_number(pos.x),
        y = serialize_number(pos.y)
    }
end

-- Main serialization function
storage.actions.save_entity_state = function(player_index, distance, player_entities, resource_entities, items_on_ground)
    local surface = storage.agent_characters[player_index].surface
    if player_entities then
        entities = surface.find_entities_filtered({area={{-distance, -distance}, {distance, distance}}, force=storage.agent_characters[player_index].force})
    else
        if resource_entities then
            entities = surface.find_entities({{-distance, -distance}, {distance, distance}})
        else
            entities = surface.find_entities_filtered({area={{-distance, -distance}, {distance, distance}}, force=storage.agent_characters[player_index].force})
        end
    end

    -- Always get items on ground if requested
    if items_on_ground then
        local ground_items = surface.find_entities_filtered({
            area = {{-distance, -distance}, {distance, distance}},
            name = "item-on-ground"
        })
        -- Merge the arrays
        for _, item in pairs(ground_items) do
            table.insert(entities, item)
        end
    end

    local entity_states = {}
    local entity_array = {}
    -- The native design overlay retains settings/wires both before and after
    -- construction. Entity snapshots below retain runtime inventory and energy;
    -- existing real entities are matched when the design overlay is restored.
    local capture_design = false
    local min_x,min_y,max_x,max_y = math.huge,math.huge,-math.huge,-math.huge
    for _, entity in pairs(entities) do
        if entity.type == "entity-ghost" or entity.type == "tile-ghost"
            or entity.type == "item-request-proxy" then capture_design = true
        elseif entity.type ~= "character" and entity.type ~= "item-entity"
            and not entity.prototype.has_flag("not-blueprintable") then
            capture_design = true
        end
        local box=entity.bounding_box
        min_x=math.min(min_x,box.left_top.x); min_y=math.min(min_y,box.left_top.y)
        max_x=math.max(max_x,box.right_bottom.x); max_y=math.max(max_y,box.right_bottom.y)
    end
    if capture_design then
        local inventory=game.create_inventory(1)
        local ok,err=pcall(function()
            local stack=inventory[1]; stack.set_stack{name="blueprint"}
            local mapping=stack.create_blueprint{surface=surface,
                force=storage.agent_characters[player_index].force,
                area={{min_x-1,min_y-1},{max_x+1,max_y+1}},always_include_tiles=true,
                include_entities=true,include_modules=true,include_station_names=true,
                include_trains=true,include_fuel=true}
            local anchor=nil
            for _, blueprint_entity in ipairs(stack.get_blueprint_entities() or {}) do
                local original=mapping[blueprint_entity.entity_number]
                if original then
                    anchor={x=original.position.x-blueprint_entity.position.x,
                        y=original.position.y-blueprint_entity.position.y}
                    break
                end
            end
            if not anchor then
                local tiles=stack.get_blueprint_tiles() or {}
                local names,seen={},{}
                local relative_x,relative_y=math.huge,math.huge
                for _,tile in ipairs(tiles) do
                    if not seen[tile.name] then names[#names+1]=tile.name;seen[tile.name]=true end
                    relative_x=math.min(relative_x,tile.position.x)
                    relative_y=math.min(relative_y,tile.position.y)
                end
                local absolute_x,absolute_y=math.huge,math.huge
                for _,tile in ipairs(surface.find_tiles_filtered{
                    name=names,area={{min_x-1,min_y-1},{max_x+1,max_y+1}}}) do
                    absolute_x=math.min(absolute_x,tile.position.x)
                    absolute_y=math.min(absolute_y,tile.position.y)
                end
                for _,ghost in ipairs(surface.find_entities_filtered{type="tile-ghost",
                    area={{min_x-1,min_y-1},{max_x+1,max_y+1}}}) do
                    absolute_x=math.min(absolute_x,math.floor(ghost.position.x))
                    absolute_y=math.min(absolute_y,math.floor(ghost.position.y))
                end
                if tiles[1] and absolute_x < math.huge then
                    anchor={x=absolute_x-relative_x,y=absolute_y-relative_y}
                end
            end
            if not anchor or not stack.is_blueprint_setup() then
                error("Could not capture pending construction for checkpoint")
            end
            local pending_tiles={}
            for _,entity in pairs(entities) do
                if entity.type == "tile-ghost" then
                    pending_tiles[#pending_tiles+1]=entity.position
                end
            end
            table.insert(entity_array,{name='"fle-blueprint-overlay"',
                position=serialize_position(anchor),content='"'..stack.export_stack()..'"',
                pending_tiles=pending_tiles})
        end)
        inventory.destroy()
        if not ok then error(err) end
    end
    -- Serialize inventories by type (Factorio 2.0: unified crafter_* defines)
    local inventory_defines = {
        chest = defines.inventory.chest,
        crafter_input = defines.inventory.crafter_input,      -- was furnace_source/assembling_machine_input
        crafter_output = defines.inventory.crafter_output,    -- was furnace_result/assembling_machine_output
        fuel = defines.inventory.fuel,
        burnt_result = defines.inventory.burnt_result,
        turret_ammo = defines.inventory.turret_ammo,
        lab_input = defines.inventory.lab_input,
        lab_modules = defines.inventory.lab_modules,
        crafter_modules = defines.inventory.crafter_modules,
        roboport_robot = defines.inventory.roboport_robot,
        roboport_material = defines.inventory.roboport_material,
        robot_cargo = defines.inventory.robot_cargo,
    }

    for _, entity in pairs(entities) do

        if entity.name == "item-on-ground" then
            -- Capture the item details
            local item = entity.stack
            if item and item.valid then
                local state = {
                    name = '\"item-on-ground\"',
                    type = '"' .. item.name .. '"',
                    count = serialize_number(item.count),
                    position = serialize_position(entity.position),
                }
                table.insert(entity_array, state)
            end
        elseif entity.type == "entity-ghost" or entity.type == "tile-ghost"
            or entity.type == "item-request-proxy" then
            -- Restored through the native overlay after physical entities.
        elseif entity.name ~= "character" then
            local state = {
                name = '"' .. entity.name .. '"',
                position = serialize_position(entity.position),
                direction = entity.direction,
                entity_number = entity.unit_number or -1,
                type = '"' .. entity.type .. '"',
                health = serialize_number(entity.health),
                energy = serialize_number(entity.energy or 0),
                active = entity.active,
                status = storage.utils.entity_status_names(entity.status),
                warnings = {},
                inventories = {}
            }
            state.deconstruction = entity.to_be_deconstructed(entity.force)
            if entity.to_be_upgraded() then
                local target,quality=entity.get_upgrade_target()
                if target then
                    state.upgrade_target='"'..target.name..'"'
                    state.upgrade_quality='"'..(quality and quality.name or "normal")..'"'
                end
            end

            -- Add any warnings
            for _, warning in pairs(storage.utils.get_issues(entity) or {}) do
                table.insert(state.warnings, '"' .. warning .. '"')
            end

            -- Handle dimensions
            local prototype = prototypes.entity[entity.name]
            if prototype then
                local collision_box = prototype.collision_box
                state.dimensions = {
                    width = serialize_number(math.abs(collision_box.right_bottom.x - collision_box.left_top.x)),
                    height = serialize_number(math.abs(collision_box.right_bottom.y - collision_box.left_top.y))
                }
                state.tile_dimensions = {
                    tile_width = serialize_number(prototype.tile_width),
                    tile_height = serialize_number(prototype.tile_height)
                }
            end

            for name, define in pairs(inventory_defines) do
                local inventory = entity.get_inventory(define)
                if inventory then
                    state.inventories[name] = {}
                    -- Get contents with proper item names
                    local contents = storage.utils.get_contents_compat(inventory)
                    for item_name, count in pairs(contents) do
                        if item_name and item_name ~= "" then  -- Ensure valid item name
                            state.inventories[name][tostring(item_name)] = serialize_number(count)
                        end
                    end
                end
            end

            -- Handle fluids
            if entity.fluidbox then
                state.fluid_box = {}
                for i = 1, #entity.fluidbox do
                    local fluid = entity.fluidbox[i]
                    if fluid then
                        table.insert(state.fluid_box, {
                            name = '"' .. fluid.name .. '"',
                            amount = serialize_number(fluid.amount),
                            temperature = serialize_number(fluid.temperature)
                        })
                    end
                end
            end

            -- Handle burner state
            if entity.burner then
                -- Factorio 2.0: currently_burning may be a LuaItemPrototype userdata
                local burning_name = nil
                if entity.burner.currently_burning then
                    -- Try to get the name safely (could be userdata or table)
                    local ok, name = pcall(function()
                        return entity.burner.currently_burning.name
                    end)
                    if ok and name then
                        burning_name = '"' .. tostring(name) .. '"'
                    end
                end
                state.burner = {
                    currently_burning = burning_name,
                    remaining_burning_fuel = serialize_number(entity.burner.remaining_burning_fuel or 0),
                    heat = serialize_number(entity.burner.heat or 0)
                }

                -- Add burner inventory with proper item names
                local burner_inventory = entity.burner.inventory
                if burner_inventory then
                    state.burner.inventory = {}
                    local contents = storage.utils.get_contents_compat(burner_inventory)
                    --game.print("get_contents() results:")
                    for item_name, count in pairs(contents) do
                        if item_name and item_name ~= "" then  -- Ensure valid item name
                            --game.print("Item: '" .. tostring(item_name) .. "' Count: " .. tostring(count))
                            --state.burner.inventory['\"' .. tostring(item_name) .. '\"'] = serialize_number(count)
                            state.burner.inventory[tostring(item_name)] = serialize_number(count)
                        end
                    end
                end
            end

            -- Handle recipe - only for crafting machines and furnaces
            if (entity.type == "assembling-machine" or
                    entity.type == "furnace" or
                    entity.type == "rocket-silo") and
                    entity.get_recipe then
                local recipe = entity.get_recipe()
                if recipe then
                    state.recipe = storage.utils.serialize_recipe(recipe)
                end
            end

            -- Handle specific entity types
            --if entity.type == "transport-belt" then
            --    state.input_position = serialize_position(entity.position)
            --    state.output_position = serialize_position(entity.position)
            --    -- Add belt contents
            --    state.inventory = {}
            --    for name, count in pairs(entity.get_transport_line(1).get_contents()) do
            --        state.inventory[tostring(name)] = serialize_number(count)
            --    end
            if entity.type == "transport-belt" then
                --state.input_position = serialize_position(entity.input_position)
                --state.output_position = serialize_position(entity.output_position)
                state.position = serialize_position(entity.position)

                -- Store contents of each transport line separately
                state.transport_lines = {}

                -- Front line (line 1)
                state.transport_lines[1] = {}
                local contents1 = storage.utils.get_contents_compat(entity.get_transport_line(1))
                for name, count in pairs(contents1) do
                    state.transport_lines[1][tostring(name)] = serialize_number(count)
                end

                -- Back line (line 2)
                state.transport_lines[2] = {}
                local contents2 = storage.utils.get_contents_compat(entity.get_transport_line(2))
                for name, count in pairs(contents2) do
                    state.transport_lines[2][tostring(name)] = serialize_number(count)
                end

                -- Total counts (for backwards compatibility)
                state.inventory = {}
                for name, count in pairs(contents1) do
                    state.inventory[tostring(name)] = serialize_number(count)
                end
                for name, count in pairs(contents2) do
                    local existing = state.inventory[tostring(name)]
                    if existing then
                        state.inventory[tostring(name)] = serialize_number(tonumber(existing) + count)
                    else
                        state.inventory[tostring(name)] = serialize_number(count)
                    end
                end

            elseif entity.type == "inserter" then
                state.pickup_position = serialize_position(entity.pickup_position)
                state.drop_position = serialize_position(entity.drop_position)

            elseif entity.type == "splitter" then
                -- Calculate splitter positions based on orientation
                local x, y = entity.position.x, entity.position.y
                state.input_positions = {}
                state.output_positions = {}
                local lateral_offset = 0.5

                if entity.direction == defines.direction.north then
                    state.input_positions = {
                        serialize_position({x = x - lateral_offset, y = y + 1}),
                        serialize_position({x = x + lateral_offset, y = y + 1})
                    }
                    state.output_positions = {
                        serialize_position({x = x - lateral_offset, y = y - 1}),
                        serialize_position({x = x + lateral_offset, y = y - 1})
                    }
                elseif entity.direction == defines.direction.south then
                    state.input_positions = {
                        serialize_position({x = x + lateral_offset, y = y - 1}),
                        serialize_position({x = x - lateral_offset, y = y - 1})
                    }
                    state.output_positions = {
                        serialize_position({x = x + lateral_offset, y = y + 1}),
                        serialize_position({x = x - lateral_offset, y = y + 1})
                    }
                elseif entity.direction == defines.direction.east then
                    state.input_positions = {
                        serialize_position({x = x - 1, y = y - lateral_offset}),
                        serialize_position({x = x - 1, y = y + lateral_offset})
                    }
                    state.output_positions = {
                        serialize_position({x = x + 1, y = y - lateral_offset}),
                        serialize_position({x = x + 1, y = y + lateral_offset})
                    }
                elseif entity.direction == defines.direction.west then
                    state.input_positions = {
                        serialize_position({x = x + 1, y = y + lateral_offset}),
                        serialize_position({x = x + 1, y = y - lateral_offset})
                    }
                    state.output_positions = {
                        serialize_position({x = x - 1, y = y + lateral_offset}),
                        serialize_position({x = x - 1, y = y - lateral_offset})
                    }
                end

                -- Serialize splitter inventories
                state.inventory = {}
                for i = 1, 2 do
                    state.inventory[i] = {}
                    -- Factorio 2.0: Use compat wrapper for get_contents()
                    local contents = storage.utils.get_contents_compat(entity.get_transport_line(i))
                    for name, count in pairs(contents) do
                        state.inventory[i][tostring(name)] = serialize_number(count)
                    end
                end

            elseif entity.type == "mining-drill" then
                state.drop_position = serialize_position(entity.drop_position)

            elseif entity.type == "boiler" then
                -- Add connection points
                local x, y = entity.position.x, entity.position.y
                if entity.direction == defines.direction.north then
                    state.connection_points = {
                        serialize_position({x = x - 2, y = y + 0.5}),
                        serialize_position({x = x + 2, y = y + 0.5})
                    }
                    state.steam_output_point = serialize_position({x = x, y = y - 2})
                elseif entity.direction == defines.direction.south then
                    state.connection_points = {
                        serialize_position({x = x - 2, y = y - 0.5}),
                        serialize_position({x = x + 2, y = y - 0.5})
                    }
                    state.steam_output_point = serialize_position({x = x, y = y + 2})
                elseif entity.direction == defines.direction.east then
                    state.connection_points = {
                        serialize_position({x = x - 0.5, y = y - 2}),
                        serialize_position({x = x - 0.5, y = y + 2})
                    }
                    state.steam_output_point = serialize_position({x = x + 2, y = y})
                elseif entity.direction == defines.direction.west then
                    state.connection_points = {
                        serialize_position({x = x + 0.5, y = y - 2}),
                        serialize_position({x = x + 0.5, y = y + 2})
                    }
                    state.steam_output_point = serialize_position({x = x - 2, y = y})
                end
            end

            table.insert(entity_array, state)
        else
            -- Find the index of this character in storage.agent_characters
            agent_index = -1
            for idx, agent in pairs(storage.agent_characters) do
                if agent == entity then
                    agent_index = idx
                    break
                end
            end
            local state = {
                name = '"' .. entity.name .. '"',
                position = serialize_position(entity.position),
                direction = entity.direction,
                entity_number = entity.unit_number or -1,
                inventories = {},
                agent_index = agent_index,
                color = {
                    r = serialize_number(entity.color.r),
                    g = serialize_number(entity.color.g),
                    b = serialize_number(entity.color.b),
                    a = serialize_number(entity.color.a)
                }
            }
            -- Get the character's inventory using defines
            local inventory = entity.get_inventory(defines.inventory.character_main)

            if inventory then
                state.inventory = {}
                -- Factorio 2.0: Use compat wrapper for get_contents()
                local contents = storage.utils.get_contents_compat(inventory)
                for item_name, count in pairs(contents) do
                    if item_name and item_name ~= "" then
                        state.inventory[tostring(item_name)] = serialize_number(count)
                    end
                end
            end
            table.insert(entity_array, state)
        end
    end
    return entity_array
end
