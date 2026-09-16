local ITEM_INVENTORY_TYPES = {}
local item_inventory_type_seen = {}
local function add_inventory_type(inventory)
    if inventory ~= nil and not item_inventory_type_seen[inventory] then
        item_inventory_type_seen[inventory] = true
        ITEM_INVENTORY_TYPES[#ITEM_INVENTORY_TYPES + 1] = inventory
    end
end
add_inventory_type(defines.inventory.chest)
add_inventory_type(defines.inventory.furnace_source)
add_inventory_type(defines.inventory.furnace_result)
add_inventory_type(defines.inventory.assembling_machine_input)
add_inventory_type(defines.inventory.assembling_machine_output)
add_inventory_type(defines.inventory.crafter_input)
add_inventory_type(defines.inventory.crafter_output)
add_inventory_type(defines.inventory.rocket_silo_input)
add_inventory_type(defines.inventory.rocket_silo_output)
add_inventory_type(defines.inventory.rocket_silo_rocket)
add_inventory_type(defines.inventory.lab_input)
add_inventory_type(defines.inventory.fuel)
add_inventory_type(defines.inventory.burnt_result)
add_inventory_type(defines.inventory.item_main)
add_inventory_type(defines.inventory.robot_cargo)
add_inventory_type(defines.inventory.robot_repair)
add_inventory_type(defines.inventory.car_trunk)
add_inventory_type(defines.inventory.roboport_material)
add_inventory_type(defines.inventory.roboport_robot)
add_inventory_type(defines.inventory.artillery_turret_ammo)
add_inventory_type(defines.inventory.turret_ammo)
add_inventory_type(defines.inventory.beacon_modules)

local function entity_sort_key(entity)
    return entity.unit_number or math.huge
end

local function sort_entities(entities)
    table.sort(entities, function(a, b)
        local ua = entity_sort_key(a)
        local ub = entity_sort_key(b)
        if ua ~= ub then
            return ua < ub
        end
        if a.position.x ~= b.position.x then
            return a.position.x < b.position.x
        end
        if a.position.y ~= b.position.y then
            return a.position.y < b.position.y
        end
        return a.name < b.name
    end)
end

local OUTPUT_INVENTORY_BY_TYPE = {
    ["furnace"] = defines.inventory.furnace_result,
    ["assembling-machine"] = defines.inventory.assembling_machine_output,
    ["rocket-silo"] = defines.inventory.rocket_silo_output,
    ["container"] = defines.inventory.chest,
    ["logistic-container"] = defines.inventory.chest,
    ["car"] = defines.inventory.car_trunk,
    ["spider-vehicle"] = defines.inventory.spider_trunk,
    ["cargo-wagon"] = defines.inventory.cargo_wagon,
    ["agricultural-tower"] = defines.inventory.agricultural_tower_output,
    ["asteroid-collector"] = defines.inventory.asteroid_collector_output,
}

local function collect_matching_stacks(entity, matches, include_inputs)
    local stacks = {}
    local inventory_ids
    if include_inputs then
        inventory_ids = ITEM_INVENTORY_TYPES
    else
        local output_id = OUTPUT_INVENTORY_BY_TYPE[entity.type]
        inventory_ids = output_id ~= nil and {output_id} or {}
    end
    for _, inventory_id in ipairs(inventory_ids) do
        local ok, inventory = pcall(function()
            return entity.get_inventory(inventory_id)
        end)
        if ok and inventory then
            local contents = storage.utils.get_contents_compat(inventory)
            local names = {}
            for name in pairs(contents) do
                if matches(name) then
                    names[#names + 1] = name
                end
            end
            table.sort(names)
            for _, name in ipairs(names) do
                stacks[#stacks + 1] = {
                    name = name,
                    count = contents[name],
                    inventory = inventory,
                }
            end
        end
    end
    return stacks
end

storage.actions.extract_area = function(player_index, x1, y1, x2, y2, items, interaction_radius, max_entities, max_items, include_inputs)
    local player = storage.agent_characters[player_index]
    if not player then
        return {error = "Player not found"}
    end
    local surface = player.surface
    if not surface then
        return {error = "Player has no surface"}
    end

    max_entities = math.min(math.max(tonumber(max_entities) or 512, 1), 2048)
    max_items = math.min(math.max(tonumber(max_items) or 4096, 1), 1000000)
    interaction_radius = tonumber(interaction_radius) or 10

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

    local wanted = nil
    if type(items) == "table" and #items > 0 then
        wanted = {}
        for _, name in ipairs(items) do
            if type(name) == "string" and name ~= "" then
                wanted[name] = true
            end
        end
    end

    local function matches(name)
        return wanted == nil or wanted[name] == true
    end

    local entities = surface.find_entities_filtered{
        area = query_area, force = player.force
    }
    sort_entities(entities)

    local fast = storage.fast == true
    local scan_inputs = include_inputs == true
    local player_position = player.position
    local main_inventory = player.get_main_inventory()

    local extracted = {}
    local out_of_reach = {}
    local inventory_full = nil
    local scanned = 0
    local total_extracted = 0
    local truncated = false

    for index = 1, #entities do
        if scanned >= max_entities then
            truncated = true
            break
        end
        local entity = entities[index]
        scanned = scanned + 1
        if entity.valid and entity.type ~= "character" then
            local stacks = collect_matching_stacks(entity, matches, scan_inputs)
            if #stacks > 0 then
                local dx = entity.position.x - player_position.x
                local dy = entity.position.y - player_position.y
                if not fast and math.sqrt(dx * dx + dy * dy) > interaction_radius then
                    out_of_reach[#out_of_reach + 1] = {
                        name = entity.name,
                        position = {x = entity.position.x, y = entity.position.y},
                    }
                else
                    local stop = false
                    for _, stack in ipairs(stacks) do
                        local remaining = max_items - total_extracted
                        if remaining <= 0 then
                            truncated = true
                            stop = true
                            break
                        end
                        local take = math.min(stack.count, remaining)
                        if take < stack.count then
                            truncated = true
                        end
                        if take > 0 and not (main_inventory and main_inventory.can_insert({name = stack.name, count = take})) then
                            inventory_full = {
                                name = stack.name,
                                position = {x = entity.position.x, y = entity.position.y},
                            }
                            stop = true
                            break
                        end
                        if take > 0 then
                            local removed = stack.inventory.remove({name = stack.name, count = take})
                            local inserted = 0
                            if removed > 0 then
                                inserted = player.insert({name = stack.name, count = removed})
                                if inserted < removed then
                                    stack.inventory.insert({name = stack.name, count = removed - inserted})
                                    inventory_full = {
                                        name = stack.name,
                                        position = {x = entity.position.x, y = entity.position.y},
                                    }
                                end
                            end
                            if inserted > 0 then
                                extracted[stack.name] = (extracted[stack.name] or 0) + inserted
                                total_extracted = total_extracted + inserted
                            end
                            if inserted < removed then
                                stop = true
                                break
                            end
                        end
                    end
                    if stop then
                        break
                    end
                end
            end
        end
    end

    local status
    if inventory_full ~= nil then
        status = "inventory_full"
    elseif #out_of_reach > 0 or truncated then
        status = "partial"
    elseif total_extracted == 0 then
        status = "no_targets"
    else
        status = "completed"
    end

    return {
        status = status,
        area = {
            left = math.floor(left),
            top = math.floor(top),
            right = math.floor(right),
            bottom = math.floor(bottom),
        },
        scanned = scanned,
        extracted = extracted,
        out_of_reach = out_of_reach,
        inventory_full = inventory_full,
        truncated = truncated,
        tick = game.tick,
    }
end
