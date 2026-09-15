-- Return a normalized recent production rate without serializing all force
-- statistics. Manual harvest/craft events are removed from the detector rate.

local PRECISIONS = {
    {seconds = 5, index = defines.flow_precision_index.five_seconds},
    {seconds = 60, index = defines.flow_precision_index.one_minute},
    {seconds = 600, index = defines.flow_precision_index.ten_minutes},
    {seconds = 3600, index = defines.flow_precision_index.one_hour},
}

local function choose_precision(window_seconds)
    for _, precision in ipairs(PRECISIONS) do
        if window_seconds <= precision.seconds then
            return precision
        end
    end
    return PRECISIONS[#PRECISIONS]
end

local function normalize_window(window_seconds)
    local requested = math.max(1, math.min(tonumber(window_seconds) or 5, 3600))
    return requested, choose_precision(requested)
end

local function normalize_windows(window_seconds)
    if type(window_seconds) == "table" then
        local windows = {}
        for _, value in ipairs(window_seconds) do
            local requested, precision = normalize_window(value)
            table.insert(windows, {requested, precision})
        end
        if #windows == 0 then
            return nil, "window_seconds list must not be empty"
        end
        return windows
    end
    local requested, precision = normalize_window(window_seconds)
    return {{requested, precision}}
end

local function normalize_items(item_name)
    if type(item_name) == "string" then
        if item_name == "" then
            return nil, "item_name must be a non-empty string"
        end
        return {item_name}
    end
    if type(item_name) ~= "table" then
        return nil, "item_name must be a non-empty string or a list of item names"
    end
    local items = {}
    for _, item in ipairs(item_name) do
        if type(item) ~= "string" or item == "" then
            return nil, "every item name must be a non-empty string"
        end
        table.insert(items, item)
    end
    if #items == 0 then
        return nil, "item_name list must not be empty"
    end
    return items
end

local function prune_manual_events(tick)
    -- Keep enough history for a later long-window query. This endpoint is
    -- called for both 60s and 300s context fields; pruning to the current
    -- short window would make the next 300s query lose older manual events
    -- and reintroduce them as false automated production.
    local retention_cutoff_tick = tick - 3600 * 60
    local retained = {}
    storage.manual_production_events = storage.manual_production_events or {}
    for _, event in ipairs(storage.manual_production_events) do
        if event.tick >= retention_cutoff_tick then
            table.insert(retained, event)
        end
    end
    storage.manual_production_events = retained
    return retained
end

local function rate_record(
    item_name,
    requested_window_seconds,
    precision,
    stats,
    manual_events,
    tick
)
    local effective_seconds = precision.seconds
    local total_per_minute = stats.get_flow_count({
        name = item_name,
        category = "input",
        precision_index = precision.index,
        count = false,
    }) or 0

    local cutoff_tick = tick - effective_seconds * 60
    local manual_count = 0
    for _, event in ipairs(manual_events) do
        if event.tick >= cutoff_tick then
            manual_count = manual_count + ((event.outputs or {})[item_name] or 0)
        end
    end

    total_per_minute = math.max(total_per_minute, 0)
    local manual_per_minute = manual_count / effective_seconds * 60
    return {
        item_name = item_name,
        requested_window_seconds = requested_window_seconds,
        effective_window_seconds = effective_seconds,
        total_per_minute = total_per_minute,
        manual_per_minute = manual_per_minute,
        dynamic_per_minute = math.max(total_per_minute - manual_per_minute, 0),
        observed_at_tick = tick,
    }
end

storage.actions.get_recent_rate = function(player_index, item_name, window_seconds)
    local items, item_error = normalize_items(item_name)
    if not items then
        return {error = item_error}
    end
    local windows, window_error = normalize_windows(window_seconds)
    if not windows then
        return {error = window_error}
    end

    local tick = game.tick
    local force = game.forces.player
    local surface = game.surfaces[1]
    local stats = force.get_item_production_statistics(surface)
    local manual_events = prune_manual_events(tick)

    local rates = {}
    for _, item in ipairs(items) do
        local per_window = {}
        for _, window in ipairs(windows) do
            per_window[tostring(window[1])] = rate_record(
                item,
                window[1],
                window[2],
                stats,
                manual_events,
                tick
            )
        end
        rates[item] = per_window
    end

    if type(item_name) == "string" and #windows == 1 then
        return rates[items[1]][tostring(windows[1][1])]
    end
    return {rates = rates, observed_at_tick = tick}
end
