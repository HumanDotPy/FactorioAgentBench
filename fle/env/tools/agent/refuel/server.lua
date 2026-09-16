local function fuelable_error(entity)
    return "\"" .. entity.name .. " (type " .. entity.type
        .. ") has no fuel slot; only burner machines and vehicles are fuelable: "
        .. "burner inserter, burner mining drill, stone/steel furnace, boiler, "
        .. "burner generator, car, tank, locomotive\""
end

local function inventory_space(inventory, item_name)
    local item_prototype = prototypes.item[item_name]
    local stack_size = (item_prototype and item_prototype.stack_size) or 1
    local space = 0
    for index = 1, #inventory do
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

storage.actions.refuel = function(player_index, x, y, target_name)
    local player = storage.utils.ensure_valid_character(player_index)
    local position = {x=x, y=y}
    local surface = player.surface
    local area = {{position.x - 1, position.y - 1}, {position.x + 1, position.y + 1}}
    local buildings = nil

    if target_name then
        buildings = surface.find_entities_filtered{area = area, name = target_name}
    else
        buildings = surface.find_entities_filtered{area = area}
    end

    local closest_distance = math.huge
    local closest_entity = nil
    local nearest_non_fuel = nil
    local nearest_non_fuel_distance = math.huge
    for _, building in ipairs(buildings) do
        if building.name ~= "character" and building.valid then
            local distance = ((position.x - building.position.x) ^ 2
                + (position.y - building.position.y) ^ 2) ^ 0.5
            local fuel_inventory = building.get_inventory
                and building.get_inventory(defines.inventory.fuel)
            if fuel_inventory then
                if distance < closest_distance then
                    closest_distance = distance
                    closest_entity = building
                end
            elseif distance < nearest_non_fuel_distance then
                nearest_non_fuel_distance = distance
                nearest_non_fuel = building
            end
        end
    end

    if closest_entity == nil then
        if nearest_non_fuel then
            error(fuelable_error(nearest_non_fuel))
        elseif target_name then
            error("\"Could not find a valid " .. target_name .. " entity at ("
                .. position.x .. ", " .. position.y .. ")\"")
        else
            error("\"Could not find any entity at (" .. position.x .. ", "
                .. position.y .. ")\"")
        end
    end

    if not storage.fast and closest_distance > 10 then
        error("\"Entity at (" .. closest_entity.position.x .. ", "
            .. closest_entity.position.y
            .. ") is too far away from your position of (" .. player.position.x
            .. ", " .. player.position.y .. "), move closer.\"")
    end

    local fuel_inventory = closest_entity.get_inventory(defines.inventory.fuel)

    local existing_name = nil
    for index = 1, #fuel_inventory do
        local stack = fuel_inventory[index]
        if stack and stack.valid_for_read then
            existing_name = stack.name
            break
        end
    end

    local candidates = {}
    local candidate_order = {}
    local main_inventory = player.get_main_inventory()
    if main_inventory then
        for index = 1, #main_inventory do
            local stack = main_inventory[index]
            if stack and stack.valid_for_read then
                local item_prototype = prototypes.item[stack.name]
                local fuel_value = (item_prototype and (item_prototype.fuel_value or 0)) or 0
                if fuel_value > 0 then
                    local entry = candidates[stack.name]
                    if not entry then
                        entry = {name = stack.name, fuel_value = fuel_value, count = 0}
                        candidates[stack.name] = entry
                        candidate_order[#candidate_order + 1] = entry
                    end
                    entry.count = entry.count + stack.count
                end
            end
        end
    end

    local fuel_name = existing_name
    local available = 0
    local remaining_fuel = 0
    local inserted = 0
    local status = nil

    if existing_name then
        local chosen = candidates[existing_name]
        if chosen == nil then
            status = "fuel_mismatch"
            remaining_fuel = inventory_space(fuel_inventory, existing_name)
        else
            available = chosen.count
            local capacity = inventory_space(fuel_inventory, chosen.name)
            if capacity <= 0 then
                status = "fuel_full"
            else
                inserted = fuel_inventory.insert{
                    name = chosen.name, count = math.min(chosen.count, capacity)
                }
                if inserted > 0 then
                    player.remove_item{name = chosen.name, count = inserted}
                    status = "refueled"
                else
                    status = "blocked"
                end
                remaining_fuel = math.max(capacity - inserted, 0)
            end
        end
    elseif #candidate_order == 0 then
        status = "no_fuel"
    else
        table.sort(candidate_order, function(a, b)
            if a.fuel_value ~= b.fuel_value then
                return a.fuel_value > b.fuel_value
            end
            return a.count > b.count
        end)
        for _, entry in ipairs(candidate_order) do
            if fuel_name == nil then
                fuel_name = entry.name
                available = entry.count
            end
            local capacity = inventory_space(fuel_inventory, entry.name)
            if capacity > 0 then
                inserted = fuel_inventory.insert{
                    name = entry.name, count = math.min(entry.count, capacity)
                }
                if inserted > 0 then
                    player.remove_item{name = entry.name, count = inserted}
                    fuel_name = entry.name
                    available = entry.count
                    remaining_fuel = math.max(capacity - inserted, 0)
                    status = "refueled"
                    break
                end
            end
        end
        if status == nil then
            status = "blocked"
        end
    end

    return {
        status = status,
        entity = storage.utils.serialize_entity(closest_entity),
        fuel = fuel_name,
        inserted = inserted,
        remaining_fuel = remaining_fuel,
        available = available,
    }
end
