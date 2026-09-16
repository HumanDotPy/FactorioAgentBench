-- Compact structured tile/entity map around a point. Bounded and read-only.
-- Glyphs: ^ > v < belts by flow direction; i/I inserters (i = burner) with
-- drop-side glyph; A assembler, F furnace, D drill, L lab, G generator,
-- B boiler, p pump, P pole, C chest, | pipe, t tree, R rock, s stump,
-- o item on ground, @ character, ~ water, # blocked terrain, * ore tile
-- without an entity, . clear ground.
local belt_glyph = {[0] = "^", [4] = ">", [8] = "v", [12] = "<"}
local fixed = {
    ["assembling-machine-1"] = "A",
    ["assembling-machine-2"] = "A",
    ["assembling-machine-3"] = "A",
    ["stone-furnace"] = "F",
    ["steel-furnace"] = "F",
    ["electric-furnace"] = "F",
    ["lab"] = "L",
    ["steam-engine"] = "G",
    ["boiler"] = "B",
    ["offshore-pump"] = "p",
    ["wooden-chest"] = "C",
    ["iron-chest"] = "C",
    ["steel-chest"] = "C",
    ["pipe"] = "|",
    ["pipe-to-ground"] = "|",
}

local status_names = nil

local function status_name(status)
    if status == nil then
        return "unknown"
    end
    if not status_names then
        status_names = {}
        for name, value in pairs(defines.entity_status or {}) do
            status_names[value] = name
        end
    end
    return status_names[status] or "unknown"
end

local function entity_glyph(entity)
    if entity.name == "character" then
        return "@"
    elseif entity.type == "tree" then
        return "t"
    elseif entity.type == "corpse" and entity.name:find("stump") then
        return "s"
    elseif entity.type == "simple-entity" then
        return "R"
    elseif entity.type == "transport-belt" or entity.type == "underground-belt" then
        return belt_glyph[entity.direction] or ">"
    elseif entity.type == "item-on-ground" then
        return "o"
    elseif entity.type == "inserter" then
        return entity.name == "inserter" and "I" or "i"
    elseif entity.type == "electric-pole" then
        return "P"
    elseif entity.type == "mining-drill" then
        return "D"
    end
    return fixed[entity.name]
end

local function contents_of(entity)
    if not storage.utils.get_contents_compat then
        return {}
    end
    for _, key in ipairs({"chest", "crafter_input", "furnace_source", "fuel"}) do
        if defines and defines.inventory and defines.inventory[key]
            and entity.get_inventory then
            local ok, inventory = pcall(function()
                return entity.get_inventory(defines.inventory[key])
            end)
            if ok and inventory then
                local contents = storage.utils.get_contents_compat(inventory)
                if contents and next(contents) ~= nil then
                    return contents
                end
            end
        end
    end
    return {}
end

storage.actions.get_tile_map = function(player_index, x, y, radius)
    radius = math.min(math.max(tonumber(radius) or 16, 1), 32)
    local character = storage.agent_characters[player_index]
    local surface = character.surface
    local cx, cy = math.floor(tonumber(x)), math.floor(tonumber(y))
    local rows = {}
    local entities = {}
    local entities_truncated = false
    local seen = {}

    local function entity_at(position)
        if not position then
            return nil
        end
        local ok, found = pcall(function()
            return surface.find_entities_filtered{
                position = {x = position.x, y = position.y},
                radius = 0.5,
                limit = 4,
            }
        end)
        if not ok or not found then
            return nil
        end
        for _, other in pairs(found) do
            if other.valid ~= false and other.name ~= "character" then
                return other
            end
        end
        return nil
    end

    local function entity_record(entity)
        local status = status_name(entity.status)
        local record = {
            name = entity.name,
            type = entity.type,
            entity_id = entity.unit_number,
            position = {x = entity.position.x, y = entity.position.y},
            direction = storage.utils.inserter_engine_direction(
                entity.name, entity.direction),
            status = status,
        }
        if entity.type == "item-on-ground" then
            local stack = entity.stack
            if stack and stack.valid_for_read then
                record.item = stack.name
                record.count = stack.count
            end
        end
        if entity.type == "inserter" or entity.type == "mining-drill" then
            if entity.drop_position then
                record.drop_position = {
                    x = entity.drop_position.x,
                    y = entity.drop_position.y,
                }
                local drop_target = entity_at(entity.drop_position)
                record.drop_target = drop_target and drop_target.name or nil
            end
        end
        if entity.type == "inserter" then
            if entity.pickup_position then
                record.pickup_position = {
                    x = entity.pickup_position.x,
                    y = entity.pickup_position.y,
                }
            end
            if status == "waiting_for_source_items" then
                local pickup_target = entity_at(entity.pickup_position)
                record.pickup_target = pickup_target and pickup_target.name or nil
                record.source_inventory = pickup_target and contents_of(pickup_target) or {}
                record.stall_reason = "waiting_for_source_items"
            end
        end
        return record
    end

    local function accept_entity(entity)
        local glyph = entity_glyph(entity)
        if glyph == nil then
            return nil
        end
        local key
        if entity.unit_number then
            key = "u" .. tostring(entity.unit_number)
        else
            key = entity.name .. "@" .. entity.position.x .. "," .. entity.position.y
        end
        if seen[key] then
            return glyph
        end
        seen[key] = true
        if #entities < 128 then
            entities[#entities + 1] = entity_record(entity)
        else
            entities_truncated = true
        end
        return glyph
    end

    -- Factorio 2.0 removed LuaSurface.get_tiles; find_tiles_filtered with only
    -- an area returns the same bounded LuaTile set.
    local bulk_tiles = surface.find_tiles_filtered{
        area = {
            {cx - radius, cy - radius},
            {cx + radius + 1, cy + radius + 1}
        }
    }

    local tile_by_position = nil
    local found_by_tile = nil
    if bulk_tiles then
        tile_by_position = {}
        for _, tile in ipairs(bulk_tiles) do
            tile_by_position[tile.position.x .. "," .. tile.position.y] = tile
        end
        found_by_tile = {}
        local area_entities = surface.find_entities_filtered{
            area = {
                {cx - radius, cy - radius},
                {cx + radius + 1, cy + radius + 1}
            }
        }
        for _, entity in ipairs(area_entities) do
            local box = entity.bounding_box
            if box then
                local min_x = math.max(math.floor(box.left_top.x), cx - radius)
                local max_x = math.min(math.ceil(box.right_bottom.x) - 1, cx + radius)
                local min_y = math.max(math.floor(box.left_top.y), cy - radius)
                local max_y = math.min(math.ceil(box.right_bottom.y) - 1, cy + radius)
                for tile_x = min_x, max_x do
                    for tile_y = min_y, max_y do
                        local key = tile_x .. "," .. tile_y
                        local found = found_by_tile[key]
                        if not found then
                            found = {}
                            found_by_tile[key] = found
                        end
                        if #found < 4 then
                            found[#found + 1] = entity
                        end
                    end
                end
            end
        end
    end

    for tile_y = cy - radius, cy + radius do
        local row = {}
        for tile_x = cx - radius, cx + radius do
            local key = tile_x .. "," .. tile_y
            local found
            if found_by_tile then
                found = found_by_tile[key] or {}
            else
                found = surface.find_entities_filtered{
                    area = {{tile_x, tile_y}, {tile_x + 1, tile_y + 1}}, limit = 4
                }
            end
            local glyph = nil
            for _, entity in ipairs(found) do
                if entity.type ~= "resource" then
                    glyph = accept_entity(entity)
                    if glyph ~= nil then
                        break
                    end
                end
            end
            if glyph == nil and #found > 0 and found[1].type == "resource" then
                glyph = "*"
            end
            if glyph == nil then
                local tile = tile_by_position and tile_by_position[key]
                if tile == nil then
                    tile = surface.get_tile(tile_x, tile_y)
                end
                if tile.name == "water" or tile.name:find("^water") then
                    glyph = "~"
                elseif tile.collides_with("player") then
                    glyph = "#"
                else
                    glyph = "."
                end
            end
            row[#row + 1] = glyph
        end
        rows[#rows + 1] = table.concat(row)
    end
    return {
        center = {x = cx, y = cy},
        radius = radius,
        rows = rows,
        entities = entities,
        entities_truncated = entities_truncated,
        legend = "^>v< belts (all belt types); i/I inserters (drop side); A assembler; "
            .. "F furnace; D drill; L lab; B boiler; G engine; p pump; P pole; C chest; "
            .. "| pipe; t tree; R rock; s stump; o item on ground; @ character; "
            .. "* ore; ~ water; # blocked; . clear",
    }
end
