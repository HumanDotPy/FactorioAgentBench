-- utils.lua
storage.utils.remove_enemies = function ()
    game.forces["enemy"].kill_all_units()  -- Removes all biters
    game.map_settings.enemy_expansion.enabled = false  -- Stops biters from expanding
    game.map_settings.enemy_evolution.enabled = false  -- Stops biters from evolving
    local surface = game.surfaces[1]
    for _, entity in pairs(surface.find_entities_filtered({type="unit-spawner"})) do
        entity.destroy()
    end
end

local directions = {'north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest'}

storage.utils.get_direction = function(from_position, to_position)
    local dx = to_position.x - from_position.x
    local dy = to_position.y - from_position.y
    local adx = math.abs(dx)
    local ady = math.abs(dy)
    local diagonal_threshold = 0.5

    -- Factorio 2.0 direction values: north=0, northeast=2, east=4, southeast=6, south=8, southwest=10, west=12, northwest=14
    if adx > ady then
        if dx > 0 then
            return (ady / adx > diagonal_threshold) and (dy > 0 and 6 or 2) or 4  -- southeast/northeast or east
        else
            return (ady / adx > diagonal_threshold) and (dy > 0 and 10 or 14) or 12  -- southwest/northwest or west
        end
    else
        if dy > 0 then
            return (adx / ady > diagonal_threshold) and (dx > 0 and 6 or 10) or 8  -- southeast/southwest or south
        else
            return (adx / ady > diagonal_threshold) and (dx > 0 and 2 or 14) or 0  -- northeast/northwest or north
        end
    end
end

storage.utils.get_direction_with_diagonals = function(from_pos, to_pos)
    local dx = to_pos.x - from_pos.x
    local dy = to_pos.y - from_pos.y

    if dx == 0 and dy == 0 then
        return nil
    end

    -- Check for cardinal directions first
    local cardinal_margin = 0.20 --0.25
    if math.abs(dx) < cardinal_margin then
        return dy > 0 and defines.direction.south or defines.direction.north
    elseif math.abs(dy) < cardinal_margin then
        return dx > 0 and defines.direction.east or defines.direction.west
    end

    -- Handle diagonal directions
    if dx > 0 then
        return dy > 0 and defines.direction.southeast or defines.direction.northeast
    else
        return dy > 0 and defines.direction.southwest or defines.direction.northwest
    end
end


storage.utils.get_closest_entity = function(player, position)
    local closest_distance = math.huge
    local closest_entity = nil
    local entities = player.surface.find_entities_filtered{
        position = position,
        force = "player",
        radius = 5  -- Increased from 3 to 5 to better handle large entities like 3x3 drills
    }

    for _, entity in ipairs(entities) do
        if entity.name ~= 'character' and entity.name ~= 'laser-beam' then
            local distance = ((position.x - entity.position.x) ^ 2 + (position.y - entity.position.y) ^ 2) ^ 0.5
            if distance < closest_distance then
                closest_distance = distance
                closest_entity = entity
            end
        end
    end

    return closest_entity
end

storage.utils.calculate_movement_ticks = function(player, from_pos, to_pos)
    -- Calculate distance between points
    local dx = to_pos.x - from_pos.x
    local dy = to_pos.y - from_pos.y
    local distance = math.sqrt(dx * dx + dy * dy)

    -- Get player's walking speed (tiles per tick)
    -- Character base speed is 0.15 tiles/tick
    local walking_speed = player.character_running_speed
    if not walking_speed or walking_speed == 0 then
        walking_speed = 0.15  -- Default walking speed
    end

    -- Calculate ticks needed for movement
    return math.ceil(distance / walking_speed)
end

-- Wrapper around LuaSurface.can_place_entity that replicates all checks LuaPlayer.can_place_entity performs.
-- This allows our code to validate placement without relying on an actual LuaPlayer instance.
-- extra_params can be provided by callers to pass additional flags (e.g. fast_replace) if needed.
storage.utils.can_place_entity = function(player, entity_name, position, direction, extra_params)
    local params = extra_params or {}
    params.name = entity_name
    params.position = position
    params.direction = direction
    params.force = player.force
    -- Use the manual build-check path so the engine applies the same rules as when a human player builds.
    params.build_check_type = defines.build_check_type.manual
    return player.surface.can_place_entity(params)
end

storage.utils.avoid_entity = function(player_index, entity, position, direction)
    local player = storage.agent_characters[player_index]
    return player.surface.can_place_entity{
        name = entity,
        force = "player",
        position = position,
        direction = storage.utils.get_entity_direction(entity, direction),
        build_check_type = defines.build_check_type.manual
    }
end

storage.crafting_queue = {}

script.on_event(defines.events.on_tick, function(event)
  local queue = storage.crafting_queue
  if not queue or #queue == 0 then return end
  -- Iterate over the crafting queue and update the remaining ticks
  for i = #queue, 1, -1 do
    local task = queue[i]
    task.remaining_ticks = task.remaining_ticks - 1

    -- If the crafting is finished, consume the ingredients, insert the crafted entity, and remove the task from the queue
    if task.remaining_ticks <= 0 then
      for _, ingredient in pairs(task.recipe.ingredients) do
        task.player.remove_item({name = ingredient.name, count = ingredient.amount * task.count})
      end
      task.player.insert({name = task.entity_name, count = task.count})
      table.remove(queue, i)
    end
  end
end)

-- Utility function to ensure a valid character exists for a given player index
-- Call this before any operation that needs the character
-- Returns the valid character entity, or creates a new one if invalid/missing
storage.utils.ensure_valid_character = function(player_index)
    if not storage.agent_characters then
        storage.agent_characters = {}
    end

    local char = storage.agent_characters[player_index]

    -- If character is missing or invalid, create a new one
    if not char or not char.valid then

        --if not char then
        --    error("Character not available")
        --end
        --if char.position and not char.valid then
        --    error("Character at: x="..char.position.x..", y="..char.position.y)
        --end
        --if not char.valid then
        --    error("Character not valid")
        --end

        local spawn_position = {x = 0, y = (player_index - 1) * 2}

        local new_char = game.surfaces[1].create_entity{
            name = "character",
            position = spawn_position,
            force = game.forces.player
        }

        if new_char then
            storage.agent_characters[player_index] = new_char
            return new_char
        else
            error("Failed to create agent character " .. player_index)
        end
    end

    return char
end

function dump(o)
   if type(o) == 'table' then
      local s = '{ '
      for k,v in pairs(o) do
         if type(k) ~= 'number' then k = string.format('%q', k) end
         s = s .. '['..k..'] = ' .. dump(v) .. ','
      end
      return s .. '} '
   elseif type(o) == 'string' then
      -- Older entity serializers wrap scalar strings in quotes themselves.
      -- Normalize that representation once, then quote every string at the
      -- transport boundary, including raw diagnostic strings and item names.
      if o:sub(1,1) == '"' and o:sub(-1) == '"' and #o >= 2 then
         o = o:sub(2,-2)
      end
      return string.format('%q', o)
   else
      return tostring(o)
   end
end

-- Unconnected character entities craft natively, but Factorio does not enter
-- their completed handcrafts into force production statistics. Those flows
-- drive craft-item research triggers. Observe only active queues and account
-- completed recipes (including native intermediate crafts), never requests.
local function native_craft_counts(character)
    local counts = {}
    for _, entry in ipairs(character.crafting_queue or {}) do
        counts[entry.recipe] = (counts[entry.recipe] or 0) + entry.count
    end
    return counts
end

storage.utils.sync_native_crafting = function(player_index)
    local pending = storage.native_crafting and storage.native_crafting[player_index]
    if not pending then return end
    local character = storage.agent_characters[player_index]
    if not character or not character.valid or character ~= pending.character then
        storage.native_crafting[player_index] = nil
        return
    end
    local current = native_craft_counts(character)
    local stats = character.force.get_item_production_statistics(character.surface)
    for name, previous in pairs(pending.counts) do
        local completed = previous - (current[name] or 0)
        if completed > 0 then
            local recipe = character.force.recipes[name]
            local record = {crafted_count=completed, inputs={}, outputs={}}
            for _, ingredient in pairs(recipe.ingredients) do
                if ingredient.type == 'item' then
                    local count = ingredient.amount * completed
                    record.inputs[ingredient.name] = count
                    if not character.player then stats.on_flow(ingredient.name, -count) end
                end
            end
            for _, product in pairs(recipe.products) do
                if product.type == 'item' then
                    local count = product.amount * completed
                    record.outputs[product.name] = count
                    if not character.player then stats.on_flow(product.name, count) end
                end
            end
            storage.crafted_items = storage.crafted_items or {}
            table.insert(storage.crafted_items, record)
            storage.manual_production_events = storage.manual_production_events or {}
            table.insert(storage.manual_production_events, {
                tick=game.tick, kind='crafted', outputs=record.outputs
            })
        end
    end
    if next(current) then
        pending.counts = current
    else
        storage.native_crafting[player_index] = nil
    end
end

storage.utils.track_native_crafting = function(player_index)
    local character = storage.agent_characters[player_index]
    storage.native_crafting = storage.native_crafting or {}
    local counts = native_craft_counts(character)
    storage.native_crafting[player_index] = next(counts)
        and {character=character, counts=counts} or nil
end

storage.utils.begin_native_crafting = function(player_index, recipe_name, count)
    storage.utils.sync_native_crafting(player_index)
    local character = storage.agent_characters[player_index]
    local queued = character.begin_crafting{count=count, recipe=recipe_name}
    storage.utils.track_native_crafting(player_index)
    return queued
end

script.on_nth_tick(1, function()
    local pending = storage.native_crafting
    if not pending or not next(pending) then return end
    for player_index in pairs(pending) do
        storage.utils.sync_native_crafting(player_index)
    end
end)

function storage.utils.inspect(player, radius, position)
    local surface = player.surface
    local bounding_box = {
        left_top = {x = position.x - radius, y = position.y - radius},
        right_bottom = {x = position.x + radius, y = position.y + radius}
    }

    local entities = surface.find_entities_filtered({bounding_box, force = "player"})
    local entity_data = {}

    for _, entity in ipairs(entities) do
        if entity.name ~= 'character' then
            local data = {
                name = entity.name:gsub("-", "_"),
                position = entity.position,
                direction = entity.direction,--directions[entity.direction+1],
                health = entity.health,
                force = entity.force.name,
                energy = entity.energy,
                status = entity.status,
                --crafted_items = entity.crafted_items or nil
            }

            -- Get entity contents if it has an inventory
            if entity.get_inventory(defines.inventory.chest) then
                local inventory = storage.utils.get_contents_compat(entity.get_inventory(defines.inventory.chest))
                data.contents = inventory
            end

            data.warnings = storage.utils.get_issues(entity)

            -- Get entity orientation if it has an orientation attribute
            if entity.type == "train-stop" or entity.type == "car" or entity.type == "locomotive" then
                data.orientation = entity.orientation
            end

            -- Get connected entities for pipes and transport belts
            if entity.type == "pipe" or entity.type == "transport-belt" then
                local path_ends = find_path_ends(entity)
                data.path_ends = {}
                for _, path_end in pairs(path_ends) do
                    local path_position = {x=path_end.position.x - player.position.x, y=path_end.position.y - player.position.y}
                    table.insert(data.path_ends, {name = path_end.name:gsub("-", "_"), position = path_position, unit_number = path_end.unit_number})
                end
            end

            table.insert(entity_data, data)
        else
            local data = {
                name = "player_character",
                position = entity.position,
                direction = directions[(entity.direction/2)+1],  -- Factorio 2.0 direction values are 0,2,4,6,8,10,12,14
            }
            table.insert(entity_data, data)
        end
    end

    -- Sort entities with path_ends by the length of path_ends in descending order
    table.sort(entity_data, function(a, b)
        if a.path_ends and b.path_ends then
            return #a.path_ends > #b.path_ends
        elseif a.path_ends then
            return true
        else
            return false
        end
    end)

    -- Remove entities that exist in the path_ends of other entities
    local visited_paths = {}
    local filtered_entity_data = {}
    for _, data in ipairs(entity_data) do
        if data.path_ends then
            local should_add = true
            for _, path_end in ipairs(data.path_ends) do
                if visited_paths[path_end.unit_number] then
                    should_add = false
                    break
                end
            end
            if should_add then
                for _, path_end in ipairs(data.path_ends) do
                    visited_paths[path_end.unit_number] = true
                end
                table.insert(filtered_entity_data, data)
            else
                data.path_ends = nil
                --table.insert(filtered_entity_data, data)
            end
        else
            table.insert(filtered_entity_data, data)
        end
    end
    entity_data = filtered_entity_data

    return entity_data
end

-- Format player inventory contents for error messages
storage.utils.format_inventory_for_error = function(player)
    local main_inv = player.get_inventory(defines.inventory.character_main)
    if not main_inv then
        return "empty"
    end

    local contents = storage.utils.get_contents_compat(main_inv)
    if not contents or next(contents) == nil then
        return "empty"
    end

    local items = {}
    for name, count in pairs(contents) do
        table.insert(items, name .. "=" .. count)
    end

    -- Limit to first 10 items to avoid overly long error messages
    if #items > 10 then
        local truncated = {}
        for i = 1, 10 do
            truncated[i] = items[i]
        end
        return table.concat(truncated, ", ") .. " (and " .. (#items - 10) .. " more)"
    end

    return table.concat(items, ", ")
end

-- Read fluid port geometry plus live connection state. Read-only: never
-- mutates the entity or its fluidboxes.
--
-- Each port reports the fluidbox connection point (the fluidbox center, which
-- is usually inside the machine body), whether that fluidbox currently has a
-- live connection, its peers when connected, and -- for open ports -- the
-- candidate tiles where a connecting pipe would go, best candidate first.
-- The attach tile is one tile outward along the port's facing direction; when
-- the runtime does not expose a facing, the outward ray from the entity
-- center is used, then any free orthogonal neighbour.
storage.utils.fluid_port_report = function(entity, player)
    local report = { ports = {}, inputs = {}, outputs = {} }
    if not entity then
        return report
    end
    local valid_ok, is_valid = pcall(function() return entity.valid end)
    if valid_ok and is_valid == false then
        return report
    end

    local has_fluidbox, fluidbox = pcall(function() return entity.fluidbox end)
    if not has_fluidbox or fluidbox == nil then
        return report
    end
    local length_ok, length = pcall(function() return #fluidbox end)
    if not length_ok or not length or length == 0 then
        return report
    end

    local center = entity.position
    local box = entity.bounding_box

    local function inside_entity(tile)
        if not box then
            return false
        end
        return tile.x > box.left_top.x and tile.x < box.right_bottom.x
            and tile.y > box.left_top.y and tile.y < box.right_bottom.y
    end

    local function can_place_pipe(tile)
        if player == nil then
            return false
        end
        local ok_place, placeable = pcall(function()
            return storage.utils.can_place_entity(player, "pipe", tile, 0)
        end)
        return ok_place and placeable and true or false
    end

    local function direction_delta(direction)
        if direction == nil then
            return nil
        end
        if direction == defines.direction.north then
            return 0, -1
        elseif direction == defines.direction.east then
            return 1, 0
        elseif direction == defines.direction.south then
            return 0, 1
        elseif direction == defines.direction.west then
            return -1, 0
        end
        return nil
    end

    local function attach_tiles(position, port_direction)
        local candidates = {}
        local seen = {}
        local function add(tile)
            local key = string.format("%.2f,%.2f", tile.x, tile.y)
            if seen[key] then
                return
            end
            seen[key] = true
            if not inside_entity(tile) and can_place_pipe(tile) then
                candidates[#candidates + 1] = tile
            end
        end

        local dx, dy = direction_delta(port_direction)
        if dx then
            -- The runtime told us which face this port opens onto; only that
            -- tile can carry the pipe. Listing other neighbours would send
            -- the agent to tiles that can never connect.
            add({ x = position.x + dx, y = position.y + dy })
            return candidates
        end
        local rx = position.x - center.x
        local ry = position.y - center.y
        if math.abs(rx) >= math.abs(ry) and rx ~= 0 then
            add({ x = position.x + (rx > 0 and 1 or -1), y = position.y })
        elseif ry ~= 0 then
            add({ x = position.x, y = position.y + (ry > 0 and 1 or -1) })
        end
        add({ x = position.x + 1, y = position.y })
        add({ x = position.x - 1, y = position.y })
        add({ x = position.x, y = position.y + 1 })
        add({ x = position.x, y = position.y - 1 })
        add({ x = math.floor(position.x) + 0.5, y = math.floor(position.y) + 0.5 })
        return candidates
    end

    for fluidbox_index = 1, length do
        local ports_ok, connections = pcall(function()
            return fluidbox.get_pipe_connections(fluidbox_index)
        end)
        if ports_ok and type(connections) == "table" then
            local peer_boxes = {}
            local live_ok, live_connections = pcall(function()
                return fluidbox.get_connections(fluidbox_index)
            end)
            local connection_state_known = live_ok
                and type(live_connections) == "table"
            if connection_state_known then
                for _, neighbour in ipairs(live_connections) do
                    local owner = neighbour and neighbour.owner
                    if owner and owner.valid ~= false then
                        peer_boxes[#peer_boxes + 1] = {
                            entity_id = owner.unit_number,
                            name = owner.name,
                            position = owner.position,
                            box = owner.bounding_box,
                        }
                    end
                end
            end

            local function point_box_distance(point, box)
                if not box then
                    return math.huge
                end
                local dx = math.max(
                    box.left_top.x - point.x, 0, point.x - box.right_bottom.x
                )
                local dy = math.max(
                    box.left_top.y - point.y, 0, point.y - box.right_bottom.y
                )
                return math.sqrt(dx * dx + dy * dy)
            end

            for _, connection in ipairs(connections) do
                local position = connection.position
                if position then
                    local port = {
                        x = position.x,
                        y = position.y,
                        fluidbox_index = fluidbox_index,
                        flow_direction = connection.flow_direction,
                        connection_type = connection.connection_type,
                    }
                    if connection.direction ~= nil then
                        port.direction = connection.direction
                    end
                    if connection_state_known then
                        local peers = {}
                        for _, peer in ipairs(peer_boxes) do
                            if point_box_distance(position, peer.box) <= 1.0 then
                                peers[#peers + 1] = {
                                    entity_id = peer.entity_id,
                                    name = peer.name,
                                    position = peer.position,
                                }
                            end
                        end
                        port.connected = #peers > 0
                        if #peers > 0 then
                            port.peers = peers
                        else
                            port.attach_tiles = attach_tiles(
                                position, connection.direction
                            )
                        end
                    end
                    report.ports[#report.ports + 1] = port
                    if port.flow_direction == "input" then
                        report.inputs[#report.inputs + 1] = port
                    elseif port.flow_direction == "output" then
                        report.outputs[#report.outputs + 1] = port
                    end
                end
            end
        end
    end

    return report
end

-- Attach the fluid connection report to a freshly serialized machine and add
-- explicit warnings for open ports. Pipes and underground pipes are quiet:
-- an open pipe end is a normal intermediate state, not a problem.
storage.utils.attach_connection_report = function(serialized, entity, player)
    local prototype = prototypes.entity[entity.name]
    if not prototype then
        return serialized
    end
    -- LuaEntityPrototype is strict: reading an absent key raises instead of
    -- returning nil, so probe fluid_boxes defensively.
    local boxes_ok, boxes = pcall(function() return prototype.fluid_boxes end)
    if not boxes_ok or not boxes or #boxes == 0 then
        return serialized
    end

    local report = storage.utils.fluid_port_report(entity, player)
    if #report.ports == 0 then
        return serialized
    end
    serialized.fluid = report

    local quiet = prototype.type == "pipe" or prototype.type == "pipe-to-ground"
    if quiet then
        return serialized
    end

    serialized.warnings = serialized.warnings or {}
    for _, port in ipairs(report.ports) do
        if port.connected == false then
            local label = port.flow_direction
            if label == "input-output" or label == nil then
                label = "fluid"
            end
            local text = "unconnected " .. label .. " port at ("
                .. port.x .. ", " .. port.y .. ")"
            if port.attach_tiles and #port.attach_tiles > 0 then
                local tile = port.attach_tiles[1]
                text = text .. "; place a pipe at (" .. tile.x .. ", " .. tile.y .. ")"
            else
                text = text .. "; no free pipe attach tile found"
            end
            table.insert(serialized.warnings, "'" .. text .. "'")
        end
    end
    return serialized
end

storage.utils.escape_character_to_free_tile = function(player, avoid_box, prefer_away, prefer_toward)
    if not player or not player.position then
        return nil
    end
    local surface = player.surface
    local origin = player.position
    local candidates = {}
    for _, radius in ipairs({1, 2}) do
        candidates[#candidates + 1] = {x = origin.x + radius, y = origin.y}
        candidates[#candidates + 1] = {x = origin.x - radius, y = origin.y}
        candidates[#candidates + 1] = {x = origin.x, y = origin.y + radius}
        candidates[#candidates + 1] = {x = origin.x, y = origin.y - radius}
    end

    local function inside_avoid_box(candidate)
        if not avoid_box then
            return false
        end
        local margin = 0.45
        return candidate.x > avoid_box.left_top.x - margin
            and candidate.x < avoid_box.right_bottom.x + margin
            and candidate.y > avoid_box.left_top.y - margin
            and candidate.y < avoid_box.right_bottom.y + margin
    end

    local function is_free(candidate)
        if inside_avoid_box(candidate) then
            return false
        end
        local blockers = surface.find_entities_filtered{
            position = candidate, radius = 0.45,
            collision_mask = "player", limit = 1
        }
        if blockers and #blockers > 0 then
            return false
        end
        for _, offset in ipairs({{0, 0}, {0.45, 0}, {-0.45, 0}, {0, 0.45}, {0, -0.45}}) do
            local tile = surface.get_tile(candidate.x + offset[1], candidate.y + offset[2])
            -- Factorio 2.0: LuaTile has no `walkable` property; reading it raises
            -- and kills the nth-tick walking-queue handler. Ask the engine
            -- whether the player collision layer collides with this tile.
            if tile and tile.collides_with("player") then
                return false
            end
        end
        return true
    end

    local function preference(candidate)
        local reference = prefer_toward or prefer_away
        if not reference then
            return 0
        end
        local dx = candidate.x - reference.x
        local dy = candidate.y - reference.y
        local distance = math.sqrt(dx * dx + dy * dy)
        if prefer_toward then
            return -distance
        end
        return distance
    end

    table.sort(candidates, function(a, b)
        return preference(a) > preference(b)
    end)

    for _, candidate in ipairs(candidates) do
        if is_free(candidate) then
            player.teleport(candidate)
            return player.position
        end
    end
    return nil
end
