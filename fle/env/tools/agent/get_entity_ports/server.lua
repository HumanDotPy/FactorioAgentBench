-- Report the fluid connection ports of the entity at a position. Bounded and
-- read-only: never mutates the entity or its fluidboxes.
storage.actions.get_entity_ports = function(player_index, x, y, entity_name)
    local character = storage.agent_characters[player_index]
    local surface = character.surface
    local position = {x = tonumber(x), y = tonumber(y)}
    local found = surface.find_entities_filtered{
        position = position, radius = 0.71, limit = 8
    }
    local entity = nil
    local fallback = nil
    for _, candidate in ipairs(found or {}) do
        if candidate.name == entity_name then
            entity = candidate
            break
        end
        if
            fallback == nil
            and candidate.type ~= "resource"
            and candidate.type ~= "item-on-ground"
        then
            fallback = candidate
        end
    end
    if entity == nil then
        entity = fallback
    end
    if entity == nil then
        return {
            error = "no entity at "
                .. tostring(position.x)
                .. ","
                .. tostring(position.y),
        }
    end

    local report = storage.utils.fluid_port_report(entity, character)

    return {
        entity_id = entity.unit_number,
        name = entity.name,
        inputs = report.inputs,
        outputs = report.outputs,
        ports = report.ports,
    }
end
