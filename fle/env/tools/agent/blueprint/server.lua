-- Native blueprint capture and ghost placement. No inventory, research or clock
-- mutations: construction is performed by the character or native robots.
local function with_stack(callback)
    local inventory = game.create_inventory(1)
    inventory[1].set_stack{name="blueprint"}
    local ok, result = pcall(callback, inventory[1])
    inventory.destroy()
    if not ok then return {error=tostring(result)} end
    return result
end

local function capture(character, x, y, radius)
    if radius <= 0 or radius > 128 then
        return {error="capture radius must be greater than 0 and at most 128"}
    end
    return with_stack(function(stack)
        stack.create_blueprint{
            surface=character.surface, force=character.force,
            area={{x-radius,y-radius},{x+radius,y+radius}},
            always_include_tiles=true, include_entities=true, include_modules=true,
            include_station_names=true, include_trains=true, include_fuel=true,
        }
        if not stack.is_blueprint_setup() then return {error="empty blueprint area"} end
        return {blueprint='"' .. stack.export_stack() .. '"',
            entity_count=stack.get_blueprint_entity_count(),
            tile_count=#(stack.get_blueprint_tiles() or {}), center_x=x,center_y=y}
    end)
end

local function import(stack, content)
    local status = stack.import_stack(content)
    if status ~= 0 then error("Factorio rejected or repaired exchange data (code " .. status .. ")") end
    return stack
end

local function place(character, player_index, content, x, y, options)
    return with_stack(function(stack)
        import(stack, content)
        if not stack.is_blueprint or not stack.is_blueprint_setup() then
            return {error="select a nonempty blueprint before placing"}
        end
        local direction = options.direction or 0
        if direction ~= 0 and direction ~= 4 and direction ~= 8 and direction ~= 12 then
            return {error="direction must be 0, 4, 8, or 12"}
        end
        local mode = defines.build_mode[options.build_mode or "normal"]
        if not mode then return {error="build_mode must be normal, forced, or superforced"} end
        local ghosts = stack.build_blueprint{
            surface=character.surface, force=character.force, position={x=x,y=y},
            direction=direction, build_mode=mode, skip_fog_of_war=false, raise_built=true,
        }
        local summaries = {}
        for _, ghost in ipairs(ghosts) do
            if ghost.valid and #summaries < 128 then
                summaries[#summaries+1] = {name=ghost.ghost_name,
                    position=ghost.position, direction=ghost.direction,entity_id=ghost.unit_number}
            end
        end
        return {status=#ghosts>0 and "ghosts_created" or "no_new_ghosts",construction="native",
            created_ghosts=#ghosts,ghosts=summaries,ghosts_truncated=#ghosts>#summaries,
            blueprint_entities=stack.get_blueprint_entity_count(),
            blueprint_tiles=#(stack.get_blueprint_tiles() or {}),position={x=x,y=y}}

    end)
end

storage.actions.blueprint = function(player_index, command, a, b, c, options)
    local character = storage.agent_characters[player_index]
    if not character or not character.valid then return {error="no character"} end
    if command == "capture" then
        return capture(character, tonumber(a) or 0, tonumber(b) or 0, tonumber(c) or 32)
    elseif command == "place" then
        return place(character, player_index, a, tonumber(b) or 0, tonumber(c) or 0, options or {})
    elseif command == "ghosts" then
        local x,y,radius = tonumber(a) or 0,tonumber(b) or 0,tonumber(c) or 32
        if radius <= 0 or radius > 128 then return {error="radius must be in (0,128]"} end
        local found = character.surface.find_entities_filtered{
            type={"entity-ghost","tile-ghost"},force=character.force,
            area={{x-radius,y-radius},{x+radius,y+radius}}}
        local result = {}
        local offset = math.max(0, tonumber(options and options.offset) or 0)
        for index=offset+1,math.min(#found,offset+128) do
            local ghost=found[index]
            result[#result+1]={name=ghost.ghost_name,position=ghost.position,
                direction=ghost.direction,entity_id=ghost.unit_number,type=ghost.type,
                item_requests=ghost.type=="entity-ghost" and ghost.item_requests or nil}
        end
        return {ghosts=result,total=#found,offset=offset,truncated=#found>offset+#result}
    elseif command == "validate" then
        return with_stack(function(stack)
            import(stack, a)
            return {content='"' .. stack.export_stack() .. '"',
                entity_count=stack.is_blueprint and stack.get_blueprint_entity_count() or 0}
        end)
    elseif command == "apply" then
        options=options or {}
        local radius=tonumber(options.radius) or 32
        if radius <= 0 or radius > 128 then return {error="radius must be in (0,128]"} end
        local x,y=tonumber(b) or 0,tonumber(c) or 0
        return with_stack(function(stack)
            import(stack,a)
            local area={{x-radius,y-radius},{x+radius,y+radius}}
            if stack.is_deconstruction_item then
                local params={surface=character.surface,force=character.force,area=area,
                    skip_fog_of_war=false}
                if options.cancel then stack.cancel_deconstruct_area(params)
                else stack.deconstruct_area(params) end
            elseif stack.is_upgrade_item then
                local params={force=character.force,area=area,item=stack,skip_fog_of_war=false}
                if options.cancel then character.surface.cancel_upgrade_area(params)
                else character.surface.upgrade_area(params) end
            else return {error="apply requires a deconstruction or upgrade planner"} end
            return {status=options.cancel and "orders_cancelled" or "orders_requested",
                construction="native"}
        end)
    end
    return {error="unknown blueprint command: " .. tostring(command)}
end

