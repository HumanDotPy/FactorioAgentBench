storage.actions.sleep = function(seconds)
    -- Sleep keeps the virtual action-cost clock separate from game.tick.
    local standard_ticks = seconds * 60
    if standard_ticks > 0 then
        storage.elapsed_ticks = (storage.elapsed_ticks or 0) + standard_ticks
    end
    return game.tick
end
