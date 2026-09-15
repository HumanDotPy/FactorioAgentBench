-- Add this function to analyze cliff neighborhoods
function analyze_cliff_orientation(entity, surface)
    if not entity or not entity.valid then
        return "west-to-east"
    end

    local pos = entity.position

    -- Check for cliff neighbors in 8 directions
    local neighbors = {}
    local directions = {
        {name = "n", dx = 0, dy = -1},
        {name = "ne", dx = 1, dy = -1},
        {name = "e", dx = 1, dy = 0},
        {name = "se", dx = 1, dy = 1},
        {name = "s", dx = 0, dy = 1},
        {name = "sw", dx = -1, dy = 1},
        {name = "w", dx = -1, dy = 0},
        {name = "nw", dx = -1, dy = -1}
    }

    -- Track which positions we've already confirmed as having cliffs
    local checked_positions = {}

    -- Store the entity's unit number for comparison
    local current_unit_number = entity.valid and entity.unit_number or nil

    for _, dir in ipairs(directions) do
        local check_pos = {x = pos.x + dir.dx*2, y = pos.y + dir.dy*2}
        local pos_key = check_pos.x .. "," .. check_pos.y

        -- Skip if we've already checked this position
        if not checked_positions[pos_key] then
            local area = {
                left_top = {x = check_pos.x - 0.1, y = check_pos.y - 0.1},
                right_bottom = {x = check_pos.x + 0.1, y = check_pos.y + 0.1}
            }

            local found_cliffs = surface.find_entities_filtered{
                area = area,
                type = "cliff"
            }

            -- Check if any of the found cliffs are NOT the current entity
            local has_neighbor = false
            for _, cliff in ipairs(found_cliffs) do
                if cliff.valid and cliff.unit_number ~= current_unit_number then
                    has_neighbor = true
                    break
                end
            end

            neighbors[dir.name] = has_neighbor
            checked_positions[pos_key] = has_neighbor
        else
            -- Use the cached result
            neighbors[dir.name] = checked_positions[pos_key]
        end
    end

    -- Count neighbors
    local neighbor_count = 0
    for _, has_neighbor in pairs(neighbors) do
        if has_neighbor then
            neighbor_count = neighbor_count + 1
        end
    end

    -- Determine orientation based on neighbor pattern
    local orientation = "west-to-east" -- default

    -- End pieces (1 neighbor)
    if neighbor_count == 1 then
        if neighbors.n then
            orientation = "south-to-none"
        elseif neighbors.s then
            orientation = "north-to-none"
        elseif neighbors.e then
            orientation = "west-to-none"
        elseif neighbors.w then
            orientation = "east-to-none"
        elseif neighbors.ne then
            orientation = "south-to-none"
        elseif neighbors.se then
            orientation = "north-to-none"
        elseif neighbors.sw then
            orientation = "north-to-none"
        elseif neighbors.nw then
            orientation = "south-to-none"
        end
    -- Straight pieces (2 neighbors on opposite sides)
    elseif neighbor_count == 2 then
        if neighbors.n and neighbors.s then
            orientation = "west-to-east"
        elseif neighbors.e and neighbors.w then
            orientation = "north-to-south"
        -- Corner pieces (2 neighbors at 90 degrees)
        elseif neighbors.n and neighbors.e then
            orientation = "south-to-west"
        elseif neighbors.e and neighbors.s then
            orientation = "west-to-north"
        elseif neighbors.s and neighbors.w then
            orientation = "north-to-east"
        elseif neighbors.w and neighbors.n then
            orientation = "east-to-south"
        -- Diagonal connections
        elseif neighbors.ne and neighbors.sw then
            orientation = "north-to-south"
        elseif neighbors.nw and neighbors.se then
            orientation = "west-to-east"
        end
    -- Complex pieces (3+ neighbors)
    elseif neighbor_count >= 3 then
        -- T-junctions
        if not neighbors.n and neighbors.e and neighbors.s and neighbors.w then
            orientation = "east-to-west"
        elseif neighbors.n and not neighbors.e and neighbors.s and neighbors.w then
            orientation = "north-to-south"
        elseif neighbors.n and neighbors.e and not neighbors.s and neighbors.w then
            orientation = "west-to-east"
        elseif neighbors.n and neighbors.e and neighbors.s and not neighbors.w then
            orientation = "south-to-north"
        -- Inner corners (3 neighbors forming an L)
        elseif neighbors.n and neighbors.e and neighbors.ne then
            orientation = "west-to-south"
        elseif neighbors.e and neighbors.s and neighbors.se then
            orientation = "north-to-west"
        elseif neighbors.s and neighbors.w and neighbors.sw then
            orientation = "east-to-north"
        elseif neighbors.w and neighbors.n and neighbors.nw then
            orientation = "south-to-east"
        end
    end

    return orientation
end

-- Modify the entity processing section in storage.actions.render
storage.actions.render = function(player_index, include_status, radius, compression_level, center_x, center_y)
    local player = storage.agent_characters[player_index]
    if not player then
        return nil, "Player not found"
    end

    compression_level = compression_level or "standard"

    local surface = player.surface
    local player_position = {
        x = center_x or player.position.x,
        y = center_y or player.position.y
    }
    local MARGIN = 0
    -- Define search area around player
    local area = {
        left_top = {
            x = player_position.x - radius - MARGIN,
            y = player_position.y - radius - MARGIN
        },
        right_bottom = {
            x = player_position.x + radius - MARGIN,
            y = player_position.y + radius - MARGIN
        }
    }

    -- ENTITIES - Keep as is, they're already relatively efficient
    local entities = surface.find_entities_filtered({ area=area, force='neutral' })
    local entity_data = {}
    local characters = surface.find_entities_filtered({area=area, name='character'})
    for _, entity in pairs(characters) do
        table.insert(entities, entity)
    end
    -- Define resource types to exclude from entities
    local resource_names = {
        ["iron-ore"] = true,
        ["copper-ore"] = true,
        ["coal"] = true,
        ["stone"] = true,
        ["uranium-ore"] = true,
        ["crude-oil"] = true
    }

    for _, entity in pairs(entities) do
        if entity.valid then
            -- Collect all data in one protected call
            local data = {
                name = "\""..entity.name.."\"",
                position = {
                    x = entity.position.x,
                    y = entity.position.y
                },
                direction = entity.direction or 0,
                orientation = entity.orientation or 0
            }

            -- Handle special entity types
            if entity.type == 'underground-belt' then
                if entity.belt_to_ground_type then
                    data.type = entity.belt_to_ground_type
                end
            end

            -- Enhanced cliff handling with validity check
            if entity.type == 'cliff' and entity.valid then
                if entity.cliff_orientation then
                    data.cliff_orientation = "\""..entity.cliff_orientation.."\""
                else
                    local inferred_orientation = analyze_cliff_orientation(entity, surface)
                    data.cliff_orientation = "\""..inferred_orientation.."\""
                    data.cliff_inferred = true
                end
            end

            -- Handle character entities
            if entity.type == 'character' then
                -- Add character-specific data
                data.player_index = entity.player and entity.player.index or nil

                -- Get character state
                if entity.walking_state and entity.walking_state.walking then
                    data.state = "\"running\""
                    data.animation_frame = entity.walking_state.walking and
                        math.floor((game.tick % 140) / 20) or 0  -- 7 frames for running
                elseif entity.mining_state and entity.mining_state.mining then
                    data.state = "\"mining\""
                    data.animation_frame = math.floor((game.tick % 80) / 10)  -- 8 frames for mining
                else
                    data.state = "\"idle\""
                    data.animation_frame = 0
                end

                -- Get armor level (1, 2, or 3 based on equipment)
                data.level = 1  -- Default
                if entity.get_inventory then
                    local armor_inventory = entity.get_inventory(defines.inventory.character_armor)
                    if armor_inventory and armor_inventory.valid then
                        local armor = armor_inventory[1]
                        if armor and armor.valid_for_read then
                            if armor.name == "power-armor-mk2" then
                                data.level = 3
                            elseif armor.name == "power-armor" or armor.name == "modular-armor" then
                                data.level = 2
                            end
                        end
                    end
                end

                -- Check if character has a gun
                data.has_gun = false
                if entity.get_inventory then
                    local gun_inventory = entity.get_inventory(defines.inventory.character_guns)
                    if gun_inventory and gun_inventory.valid then
                        for i = 1, #gun_inventory do
                            if gun_inventory[i].valid_for_read then
                                data.has_gun = true
                                break
                            end
                        end
                    end
                end

                -- Get player color if available
                if entity.player then
                    local color = entity.player.color
                    data.color = {
                        math.floor(color.r * 255),
                        math.floor(color.g * 255),
                        math.floor(color.b * 255)
                    }
                else
                    -- Default orange for non-player characters
                    data.color = {255, 165, 0}
                end
            end

            if include_status and entity.status and entity.valid then
                data.status = entity.status
            end

            -- Add the entity to the list
            table.insert(entity_data, data)
        end
    end

    -- WATER TILES - Optimized using run-length encoding
    local water_runs = {}
    local min_x = math.floor(area.left_top.x - MARGIN)
    local max_x = math.ceil(area.right_bottom.x + MARGIN)
    local min_y = math.floor(area.left_top.y - MARGIN)
    local max_y = math.ceil(area.right_bottom.y + MARGIN)

    -- Scan row by row for water runs
    for y = min_y, max_y do
        local current_type = nil
        local run_start = nil

        for x = min_x, max_x + 1 do  -- +1 to close final run
            local tile = (x <= max_x) and surface.get_tile(x, y) or nil
            local is_water = tile and tile.valid and (tile.name:find("water") or tile.name == "deepwater" or tile.name == "water")
            local tile_type = is_water and tile.name or nil

            if tile_type ~= current_type then
                -- Close previous run if it was water
                if current_type then
                    table.insert(water_runs, {
                        t = current_type,  -- Short key names
                        x = run_start,
                        y = y,
                        l = x - run_start  -- length
                    })
                end

                -- Start new run if water
                if tile_type then
                    current_type = tile_type
                    run_start = x
                else
                    current_type = nil
                end
            end
        end
    end

    -- RESOURCES - Optimized by grouping into patches
    local resource_types = {"iron-ore", "copper-ore", "coal", "stone", "uranium-ore", "crude-oil"}
    local resources = {}

    for _, resource_type in ipairs(resource_types) do
        local resource_entities = surface.find_entities_filtered{
            area = area,
            name = resource_type
        }

        if #resource_entities > 0 then
            -- For dense patches, store as relative positions
            local patches = {}
            local processed = {}

            -- Bucket entity indices by floored tile so nearby candidates are
            -- found without scanning every remaining resource.
            local buckets = {}
            for i, entity in ipairs(resource_entities) do
                local bucket_x = math.floor(entity.position.x)
                local bucket_y = math.floor(entity.position.y)
                buckets[bucket_x] = buckets[bucket_x] or {}
                buckets[bucket_x][bucket_y] = buckets[bucket_x][bucket_y] or {}
                table.insert(buckets[bucket_x][bucket_y], i)
            end

            -- Simple clustering - group resources within 3 tiles of each other
            for i, entity in ipairs(resource_entities) do
                if not processed[i] then
                    local patch = {
                        c = {  -- center
                            math.floor(entity.position.x),
                            math.floor(entity.position.y)
                        },
                        e = {{0, 0, entity.amount}}  -- entities as [dx, dy, amount]
                    }
                    processed[i] = true

                    -- Find nearby resources in ascending index order so patch
                    -- contents match the original scan order.
                    local candidates = {}
                    for bucket_x = patch.c[1] - 3, patch.c[1] + 3 do
                        local column = buckets[bucket_x]
                        if column then
                            for bucket_y = patch.c[2] - 3, patch.c[2] + 3 do
                                local indices = column[bucket_y]
                                if indices then
                                    for _, j in ipairs(indices) do
                                        if j > i and not processed[j] then
                                            candidates[#candidates + 1] = j
                                        end
                                    end
                                end
                            end
                        end
                    end
                    table.sort(candidates)

                    for _, j in ipairs(candidates) do
                        if not processed[j] then
                            local other = resource_entities[j]
                            local dx = other.position.x - patch.c[1]
                            local dy = other.position.y - patch.c[2]

                            if math.abs(dx) <= 3 and math.abs(dy) <= 3 then
                                table.insert(patch.e, {dx, dy, other.amount})
                                processed[j] = true
                            end
                        end
                    end

                    table.insert(patches, patch)
                end
            end

            if #patches > 0 then
                resources[resource_type] = patches
            end
        end
    end

    -- Handle binary compression if requested
    if compression_level == "binary" or compression_level == "maximum" then
        -- Convert water runs to binary format
        local water_binary = encode_water_binary(water_runs)
        local resources_binary = encode_resources_binary(resources)

        return {
            entities = entity_data,
            water_binary = "\""..water_binary.."\"",  -- URL-safe Base64 encoded binary data
            resources_binary = "\""..resources_binary.."\"",  -- URL-safe Base64 encoded binary data
            -- Include metadata for decoding
            meta = {
                area = area,
                format = "\"v2-binary\""
            }
        }
    else
        -- Standard v2 format
        return {
            entities = entity_data,
            water = water_runs,
            resources = resources,
            -- Include metadata for decoding
            meta = {
                area = area,
                format = "v2"
            }
        }
    end
end
-- Binary packing functions (since string.pack isn't available in Factorio's Lua 5.2)
function pack_uint8(n)
    return string.char(bit32.band(n, 0xFF))
end

function pack_int16(n)
    -- Convert to signed representation if needed
    if n < 0 then
        n = 65536 + n
    end
    return string.char(
        bit32.band(bit32.rshift(n, 8), 0xFF),
        bit32.band(n, 0xFF)
    )
end

function pack_uint16(n)
    return string.char(
        bit32.band(bit32.rshift(n, 8), 0xFF),
        bit32.band(n, 0xFF)
    )
end

function pack_uint32(n)
    return string.char(
        bit32.band(bit32.rshift(n, 24), 0xFF),
        bit32.band(bit32.rshift(n, 16), 0xFF),
        bit32.band(bit32.rshift(n, 8), 0xFF),
        bit32.band(n, 0xFF)
    )
end

function pack_int8(n)
    -- Convert to unsigned representation
    if n < 0 then
        n = 256 + n
    end
    return string.char(bit32.band(n, 0xFF))
end

-- Binary encoding functions
function encode_water_binary(water_runs)
    local TILE_TYPES = {
        ['water'] = 1,
        ['deepwater'] = 2,
        ['water-green'] = 3,
        ['water-mud'] = 4,
        ['water-shallow'] = 5
    }

    local data = {}

    for _, run in ipairs(water_runs) do
        local tile_type = TILE_TYPES[run.t] or 1
        local x = run.x
        local y = run.y
        local length = math.min(run.l, 255)  -- Cap at 255 for single byte

        -- Pack as: type(u8), x(i16), y(i16), length(u8)
        table.insert(data, pack_uint8(tile_type))
        table.insert(data, pack_int16(x))
        table.insert(data, pack_int16(y))
        table.insert(data, pack_uint8(length))
    end

    -- Concatenate all binary data and base64 encode
    local binary_data = table.concat(data)
    return base64_encode(binary_data)
end

function encode_resources_binary(resource_patches)
    local RESOURCE_TYPES = {
        ['iron-ore'] = 1,
        ['copper-ore'] = 2,
        ['coal'] = 3,
        ['stone'] = 4,
        ['uranium-ore'] = 5,
        ['crude-oil'] = 6,
        ['tree-01'] = 7
    }

    local data = {}

    for resource_name, patches in pairs(resource_patches) do
        local resource_type = RESOURCE_TYPES[resource_name] or 0
        if resource_type > 0 then
            -- Write resource type and patch count
            table.insert(data, pack_uint8(resource_type))
            table.insert(data, pack_uint16(#patches))

            for _, patch in ipairs(patches) do
                local center = patch.c
                local entities = patch.e

                -- Write patch header: center_x(i16), center_y(i16), entity_count(u16)
                table.insert(data, pack_int16(center[1]))
                table.insert(data, pack_int16(center[2]))
                table.insert(data, pack_uint16(#entities))

                -- Write entities
                for _, entity in ipairs(entities) do
                    local dx = math.max(-128, math.min(127, entity[1]))  -- Clamp to signed byte range
                    local dy = math.max(-128, math.min(127, entity[2]))
                    local amount = entity[3]

                    -- Pack as: dx(i8), dy(i8), amount(u32)
                    table.insert(data, pack_int8(dx))
                    table.insert(data, pack_int8(dy))
                    table.insert(data, pack_uint32(amount))
                end
            end
        end
    end

    local binary_data = table.concat(data)
    return base64_encode(binary_data)
end

-- Base64 encoding function (URL-safe variant to avoid RCON issues)
function base64_encode(data)
    -- Use - and _ instead of + and / to avoid RCON command interpretation
    local b='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    local out = {}
    local length = #data
    for i = 1, length, 3 do
        local first = string.byte(data, i)
        local second = string.byte(data, i + 1)
        local third = string.byte(data, i + 2)
        out[#out + 1] = b:sub(bit32.rshift(first, 2) + 1, bit32.rshift(first, 2) + 1)
        out[#out + 1] = b:sub(bit32.band(bit32.lshift(first, 4), 0x30) + (second and bit32.rshift(second, 4) or 0) + 1,
            bit32.band(bit32.lshift(first, 4), 0x30) + (second and bit32.rshift(second, 4) or 0) + 1)
        if second then
            out[#out + 1] = b:sub(bit32.band(bit32.lshift(second, 2), 0x3C) + (third and bit32.rshift(third, 6) or 0) + 1,
                bit32.band(bit32.lshift(second, 2), 0x3C) + (third and bit32.rshift(third, 6) or 0) + 1)
        else
            out[#out + 1] = "="
        end
        if third then
            out[#out + 1] = b:sub(bit32.band(third, 0x3F) + 1, bit32.band(third, 0x3F) + 1)
        else
            out[#out + 1] = "="
        end
    end
    return table.concat(out)
end
