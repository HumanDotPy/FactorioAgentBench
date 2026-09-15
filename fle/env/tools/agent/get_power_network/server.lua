-- Read-only electric network state at a point, equivalent to a player clicking an
-- electric pole in Factorio 2.0. Exposes raw physical state only: production,
-- consumption and accumulator charge statistics. No satisfaction score and no
-- recommendations.
storage.actions.get_power_network = function(player_index, x, y, window_seconds, include_members)
    local window_options = {
        [5] = defines.flow_precision_index.five_seconds,
        [60] = defines.flow_precision_index.one_minute,
        [600] = defines.flow_precision_index.ten_minutes,
        [3600] = defines.flow_precision_index.one_hour,
    }
    local requested = tonumber(window_seconds) or 5
    if window_options[requested] == nil then
        requested = 5
    end
    local precision = window_options[requested]
    local want_members = include_members and true or false

    local px, py = tonumber(x), tonumber(y)
    local tx, ty = math.floor(px), math.floor(py)
    local character = storage.agent_characters[player_index]
    local surface = character.surface

    local function read_stats(entity)
        if entity == nil then
            return nil
        end
        local ok, stats = pcall(function()
            return entity.electric_network_statistics
        end)
        if ok and stats ~= nil then
            return stats
        end
        return nil
    end

    local function network_id_of(entity)
        if entity == nil then
            return nil
        end
        local ok, id = pcall(function()
            return entity.electric_network_id
        end)
        if ok and id ~= nil then
            return id
        end
        return nil
    end

    local function describe(entity)
        return {
            name = entity.name,
            entity_id = entity.unit_number,
            position = {x = entity.position.x, y = entity.position.y},
        }
    end

    local found = surface.find_entities_filtered{
        position = {x = px, y = py},
        radius = 0.71,
        limit = 8,
    }
    local resolved = nil
    for _, entity in ipairs(found) do
        if entity.type ~= "resource" and entity.type ~= "item-on-ground" then
            if read_stats(entity) ~= nil then
                resolved = entity
                break
            end
            if resolved == nil then
                resolved = entity
            end
        end
    end
    if resolved == nil then
        return {error = "no electric network at (" .. tx .. ", " .. ty .. ")"}
    end

    local stats_entity = nil
    local stats = read_stats(resolved)
    if stats ~= nil then
        stats_entity = resolved
    end
    local id = network_id_of(resolved)
    if stats_entity == nil then
        if id == nil then
            return {error = "no electric network at (" .. tx .. ", " .. ty .. ")"}
        end
        -- Machines carry no statistics; borrow them from a pole on the same
        -- network. The scan is bounded: 16 tiles, then 32 tiles if empty.
        local function find_pole(radius)
            local poles = surface.find_entities_filtered{
                area = {
                    {tx - radius, ty - radius},
                    {tx + radius, ty + radius},
                },
                type = "electric-pole",
                limit = 64,
            }
            for _, pole in ipairs(poles) do
                if network_id_of(pole) == id and read_stats(pole) ~= nil then
                    return pole
                end
            end
            return nil
        end
        stats_entity = find_pole(16)
        if stats_entity == nil then
            stats_entity = find_pole(32)
        end
        if stats_entity ~= nil then
            stats = read_stats(stats_entity)
        end
    end

    local active_id = id
    if stats_entity ~= nil then
        active_id = network_id_of(stats_entity) or id
    end
    local available = stats ~= nil
    if available and active_id == nil then
        available = false
    end

    local by_producer = {}
    local by_consumer = {}
    local storage_rows = {}
    local production_w = 0
    local consumption_w = 0
    local generator_count = 0
    local consumer_count = 0
    local truncated = false

    local function flow_value(name, category)
        local ok, value = pcall(function()
            return stats.get_flow_count{
                name = name,
                category = category,
                precision_index = precision,
            }
        end)
        if ok and type(value) == "number" then
            return value
        end
        return 0
    end

    local function flow_count(name, category)
        local ok, value = pcall(function()
            return stats.get_flow_count{
                name = name,
                category = category,
                precision_index = precision,
                count = true,
            }
        end)
        if ok and type(value) == "number" then
            return value
        end
        return 0
    end

    if available then
        local input_counts = stats.input_counts or {}
        local output_counts = stats.output_counts or {}
        local storage_counts = stats.storage_counts or {}

        for name, _ in pairs(output_counts) do
            local watts = flow_value(name, "output") * 60
            local count = flow_count(name, "output")
            production_w = production_w + watts
            generator_count = generator_count + count
            by_producer[#by_producer + 1] = {
                prototype = name,
                watts = watts,
                count = count,
            }
        end
        for name, _ in pairs(input_counts) do
            local watts = flow_value(name, "input") * 60
            local count = flow_count(name, "input")
            consumption_w = consumption_w + watts
            consumer_count = consumer_count + count
            by_consumer[#by_consumer + 1] = {
                prototype = name,
                watts = watts,
                count = count,
            }
        end
        for name, _ in pairs(storage_counts) do
            -- Accumulator charge has no published unit here; expose the raw
            -- value and the entity count without converting it.
            local charge = flow_value(name, "storage")
            local count = flow_count(name, "storage")
            storage_rows[#storage_rows + 1] = {
                prototype = name,
                charge = charge,
                count = count,
            }
        end
    end

    local function cap(list, key)
        table.sort(list, function(left, right)
            return left[key] > right[key]
        end)
        if #list > 64 then
            for index = #list, 65, -1 do
                list[index] = nil
            end
            truncated = true
        end
    end

    cap(by_producer, "watts")
    cap(by_consumer, "watts")
    cap(storage_rows, "charge")

    local result = {
        entity = describe(stats_entity or resolved),
        network_id = active_id or -1,
        window_seconds = requested,
        statistics_available = available,
        production_w = production_w,
        by_producer = by_producer,
        consumption_w = consumption_w,
        by_consumer = by_consumer,
        storage = storage_rows,
        generator_count = generator_count,
        consumer_count = consumer_count,
        truncated = truncated,
    }

    if want_members then
        local center = stats_entity or resolved
        local ex, ey = center.position.x, center.position.y
        local scan = surface.find_entities_filtered{
            area = {{ex - 32, ey - 32}, {ex + 32, ey + 32}},
            type = "electric-pole",
            limit = 128,
        }
        local member_poles = {}
        for _, pole in ipairs(scan) do
            if active_id ~= nil and network_id_of(pole) == active_id then
                member_poles[#member_poles + 1] = {
                    entity_id = pole.unit_number,
                    position = {x = pole.position.x, y = pole.position.y},
                }
            end
        end
        if #scan >= 128 then
            truncated = true
            result.truncated = true
        end
        result.pole_count = #member_poles
        result.members = {poles = member_poles}
    end

    return result
end
