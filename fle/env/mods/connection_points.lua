local function offset_positions(x, y, offsets)
    local positions = {}
    for _, offset in ipairs(offsets) do
        positions[#positions + 1] = {x = x + offset[1], y = y + offset[2]}
    end
    return positions
end

local function flatten(groups)
    local positions = {}
    for _, group in ipairs(groups) do
        for _, position in ipairs(group) do
            positions[#positions + 1] = position
        end
    end
    return positions
end

local storage_tank_offsets = {
    [defines.direction.north] = {{-2, -1}, {-1, -2}, {1, 2}, {2, 1}},
    [defines.direction.south] = {{-2, -1}, {-1, -2}, {1, 2}, {2, 1}},
    [defines.direction.east] = {{-2, 1}, {-1, 2}, {1, -2}, {2, -1}},
    [defines.direction.west] = {{-2, 1}, {-1, 2}, {1, -2}, {2, -1}},
}

storage.utils.get_storage_tank_connection_points = function(entity)
    local offsets = storage_tank_offsets[entity.direction]
        or storage_tank_offsets[defines.direction.north]
    return offset_positions(entity.position.x, entity.position.y, offsets)
end

local chemical_plant_offsets = {
    [defines.direction.north] = {
        {{-1, -2}, {1, -2}},
        {{-1, 2}, {1, 2}},
    },
    [defines.direction.east] = {
        {{2, -1}, {2, 1}},
        {{-2, -1}, {-2, 1}},
    },
    [defines.direction.south] = {
        {{-1, 2}, {1, 2}},
        {{-1, -2}, {1, -2}},
    },
    [defines.direction.west] = {
        {{-2, -1}, {-2, 1}},
        {{2, -1}, {2, 1}},
    },
}

storage.utils.get_chemical_plant_connection_points = function(plant)
    local groups = chemical_plant_offsets[plant.direction]
        or chemical_plant_offsets[defines.direction.north]
    return offset_positions(plant.position.x, plant.position.y, flatten(groups))
end

local boiler_offsets = {
    [defines.direction.north] = {{-2, 0.5}, {2, 0.5}, {0, -1.5}},
    [defines.direction.south] = {{-2, -0.5}, {2, -0.5}, {0, 1.5}},
    [defines.direction.east] = {{-0.5, -2}, {-0.5, 2}, {1.5, 0}},
    [defines.direction.west] = {{0.5, -2}, {0.5, 2}, {-1.5, 0}},
}

storage.utils.get_heat_exchanger_connection_points = function(entity)
    local offsets = boiler_offsets[entity.direction]
        or boiler_offsets[defines.direction.north]
    return offset_positions(entity.position.x, entity.position.y, offsets)
end

storage.utils.get_boiler_connection_points = function(entity)
    local offsets = boiler_offsets[entity.direction]
        or boiler_offsets[defines.direction.north]
    return offset_positions(entity.position.x, entity.position.y, offsets)
end

local generator_axis_offsets = {
    [defines.direction.north] = {{0, -3}, {0, 3}},
    [defines.direction.south] = {{0, -3}, {0, 3}},
    [defines.direction.east] = {{-3, 0}, {3, 0}},
    [defines.direction.west] = {{-3, 0}, {3, 0}},
}

storage.utils.get_generator_connection_positions = function(entity)
    local offsets = generator_axis_offsets[entity.direction]
        or generator_axis_offsets[defines.direction.north]
    return offset_positions(entity.position.x, entity.position.y, offsets)
end

local pumpjack_offsets = {
    [defines.direction.north] = {{1, -2}},
    [defines.direction.east] = {{2, -1}},
    [defines.direction.south] = {{-1, 2}},
    [defines.direction.west] = {{-2, 1}},
}

storage.utils.get_pumpjack_connection_points = function(entity)
    local offsets = pumpjack_offsets[entity.direction]
        or pumpjack_offsets[defines.direction.north]
    return offset_positions(entity.position.x, entity.position.y, offsets)
end

local offshore_pump_output_offsets = {
    [defines.direction.north] = {{0, 1}},
    [defines.direction.south] = {{0, -1}},
    [defines.direction.east] = {{-1, 0}},
    [defines.direction.west] = {{1, 0}},
}

storage.utils.get_offshore_pump_connection_points = function(entity)
    local offsets = offshore_pump_output_offsets[entity.direction]
        or offshore_pump_output_offsets[defines.direction.north]
    return offset_positions(entity.position.x, entity.position.y, offsets)
end

local refinery_offsets = {
    [defines.direction.north] = {
        {{-1, 3}, {1, 3}},
        {{-2, -3}, {0, -3}, {2, -3}},
    },
    [defines.direction.south] = {
        {{-1, -3}, {1, -3}},
        {{-2, 3}, {0, 3}, {2, 3}},
    },
    [defines.direction.east] = {
        {{-3, -1}, {-3, 1}},
        {{3, -2}, {3, 0}, {3, 2}},
    },
    [defines.direction.west] = {
        {{3, -1}, {3, 1}},
        {{-3, -2}, {-3, 0}, {-3, 2}},
    },
}

storage.utils.get_refinery_connection_points = function(refinery)
    local groups = refinery_offsets[refinery.direction]
        or refinery_offsets[defines.direction.north]
    return offset_positions(refinery.position.x, refinery.position.y, flatten(groups))
end

local pipe_to_ground_offsets = {
    [defines.direction.north] = {{0, -1}},
    [defines.direction.south] = {{0, 1}},
    [defines.direction.east] = {{1, 0}},
    [defines.direction.west] = {{-1, 0}},
}

storage.utils.get_pipe_to_ground_connection_points = function(entity)
    local offsets = pipe_to_ground_offsets[entity.direction]
        or pipe_to_ground_offsets[defines.direction.north]
    return offset_positions(entity.position.x, entity.position.y, offsets)
end

local pump_offsets = {
    [defines.direction.north] = {{0, -1.5}, {0, 1.5}},
    [defines.direction.south] = {{0, -1.5}, {0, 1.5}},
    [defines.direction.east] = {{-1.5, 0}, {1.5, 0}},
    [defines.direction.west] = {{-1.5, 0}, {1.5, 0}},
}

storage.utils.get_pump_connection_points = function(entity)
    local offsets = pump_offsets[entity.direction]
        or pump_offsets[defines.direction.north]
    return offset_positions(entity.position.x, entity.position.y, offsets)
end
