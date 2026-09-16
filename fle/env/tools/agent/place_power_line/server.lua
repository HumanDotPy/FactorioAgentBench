local function ppl_resolve_pole(surface, position)
    local found = surface.find_entities_filtered{
        position = {x = position.x, y = position.y},
        type = "electric-pole",
    }
    for _, entity in ipairs(found) do
        if entity.valid then
            return entity
        end
    end
    return nil
end

local function ppl_connectors_connected(first_connector, second_connector)
    if first_connector.is_connected_to then
        local ok, connected = pcall(
            first_connector.is_connected_to, first_connector, second_connector)
        if ok then
            return connected
        end
    end
    for _, connection in ipairs(first_connector.connections or {}) do
        if connection.target == second_connector then
            return true
        end
    end
    for _, connection in ipairs(second_connector.connections or {}) do
        if connection.target == first_connector then
            return true
        end
    end
    return false
end

local function ppl_span_failure(nodes, resolved, index)
    local first = nodes[index]
    local second = nodes[index + 1]
    local dx = second.x - first.x
    local dy = second.y - first.y
    return {
        from_index = index - 1,
        to_index = index,
        from_position = {x = first.x, y = first.y},
        to_position = {x = second.x, y = second.y},
        gap = math.sqrt(dx * dx + dy * dy),
        missing = (resolved[index] == nil or resolved[index + 1] == nil),
    }
end

storage.actions.place_power_line = function(player_index, nodes)
    local player = storage.utils.ensure_valid_character(player_index)
    local surface = player.surface
    local resolved = {}
    for index = 1, #nodes do
        resolved[index] = ppl_resolve_pole(surface, nodes[index])
    end

    local failures = {}
    local spans_checked = 0
    for index = 1, #nodes - 1 do
        spans_checked = spans_checked + 1
        local first = resolved[index]
        local second = resolved[index + 1]
        local connected = false
        if first and second then
            local first_connector = first.get_wire_connector(
                defines.wire_connector_id.pole_copper, false)
            local second_connector = second.get_wire_connector(
                defines.wire_connector_id.pole_copper, false)
            if first_connector and second_connector then
                connected = ppl_connectors_connected(first_connector, second_connector)
            end
        end
        if not connected then
            failures[#failures + 1] = ppl_span_failure(nodes, resolved, index)
        end
    end

    return {
        connected = (#failures == 0),
        spans_checked = spans_checked,
        unreachable = failures,
    }
end
