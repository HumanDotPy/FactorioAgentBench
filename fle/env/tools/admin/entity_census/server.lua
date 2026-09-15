-- Lightweight entity census: name -> {status -> count} for the player
-- force, without serializing full entity attributes. Used by the verifier's
-- per-intervention telemetry when no objective needs entity details.

local ENTITY_STATUS_NAMES = nil

local function entity_status_name(entity_status)
    if not ENTITY_STATUS_NAMES then
        ENTITY_STATUS_NAMES = {}
        for name, value in pairs(defines.entity_status) do
            ENTITY_STATUS_NAMES[value] = name
        end
    end
    if not entity_status then
        return "normal"
    end
    return defines.entity_status[entity_status]
        or ENTITY_STATUS_NAMES[entity_status]
        or "normal"
end

storage.actions.entity_census = function(player_index)
    local character = storage.agent_characters[player_index]
    if not character or not character.valid then
        return {census = {}, total = 0}
    end
    local force = character.force
    local surface = game.surfaces["nauvis"]
    local entities = surface.find_entities_filtered({force = force})
    local census = {}
    local total = 0
    for _, entity in pairs(entities) do
        if entity.valid then
            if storage.utils.track_public_status then storage.utils.track_public_status(entity) end
            local name = entity.name
            local status_name = entity_status_name(entity.status)
            census[name] = census[name] or {}
            census[name][status_name] = (census[name][status_name] or 0) + 1
            total = total + 1
        end
    end
    return {census = census, total = total}
end
