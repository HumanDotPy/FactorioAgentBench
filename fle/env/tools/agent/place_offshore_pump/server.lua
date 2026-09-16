local function is_water_tile(tile_name)
    return tile_name == "water" or
           tile_name == "deepwater" or
           tile_name == "water-green" or
           tile_name == "deepwater-green" or
           tile_name == "water-shallow" or
           tile_name == "water-mud"
end

local water_sides = {
    {dx = 0, dy = 1, direction = defines.direction.south},
    {dx = 1, dy = 0, direction = defines.direction.east},
    {dx = 0, dy = -1, direction = defines.direction.north},
    {dx = -1, dy = 0, direction = defines.direction.west},
}

local function ordered_water_sides(preferred_direction)
    if not preferred_direction then
        return water_sides
    end
    local ordered = {}
    for _, side in ipairs(water_sides) do
        if side.direction == preferred_direction then
            ordered[#ordered + 1] = side
        end
    end
    for _, side in ipairs(water_sides) do
        if side.direction ~= preferred_direction then
            ordered[#ordered + 1] = side
        end
    end
    return ordered
end

storage.utils.find_offshore_pump_position = function(player, center_pos, preferred_direction)
    local reach = player.reach_distance or player.build_distance or 10
    local max_radius = math.min(20, math.ceil(reach))
    local sides = ordered_water_sides(preferred_direction)

    for radius = 1, max_radius do
        for y = -radius, radius do
            for x = -radius, radius do
                if math.abs(x) == radius or math.abs(y) == radius then
                    local check_pos = {x = center_pos.x + x, y = center_pos.y + y}
                    local dx = check_pos.x - player.position.x
                    local dy = check_pos.y - player.position.y
                    if math.sqrt(dx * dx + dy * dy) <= reach then
                        local current_tile = player.surface.get_tile(check_pos.x, check_pos.y)
                        if not is_water_tile(current_tile.name) then
                            local entities = player.surface.find_entities_filtered{
                                position = check_pos,
                                collision_mask = "player",
                            }
                            if #entities == 0 then
                                for _, side in ipairs(sides) do
                                    local water_pos = {
                                        x = check_pos.x + side.dx,
                                        y = check_pos.y + side.dy,
                                    }
                                    local adjacent_tile = player.surface.get_tile(water_pos.x, water_pos.y)
                                    if is_water_tile(adjacent_tile.name) then
                                        local placement = {
                                            name = "offshore-pump",
                                            position = check_pos,
                                            direction = side.direction,
                                            force = player.force,
                                            build_check_type = defines.build_check_type.manual,
                                        }
                                        if player.surface.can_place_entity(placement) then
                                            return {
                                                position = check_pos,
                                                direction = side.direction,
                                            }
                                        end
                                    end
                                end
                            end
                        end
                    end
                end
            end
        end
    end

    return nil
end

storage.actions.place_offshore_pump = function(player_index, x, y, direction)
    local player = storage.utils.ensure_valid_character(player_index)
    local preferred = {x = x, y = y}

    if prototypes.entity["offshore-pump"] == nil then
        error("\"offshore-pump isn't something that exists. Did you make a typo?\"")
    end

    if player.get_item_count("offshore-pump") == 0 then
        local inv_contents = storage.utils.format_inventory_for_error(player)
        error("\"No offshore-pump in inventory. Current inventory: " .. inv_contents .. "\"")
    end

    if direction == nil then
        direction = defines.direction.north
    end

    local found = storage.utils.find_offshore_pump_position(player, preferred, direction)
    if not found then
        error("\"No shoreline position for the offshore pump is within reach of (" ..
              preferred.x .. ", " .. preferred.y .. "). Move closer to water and retry.\"")
    end

    local built = player.surface.create_entity{
        name = "offshore-pump",
        position = found.position,
        direction = found.direction,
        force = player.force,
        raise_built = true,
    }
    if not built then
        error("\"The engine rejected the offshore pump placement at (" ..
              found.position.x .. ", " .. found.position.y .. ").\"")
    end

    player.remove_item{name = "offshore-pump", count = 1}
    local serialized = storage.utils.serialize_entity(built)
    return storage.utils.attach_connection_report(serialized, built, player)
end
