-- Factorio 2.0.77 inventory names whose contents can be extracted. The list is
-- built once at load. Build it through `add` so a renamed/removed define cannot
-- become a nil hole and dedupe ids so each inventory is read once per entity.
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
add_inventory_type(defines.inventory.fuel)
add_inventory_type(defines.inventory.burnt_result)
add_inventory_type(defines.inventory.lab_input)
add_inventory_type(defines.inventory.item_main)  -- cargo wagons and item entities
add_inventory_type(defines.inventory.robot_cargo)
add_inventory_type(defines.inventory.robot_repair)
add_inventory_type(defines.inventory.car_trunk)
add_inventory_type(defines.inventory.roboport_material)
add_inventory_type(defines.inventory.roboport_robot)
add_inventory_type(defines.inventory.artillery_turret_ammo)
add_inventory_type(defines.inventory.turret_ammo)
add_inventory_type(defines.inventory.beacon_modules)
add_inventory_type(defines.inventory.character_main)
add_inventory_type(defines.inventory.character_guns)
add_inventory_type(defines.inventory.character_ammo)
add_inventory_type(defines.inventory.character_armor)
add_inventory_type(defines.inventory.character_vehicle)
add_inventory_type(defines.inventory.character_trash)

-- Helper function to check all possible inventories of an entity
local function get_entity_item_count(entity, item_name)
    local total_count = 0
    for _, inv_type in ipairs(ITEM_INVENTORY_TYPES) do
        local inventory = entity.get_inventory(inv_type)
        if inventory then
            total_count = total_count + inventory.get_item_count(item_name)
        end
    end
    return total_count
end

-- Helper function to remove items from any valid inventory
local function remove_items_from_entity(entity, stack)
    local items_remaining = stack.count
    local total_removed = 0

    for _, inv_type in ipairs(ITEM_INVENTORY_TYPES) do
        if items_remaining <= 0 then
            break
        end

        local inventory = entity.get_inventory(inv_type)
        if inventory then
            local current_stack = {name = stack.name, count = items_remaining}
            local removed = inventory.remove(current_stack)
            total_removed = total_removed + removed
            items_remaining = items_remaining - removed
        end
    end

    return total_removed
end

storage.actions.extract_item = function(player_index, extract_item, count, x, y, source_name)
    -- Ensure we have a valid character, recreating if necessary
    local player = storage.utils.ensure_valid_character(player_index)
    local position = {x=x, y=y}
    local surface = player.surface

    -- First validate the request
    if count <= 0 then
        error("\"Invalid count: must be greater than 0\"")
    end

    local target_radius = 2.5
    local buildings = nil

    if source_name ~= nil then
        buildings = surface.find_entities_filtered{
            position = position,
            radius = target_radius,
            name = source_name
        }
    else
        buildings = surface.find_entities_filtered{
            position = position,
            radius = target_radius
        }
    end

    local closest_distance = math.huge
    local closest_entity = nil

    for _, building in ipairs(buildings) do
        if building.name ~= 'character' and building.valid then
            local item_count = get_entity_item_count(building, extract_item)
            if item_count > 0 then
                local dx = position.x - building.position.x
                local dy = position.y - building.position.y
                local distance = math.sqrt(dx * dx + dy * dy)
                if distance < closest_distance then
                    closest_distance = distance
                    closest_entity = building
                end
            end
        end
    end

    -- Error handling in priority order

    if #buildings == 0 then
        if source_name then
            error("\"Could not find a valid "..source_name.." entity at ("
                ..position.x..", "..position.y..")\"")
        else
            error("\"Could not find any entities at ("..position.x..", "..position.y..")\"")
        end
    end

    if not closest_entity then
        if source_name then
            error("\"Could not find a valid "..source_name.." entity containing "
                .. extract_item.." at ("..position.x..", "..position.y..")\"")
        else
            error("\"Could not find a valid entity containing " .. extract_item
                .. " at ("..position.x..", "..position.y..")\"")
        end
    end

    if not storage.fast then
        local reach = 10
        local pdx = player.position.x - closest_entity.position.x
        local pdy = player.position.y - closest_entity.position.y
        if math.sqrt(pdx * pdx + pdy * pdy) > reach then
            error("\"Entity at ("..closest_entity.position.x..", "..closest_entity.position.y
                ..") is too far away from your position of ("..player.position.x..","
                ..player.position.y.."), move closer.\"")
        end
    end

    -- Calculate how many items we can actually extract
    local available_count = get_entity_item_count(closest_entity, extract_item)
    local extract_count = math.min(count, available_count)

    local main_inventory = player.get_main_inventory()
    if main_inventory and main_inventory.can_insert
        and not main_inventory.can_insert({name = extract_item, count = extract_count})
    then
        local low, high = 0, extract_count
        while low < high do
            local middle = math.floor((low + high + 1) / 2)
            if main_inventory.can_insert({name = extract_item, count = middle}) then
                low = middle
            else
                high = middle - 1
            end
        end
        extract_count = low
    end

    if extract_count <= 0 then
        error("\"Inventory has no room for " .. extract_item .. "\"")
    end

    local inserted = player.insert{name=extract_item, count=extract_count}
    if inserted <= 0 then
        error("\"Inventory has no room for " .. extract_item .. "\"")
    end

    local number_extracted = remove_items_from_entity(closest_entity,
        {name=extract_item, count=inserted})
    if number_extracted < inserted then
        player.remove_item{name=extract_item, count=inserted - number_extracted}
    end

    if number_extracted > 0 then
        return number_extracted
    end
    error("\"Failed to extract " .. extract_item .. "\"")
end
