-- Loaded only into a dedicated reference process, never the benchmark worker.
local surface = game.surfaces["reference"]
local force = game.forces.player
local blueprint = {}

function blueprint.capture(area)
    local inventory = game.create_inventory(1)
    local ok, result = pcall(function()
        local stack = inventory[1]
        stack.set_stack{name="blueprint"}
        stack.create_blueprint{surface=surface, force=force, area=area,
            always_include_tiles=true, include_entities=true, include_modules=true,
            include_station_names=true, include_trains=true, include_fuel=true}
        if not stack.is_blueprint_setup() then error("empty blueprint area") end
        return {content=stack.export_stack(), entity_count=stack.get_blueprint_entity_count(),
            tile_count=#(stack.get_blueprint_tiles() or {})}
    end)
    inventory.destroy()
    if not ok then error(result) end
    return result
end

function blueprint.place(content, position, options)
    options = options or {}
    local inventory = game.create_inventory(1)
    local ok, result = pcall(function()
        local stack = inventory[1]
        stack.set_stack{name="blueprint"}
        if stack.import_stack(content) ~= 0 or not stack.is_blueprint or not stack.is_blueprint_setup() then
            error("invalid blueprint; select a book entry before placing")
        end
        local ghosts = stack.build_blueprint{surface=surface,force=force,position=position,
            direction=options.direction or 0,build_mode=defines.build_mode[options.build_mode or "normal"]}
        local built, pending = 0, 0
        if options.instant ~= false then
            -- Retry once after tiles/rails: dependencies can precede their foundations.
            for pass=1,2 do
                for _, ghost in ipairs(ghosts) do
                    if ghost.valid and (ghost.type == "entity-ghost" or ghost.type == "tile-ghost") then
                        local _, entity, proxy = ghost.revive{raise_revive=true}
                        if not ghost.valid then built = built + 1 end
                        if entity and proxy and proxy.valid then
                            local complete = true
                            for _, request in ipairs(proxy.insert_plan) do
                                for _, slot in ipairs(request.items.in_inventory or {}) do
                                    local target = entity.get_inventory(slot.inventory)
                                    if not target or not target[slot.stack+1].set_stack{
                                        name=request.id.name, quality=request.id.quality or "normal",
                                        count=slot.count or 1} then complete = false end
                                end
                                if request.items.grid_count then complete = false end
                            end
                            if complete then proxy.destroy() end
                        end
                    end
                end
            end
        end
        for _, ghost in ipairs(ghosts) do if ghost.valid then pending = pending + 1 end end
        return {built=built,pending_ghosts=pending,created_ghosts=#ghosts}
    end)
    inventory.destroy()
    if not ok then error(result) end
    return result
end
