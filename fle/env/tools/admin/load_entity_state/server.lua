-- Helper function to unquote strings
local function unquote_string(str)
    if not str then return nil end
    return (string.gsub(str, '"', ''))
end

-- Main deserialization function
storage.actions.load_entity_state = function(player, stored_json_data)
    local player_entity = storage.agent_characters[player]
    local surface = player_entity.surface
    local created_entities = {}
    local stored_data = helpers.json_to_table(stored_json_data)
    local character_states = {}
    local blueprint_overlays = {}
    local old_positions = {}
    local leftover_items = {}
    -- Snapshot characters are replaced after the factory. They must not block
    -- native revival at a spawn tile now occupied by the saved factory.
    for _,state in pairs(stored_data) do
        if unquote_string(state.name) == "character" then
            local index=state.agent_index
            local old=index and storage.agent_characters[index]
            if old and old.valid then
                old_positions[index]=old.position
                old.destroy()
                storage.agent_characters[index]=nil
            end
        end
    end
    for _,state in pairs(stored_data) do
        if unquote_string(state.name) == "fle-blueprint-overlay" then
            table.insert(blueprint_overlays,state)
        end
    end
    for _, overlay in ipairs(blueprint_overlays) do
        local inventory=game.create_inventory(1)
        local ok,err=pcall(function()
            local stack=inventory[1]; stack.set_stack{name="blueprint"}
            if stack.import_stack(unquote_string(overlay.content)) ~= 0 then
                error("Invalid pending-construction checkpoint blueprint")
            end
            local ghosts=stack.build_blueprint{surface=surface,force=game.forces.player,
                position={x=tonumber(overlay.position.x),y=tonumber(overlay.position.y)},
                build_mode=defines.build_mode.forced,skip_fog_of_war=false}
            local pending_tiles={}
            for _,position in ipairs(overlay.pending_tiles or {}) do
                pending_tiles[math.floor(position.x)..","..math.floor(position.y)]=true
            end
            for _,ghost in ipairs(ghosts) do
                if ghost.valid and ghost.type == "tile-ghost" then
                    local key=math.floor(ghost.position.x)..","..math.floor(ghost.position.y)
                    if not pending_tiles[key] then ghost.revive() end
                end
            end
        end)
        inventory.destroy()
        if not ok then error(err) end
    end
    -- Rails and foundations must exist before rolling stock is revived.
    local function rolling(state)
        local kind=unquote_string(state.type)
        return kind=="locomotive" or kind=="cargo-wagon" or kind=="fluid-wagon" or kind=="artillery-wagon"
    end
    table.sort(stored_data,function(a,b) return not rolling(a) and rolling(b) end)
    -- First pass: Create all non-character entities and store character states
    for _, state in pairs(stored_data) do
        local name = unquote_string(state.name)

        if name == "fle-blueprint-overlay" then
            -- The design was restored before physical entities.
        elseif name == "character" then
            table.insert(character_states, state)
        elseif name == "item-on-ground" then
            local item_name = unquote_string(state.type)
            local item_count = tonumber(state.count)

            if prototypes.item[item_name] then
                local entity = surface.create_entity({
                    name = name,
                    position = {
                        x = tonumber(state.position.x),
                        y = tonumber(state.position.y)
                    },
                    stack = {
                        name = item_name,
                        count = item_count
                    },
                    force = game.forces.player
                })
            else
                -- game.print("Warning: Unknown item type " .. item_name)
            end
        elseif state.type == "simple-entity-with-owner" then
            -- Do nothing, we don't want to load in placeholder entities if they were somehow persisted!
        else
            local entity
            local position={x=tonumber(state.position.x),y=tonumber(state.position.y)}
            for _,ghost in ipairs(surface.find_entities_filtered{
                type="entity-ghost",ghost_name=name,position=position,force=game.forces.player}) do
                if ghost.position.x==position.x and ghost.position.y==position.y then
                    local _,revived=ghost.revive{raise_revive=true}
                    if not revived then error("Could not restore blueprint entity "..name) end
                    entity=revived
                    break
                end
            end
            if not entity then
                entity = surface.create_entity({
                    name = name,
                    position = position,
                    direction = tonumber(state.direction),
                    force = game.forces.player,
                    raise_built = true
                })
            end

            if entity then
                created_entities[state.entity_number] = {
                    entity = entity,
                    state = state
                }
            end
        end
    end

    -- Handle characters separately
    for _, character_state in ipairs(character_states) do
        -- Store old character position if it exists
        local agent_index = character_state.agent_index
        local old_position = old_positions[agent_index]
        local old_character = nil

        -- If we have a valid agent_index, get the old character from storage.agent_characters
        if agent_index and agent_index > 0 and storage.agent_characters[agent_index] then
            old_character = storage.agent_characters[agent_index]
            if old_character then
                old_position = old_character.position
                old_character.destroy()
            end
        end

        -- Create new character at the stored position or old position
        local position = {
            x = tonumber(character_state.position.x),
            y = tonumber(character_state.position.y)
        }
        if not surface.can_place_entity{name="character", position=position} then
            position = old_position or {x=0, y=0}
        end

        local new_character = surface.create_entity({
            name = "character",
            position = position,
            direction = tonumber(character_state.direction),
            force = game.forces.player,
        })

        if new_character then
            -- Update storage.agent_characters if we have a valid agent_index
            if agent_index and agent_index > 0 then
                storage.agent_characters[agent_index] = new_character
            end

            -- Restore character color if it exists
            if character_state.color then
                new_character.color = {
                    r = tonumber(character_state.color.r),
                    g = tonumber(character_state.color.g),
                    b = tonumber(character_state.color.b),
                    a = tonumber(character_state.color.a)
                }
            end

            -- Restore character inventory
            if character_state.inventory then
                local main_inventory = new_character.get_inventory(defines.inventory.character_main)
                if main_inventory then
                    for item_name, count in pairs(character_state.inventory) do
                        -- Remove quotes if they exist
                        item_name = unquote_string(item_name)
                        if item_name and item_name ~= "" then
                            if prototypes.item[item_name] then
                                main_inventory.insert({
                                    name = item_name,
                                    count = tonumber(count)
                                })
                            else
                                -- game.print("Warning: Unknown item " .. item_name)
                            end
                        end
                    end
                else
                    -- game.print("Warning: Could not get character main inventory")
                end
            end

            -- Add character to created_entities for inventory restoration
            created_entities[character_state.entity_number] = {
                entity = new_character,
                state = character_state
            }
        end
    end

    -- Second pass: Restore states
    for unit_number, data in pairs(created_entities) do
        local entity = data.entity
        local state = data.state
        local entity_type = entity.type

        -- game.print("Processing entity: " .. entity.name .. " (type: " .. entity_type .. ")")

        -- Restore recipe - only for entities that can have recipes
        if state.recipe then
            -- Only try to set recipe on appropriate entity types
            if (entity.type == "assembling-machine" or
                entity.type == "furnace" or
                entity.type == "rocket-silo") and
               entity.get_recipe then  -- Double check entity supports recipes

                local recipe_name = unquote_string(state.recipe.name)
                if prototypes.recipe[recipe_name] then
                    -- game.print("Setting recipe " .. recipe_name .. " on " .. entity.name)
                    pcall(function()
                        entity.set_recipe(recipe_name)
                    end)
                else
                    -- game.print("Warning: Unknown recipe " .. recipe_name)
                end
            else
                -- game.print("Warning: Skipping recipe for incompatible entity type: " .. entity.type)
            end
        end

        -- Restore inventories based on entity type
        for inv_name, contents in pairs(state.inventories or {}) do
            local inventory = nil

            -- Only try to access inventories that match the entity type (Factorio 2.0: unified crafter_* defines)
            if inv_name == "chest" and (entity_type == "container" or entity_type == "logistic-container") then
                inventory = entity.get_inventory(defines.inventory.chest)
            elseif inv_name == "crafter_input" and (entity_type == "furnace" or entity_type == "assembling-machine" or entity_type == "rocket-silo") then
                inventory = entity.get_inventory(defines.inventory.crafter_input)
            elseif inv_name == "crafter_output" and (entity_type == "furnace" or entity_type == "assembling-machine" or entity_type == "rocket-silo") then
                inventory = entity.get_inventory(defines.inventory.crafter_output)
            elseif inv_name == "fuel" and entity.burner then
                inventory = entity.get_inventory(defines.inventory.fuel)
            elseif inv_name == "burnt_result" and entity.burner then
                inventory = entity.get_inventory(defines.inventory.burnt_result)
            elseif inv_name == "turret_ammo" and entity_type == "ammo-turret" then
                inventory = entity.get_inventory(defines.inventory.turret_ammo)
            elseif inv_name == "lab_input" and entity_type == "lab" then
                inventory = entity.get_inventory(defines.inventory.lab_input)
            elseif inv_name == "lab_modules" and entity_type == "lab" then
                inventory = entity.get_module_inventory()
            elseif inv_name == "crafter_modules" and (entity_type == "assembling-machine" or entity_type == "furnace" or entity_type == "rocket-silo") then
                inventory = entity.get_module_inventory()
            elseif inv_name == "roboport_robot" and entity_type == "roboport" then
                inventory = entity.get_inventory(defines.inventory.roboport_robot)
            elseif inv_name == "roboport_material" and entity_type == "roboport" then
                inventory = entity.get_inventory(defines.inventory.roboport_material)
            elseif inv_name == "robot_cargo" and (entity_type == "construction-robot" or entity_type == "logistic-robot") then
                inventory = entity.get_inventory(defines.inventory.robot_cargo)
            end

            if inventory then
                -- game.print("Found valid inventory for " .. inv_name)
                for quoted_item_name, count in pairs(contents) do
                    local item_name = unquote_string(quoted_item_name)
                    if item_name and item_name ~= "" then
                        if prototypes.item[item_name] then
                            -- game.print("Inserting " .. count .. " " .. item_name)
                            inventory.insert({
                                name = item_name,
                                count = tonumber(count)
                            })
                        else
                            -- game.print("Warning: Unknown item " .. item_name)
                        end
                    else
                        -- game.print("Warning: Empty item name in " .. inv_name)
                    end
                end
            else
                -- game.print("No valid inventory found for " .. inv_name)
            end
        end

        -- Restore burner
        if state.burner and entity.burner then
            if state.burner.currently_burning then
                local burning_name = unquote_string(state.burner.currently_burning)
                if prototypes.item[burning_name] then  -- Verify burning item exists
                    entity.burner.currently_burning = prototypes.item[burning_name]
                    entity.burner.remaining_burning_fuel = tonumber(state.burner.remaining_burning_fuel)
                    entity.burner.heat = tonumber(state.burner.heat)
                else
                    -- game.print("Warning: Unknown burning item " .. burning_name)
                end
            end
        end

        -- Restore transport belt contents
        if entity_type == "transport-belt" and state.transport_lines then
            local function restore_transport_line(line, contents, line_index)
                if not line then return end
                for item_name, count in pairs(contents or {}) do
                    local name = unquote_string(item_name)
                    local item_count = tonumber(count)
                    if name and item_count and item_count > 0
                        and prototypes.item[name] then
                        local inserted = 0
                        while inserted < item_count do
                            local position = inserted / item_count
                            local ok, accepted = pcall(function()
                                return line.insert_at(position, {
                                    name = name,
                                    count = 1
                                })
                            end)
                            if not ok or accepted ~= true then break end
                            inserted = inserted + 1
                        end
                        if inserted < item_count then
                            table.insert(leftover_items, {
                                entity_id = entity.unit_number,
                                line = line_index,
                                name = name,
                                count = item_count - inserted,
                            })
                        end
                    end
                end
            end
            restore_transport_line(
                entity.get_transport_line(1), state.transport_lines["1"], 1)
            restore_transport_line(
                entity.get_transport_line(2), state.transport_lines["2"], 2)
        end

        -- Restore energy and active state
        if state.energy then
            entity.energy = tonumber(state.energy)
        end
        if state.active ~= nil then
            entity.active = state.active
        end
    end

    for _,data in pairs(created_entities) do
        local entity,state=data.entity,data.state
        if entity.valid then
            if state.deconstruction then entity.order_deconstruction(entity.force) end
            if state.upgrade_target then
                entity.order_upgrade{force=entity.force,target={
                    name=unquote_string(state.upgrade_target),
                    quality=unquote_string(state.upgrade_quality) or "normal"}}
            end
        end
    end
    if #leftover_items > 0 then
        return {restored = true, leftover = leftover_items}
    end
    return true
end
