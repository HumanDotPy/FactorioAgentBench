storage.actions.get_fluid_network = function(player_index, x, y, include_members, max_entities)
    local character = storage.agent_characters[player_index]
    local surface = character.surface
    local px, py = tonumber(x), tonumber(y)
    max_entities = math.min(math.max(math.floor(tonumber(max_entities) or 512), 1), 4096)
    include_members = include_members == true

    local function try(fn)
        local ok, value = pcall(fn)
        if ok then
            return value
        end
        return nil
    end

    local function boxes_of(entity)
        local fb = try(function()
            return entity.fluidbox
        end)
        if fb == nil then
            return nil
        end
        local box_count = try(function()
            return #fb
        end)
        if box_count == nil or box_count < 1 then
            return nil
        end
        return fb, box_count
    end

    local found = try(function()
        return surface.find_entities_filtered{
            position = {x = px, y = py},
            radius = 0.71,
            limit = 16,
        }
    end) or {}
    local seed = nil
    for _, entity in ipairs(found) do
        if entity.type ~= "resource" and entity.type ~= "item-on-ground" then
            if boxes_of(entity) then
                seed = entity
                break
            end
        end
    end
    if seed == nil then
        return {
            error = "no fluid connection at (" .. tostring(px) .. ", " .. tostring(py) .. ")",
        }
    end

    local seed_fb, seed_box_count = boxes_of(seed)
    local sid = try(function()
        return seed_fb.get_fluid_segment_id(1)
    end)
    local contents = try(function()
        return seed_fb.get_fluid_segment_contents(1)
    end)
    local capacity = try(function()
        return seed_fb.get_capacity(1)
    end)
    capacity = tonumber(capacity) or 0

    local fluid = nil
    local amount = 0
    if type(contents) == "table" and next(contents) ~= nil then
        for name, value in pairs(contents) do
            fluid = name
            amount = amount + (tonumber(value) or 0)
        end
    else
        -- No segment contents (nil or empty): fall back to the seed's own
        -- fluid boxes so a machine port still reports its local state.
        for i = 1, seed_box_count do
            local own = try(function()
                return seed_fb[i] and seed_fb[i].amount
            end)
            local box_fluid = try(function()
                return seed_fb[i] and seed_fb[i].name
            end)
            if box_fluid ~= nil then
                fluid = box_fluid
            end
            amount = amount + (tonumber(own) or 0)
        end
        if sid == nil then
            capacity = 0
            for i = 1, seed_box_count do
                local box_capacity = try(function()
                    return seed_fb.get_capacity(i)
                end)
                capacity = capacity + (tonumber(box_capacity) or 0)
            end
        end
    end

    local visited = {}
    local queue = {seed}
    local head = 1
    local entity_count = 0
    local pipe_count = 0
    local tank_count = 0
    local pump_count = 0
    local machine_count = 0
    local entities_truncated = false
    local members = {}

    while head <= #queue do
        local entity = queue[head]
        head = head + 1
        local key = entity.unit_number
        if key ~= nil and not visited[key] then
            if entity_count >= max_entities then
                entities_truncated = true
                break
            end
            visited[key] = true
            entity_count = entity_count + 1

            if entity.type == "pipe" or entity.type == "pipe-to-ground" then
                pipe_count = pipe_count + 1
            elseif entity.type == "storage-tank" then
                tank_count = tank_count + 1
            elseif entity.type == "pump" then
                pump_count = pump_count + 1
            else
                machine_count = machine_count + 1
            end

            if include_members and #members < 64 then
                members[#members + 1] = {
                    name = entity.name,
                    type = entity.type,
                    entity_id = key,
                    position = {x = entity.position.x, y = entity.position.y},
                }
            end

            if sid ~= nil then
                local fb, box_count = boxes_of(entity)
                if fb then
                    for i = 1, box_count do
                        local conns = try(function()
                            return fb.get_connections(i)
                        end)
                        if type(conns) == "table" then
                            for _, box in ipairs(conns) do
                                local owner = try(function()
                                    return box.owner
                                end)
                                if owner ~= nil and owner.unit_number ~= nil and not visited[owner.unit_number] then
                                    local other_fb, other_count = boxes_of(owner)
                                    if other_fb then
                                        for j = 1, other_count do
                                            local other_sid = try(function()
                                                return other_fb.get_fluid_segment_id(j)
                                            end)
                                            if other_sid ~= nil and other_sid == sid then
                                                queue[#queue + 1] = owner
                                                break
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
    end

    local fill_ratio = 0
    if capacity > 0 then
        fill_ratio = amount / capacity
    end

    return {
        entity = {
            name = seed.name,
            entity_id = seed.unit_number,
            position = {x = seed.position.x, y = seed.position.y},
        },
        segment_id = sid,
        fluid = fluid,
        amount = amount,
        capacity = capacity,
        fill_ratio = fill_ratio,
        entity_count = entity_count,
        pipe_count = pipe_count,
        tank_count = tank_count,
        pump_count = pump_count,
        machine_count = machine_count,
        entities_truncated = entities_truncated,
        members = include_members and members or nil,
    }
end
