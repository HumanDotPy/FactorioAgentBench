-- Cache math functions
local floor = math.floor
local ceil = math.ceil
local max = math.max
local abs = math.abs

local water_tile_names = {
    "water", "deepwater", "water-green", "deepwater-green",
    "water-shallow", "water-mud"
}

storage.actions.nearest_buildable = function(player_index, entity_name, bounding_box, center_position)
    local player = storage.agent_characters[player_index]
    local surface = player.surface
    local entity_prototype = prototypes.entity[entity_name]
    local needs_resources = entity_prototype.resource_categories ~= nil
    local start_pos = center_position or player.position
    local needs_oil = entity_name == "pumpjack"

    -- Cache for chunk resources
    local chunk_cache = {}
    -- Cache for per-chunk blocking entity boxes and water tiles
    local blocker_cache = {}
    local water_cache = {}

    local function get_chunk_resources(chunk_x, chunk_y)
        local cache_key = chunk_x .. "," .. chunk_y
        if not chunk_cache[cache_key] then
            chunk_cache[cache_key] = surface.find_entities_filtered{
                area = {
                    {chunk_x * 32, chunk_y * 32},
                    {(chunk_x + 1) * 32, (chunk_y + 1) * 32}
                },
                type = "resource"
            }
        end
        return chunk_cache[cache_key]
    end

    local function get_chunk_blockers(chunk_x, chunk_y)
        local cache_key = chunk_x .. "," .. chunk_y
        if not blocker_cache[cache_key] then
            local entities = surface.find_entities_filtered{
                area = {
                    {chunk_x * 32, chunk_y * 32},
                    {(chunk_x + 1) * 32, (chunk_y + 1) * 32}
                },
                type = {"character", "resource"},
                invert = true
            }
            local boxes = {}
            for _, entity in ipairs(entities) do
                boxes[#boxes + 1] = entity.bounding_box
            end
            blocker_cache[cache_key] = boxes
        end
        return blocker_cache[cache_key]
    end

    local function get_chunk_water(chunk_x, chunk_y)
        local cache_key = chunk_x .. "," .. chunk_y
        if not water_cache[cache_key] then
            local tiles = surface.find_tiles_filtered{
                area = {
                    {chunk_x * 32, chunk_y * 32},
                    {(chunk_x + 1) * 32, (chunk_y + 1) * 32}
                },
                name = water_tile_names
            }
            local positions = {}
            for _, tile in ipairs(tiles) do
                positions[#positions + 1] = {x = tile.position.x, y = tile.position.y}
            end
            water_cache[cache_key] = positions
        end
        return water_cache[cache_key]
    end

    local function boxes_overlap(left_top, right_bottom, box)
        return box.left_top.x < right_bottom.x and box.right_bottom.x > left_top.x
            and box.left_top.y < right_bottom.y and box.right_bottom.y > left_top.y
    end

    local function box_has_blockers(left_top, right_bottom)
        local chunk_min_x = floor(left_top.x / 32)
        local chunk_min_y = floor(left_top.y / 32)
        local chunk_max_x = floor((right_bottom.x - 0.001) / 32)
        local chunk_max_y = floor((right_bottom.y - 0.001) / 32)
        if chunk_max_x < chunk_min_x then chunk_max_x = chunk_min_x end
        if chunk_max_y < chunk_min_y then chunk_max_y = chunk_min_y end
        for chunk_x = chunk_min_x, chunk_max_x do
            for chunk_y = chunk_min_y, chunk_max_y do
                for _, box in ipairs(get_chunk_blockers(chunk_x, chunk_y)) do
                    if boxes_overlap(left_top, right_bottom, box) then
                        return true
                    end
                end
            end
        end
        return false
    end

    local function box_has_water(left_top, right_bottom)
        local min_x = floor(left_top.x)
        local min_y = floor(left_top.y)
        local max_x = ceil(right_bottom.x) - 1
        local max_y = ceil(right_bottom.y) - 1
        for chunk_x = floor(min_x / 32), floor(max_x / 32) do
            for chunk_y = floor(min_y / 32), floor(max_y / 32) do
                for _, tile in ipairs(get_chunk_water(chunk_x, chunk_y)) do
                    if tile.x >= min_x and tile.x <= max_x
                        and tile.y >= min_y and tile.y <= max_y then
                        return true
                    end
                end
            end
        end
        return false
    end

    local function has_resource_in_box(left_top, right_bottom, resource_name)
        local chunk_min_x = floor(left_top.x / 32)
        local chunk_min_y = floor(left_top.y / 32)
        local chunk_max_x = floor((right_bottom.x - 0.001) / 32)
        local chunk_max_y = floor((right_bottom.y - 0.001) / 32)
        if chunk_max_x < chunk_min_x then chunk_max_x = chunk_min_x end
        if chunk_max_y < chunk_min_y then chunk_max_y = chunk_min_y end
        for chunk_x = chunk_min_x, chunk_max_x do
            for chunk_y = chunk_min_y, chunk_max_y do
                for _, resource in ipairs(get_chunk_resources(chunk_x, chunk_y)) do
                    if (resource_name == nil or resource.name == resource_name)
                        and boxes_overlap(left_top, right_bottom, resource.bounding_box) then
                        return true
                    end
                end
            end
        end
        return false
    end

    local function check_resource_coverage(left_top, right_bottom)
        if not needs_resources then return true end

        if needs_oil then
            return has_resource_in_box(left_top, right_bottom, "crude-oil")
        end

        local min_x = floor(left_top.x)
        local min_y = floor(left_top.y)
        local max_x = ceil(right_bottom.x) - 1
        local max_y = ceil(right_bottom.y) - 1
        local required_coverage = (max_x - min_x + 1) * (max_y - min_y + 1)

        -- Set up position tracking
        local positions = {}
        local total_resources = 0

        -- Collect resources from relevant chunks
        for chunk_x = floor(min_x / 32), floor(max_x / 32) do
            for chunk_y = floor(min_y / 32), floor(max_y / 32) do
                for _, resource in ipairs(get_chunk_resources(chunk_x, chunk_y)) do
                    local x = floor(resource.position.x)
                    local y = floor(resource.position.y)
                    if x >= min_x and x <= max_x and
                       y >= min_y and y <= max_y then
                        positions[x] = positions[x] or {}
                        if not positions[x][y] then
                            positions[x][y] = true
                            total_resources = total_resources + 1
                        end
                    end
                end
            end
        end

        -- Early exit if not enough resources
        if total_resources < required_coverage then
            return false
        end

        -- Verify complete coverage
        for x = min_x, max_x do
            if not positions[x] then return false end
            for y = min_y, max_y do
                if not positions[x][y] then return false end
            end
        end

        return true
    end

    local function is_buildable_box(origin, box_dimensions)
        -- Calculate actual positions
        local left_top = {
            x = origin.x + box_dimensions.left_top.x,
            y = origin.y + box_dimensions.left_top.y
        }
        local right_bottom = {
            x = origin.x + box_dimensions.right_bottom.x,
            y = origin.y + box_dimensions.right_bottom.y
        }

        -- Quick collision checks first
        -- Factorio 2.0: Use tile name filter for water check instead of collision_mask
        if box_has_water(left_top, right_bottom) then
            return false
        end

        -- Check for blocking entities
        if box_has_blockers(left_top, right_bottom) then
            return false
        end

        -- Resource coverage check
        if not check_resource_coverage(left_top, right_bottom) then
            return false
        end

        return true, left_top, right_bottom
    end

    local function spiral_search()
        local dx, dy = 0, 0
        local segment_length = 1
        local segment_passed = 0
        local direction = 0  -- 0: right, 1: down, 2: left, 3: up
        local MAX_RADIUS = 30

        while max(abs(dx), abs(dy)) <= MAX_RADIUS do
            local current_pos = {
                x = start_pos.x + dx,
                y = start_pos.y + dy
            }

            if bounding_box then
                local is_buildable, left_top, right_bottom = is_buildable_box(current_pos, bounding_box)
                if is_buildable then
                    --rendering.clear()
                    rendering.draw_rectangle{
                        only_in_alt_mode=true,
                        surface = surface,
                        left_top = left_top,
                        right_bottom = right_bottom,
                        filled = false,
                        color = {r=0, g=1, b=0, a=0.5},
                        time_to_live = 60000
                    }
                    return {position=current_pos, left_top=left_top, right_bottom=right_bottom}
                end
            else
                -- Simple position check for entities without bounding box
                local left_top = {x = current_pos.x, y = current_pos.y}
                local right_bottom = {x = current_pos.x + 1, y = current_pos.y + 1}
                if needs_resources then
                    if has_resource_in_box(left_top, right_bottom) then
                        return current_pos
                    end
                else
                    if not box_has_blockers(left_top, right_bottom) then
                        return current_pos
                    end
                end
            end

            -- Spiral pattern movement
            segment_passed = segment_passed + 1
            if direction == 0 then dx = dx + 1
            elseif direction == 1 then dy = dy + 1
            elseif direction == 2 then dx = dx - 1
            else dy = dy - 1 end

            if segment_passed == segment_length then
                segment_passed = 0
                direction = (direction + 1) % 4
                if direction % 2 == 0 then
                    segment_length = segment_length + 1
                end
            end
        end

        error("\"Could not find a buildable position for the entity: " .. entity_name.."\"")
    end

    return spiral_search()
end
