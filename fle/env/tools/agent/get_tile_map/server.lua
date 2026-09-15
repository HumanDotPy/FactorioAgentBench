-- Compact structured tile/entity map around a point. Bounded and read-only.
-- Glyphs: ^ > v < belts by flow direction; i/I inserters (i = burner) with
-- drop-side glyph; A assembler, F furnace, D drill, L lab, G generator,
-- B boiler, p pump, P pole, C chest, | pipe, t tree, R rock, s stump,
-- @ character, ~ water, # blocked terrain, * ore tile without an entity,
-- . clear ground.
local belt_glyph = {[0] = "^", [4] = ">", [8] = "v", [12] = "<"}
local inserter_glyph = {[0] = "v", [4] = "<", [8] = "^", [12] = ">"}
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

local function entity_glyph(entity)
    if entity.name == "character" then
        return "@"
    elseif entity.type == "tree" then
        return "t"
    elseif entity.type == "corpse" and entity.name:find("stump") then
        return "s"
    elseif entity.type == "simple-entity" then
        return "R"
    elseif entity.name == "transport-belt" then
        return belt_glyph[entity.direction] or ">"
    elseif entity.type == "inserter" then
        return entity.name == "inserter" and "I" or "i"
    elseif entity.type == "electric-pole" then
        return "P"
    elseif entity.type == "mining-drill" then
        return "D"
    end
    return fixed[entity.name]
end

storage.actions.get_tile_map = function(player_index, x, y, radius)
    radius = math.min(math.max(tonumber(radius) or 16, 1), 32)
    local character = storage.agent_characters[player_index]
    local surface = character.surface
    local cx, cy = math.floor(tonumber(x)), math.floor(tonumber(y))
    local rows = {}
    local entities = {}
    local entities_truncated = false

    local function accept_entity(entity)
        local glyph = entity_glyph(entity)
        if glyph == nil then
            return nil
        end
        if #entities < 128 then
            entities[#entities + 1] = {
                name = entity.name,
                type = entity.type,
                entity_id = entity.unit_number,
                position = {x = entity.position.x, y = entity.position.y},
                direction = entity.direction,
                status = entity.status,
            }
        else
            entities_truncated = true
        end
        return glyph
    end

    local bulk_tiles = nil
    if surface.get_tiles then
        bulk_tiles = surface.get_tiles{
            {cx - radius, cy - radius},
            {cx + radius + 1, cy + radius + 1}
        }
    end

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
                if entity.type ~= "resource" and entity.type ~= "item-on-ground" then
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
        legend = "^>v< belts; i/I inserters (drop side); A assembler; F furnace; "
            .. "D drill; L lab; B boiler; G engine; p pump; P pole; C chest; "
            .. "| pipe; t tree; R rock; s stump; @ character; "
            .. "* ore; ~ water; # blocked; . clear",
    }
end
