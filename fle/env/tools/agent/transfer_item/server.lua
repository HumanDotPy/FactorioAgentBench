storage.actions.transfer_item = function(player_index, item, sx, sy, source_name, tx, ty, target_name, quantity)
    local requested = tonumber(quantity) or 0
    local receipt = {
        status = "failed",
        item = item,
        requested = requested,
        extracted = 0,
        inserted = 0,
        returned = 0,
        leftover = 0,
        tick = game.tick,
    }

    if requested <= 0 then
        receipt.error = "quantity must be greater than 0"
        return receipt
    end

    local extract_action = storage.actions.extract_item
    local insert_action = storage.actions.insert_item
    if type(extract_action) ~= "function" or type(insert_action) ~= "function" then
        receipt.error = "extract_item and insert_item actions must be loaded"
        return receipt
    end

    local ok_extract, extracted = pcall(extract_action, player_index, item,
        requested, sx, sy, source_name)
    if not ok_extract then
        receipt.error = tostring(extracted)
        return receipt
    end
    receipt.extracted = tonumber(extracted) or 0
    if receipt.extracted <= 0 then
        receipt.error = "nothing was extracted from the source"
        return receipt
    end

    local ok_insert, insert_result = pcall(insert_action, player_index, item,
        receipt.extracted, tx, ty, target_name, false)
    local inserted = 0
    if ok_insert and type(insert_result) == "table" then
        inserted = tonumber(insert_result.inserted) or 0
    end
    receipt.inserted = inserted

    if not ok_insert then
        receipt.error = tostring(insert_result)
    elseif type(insert_result) ~= "table" or insert_result.inserted == nil then
        receipt.error = "target insertion did not report an inserted count"
    end

    if inserted < receipt.extracted then
        local missing = receipt.extracted - inserted
        local ok_restore, restore_result = pcall(insert_action, player_index, item,
            missing, sx, sy, source_name, false)
        local restored = 0
        if ok_restore and type(restore_result) == "table" then
            restored = tonumber(restore_result.inserted) or 0
        end
        restored = math.max(0, math.min(restored, missing))
        receipt.returned = restored
        receipt.leftover = missing - restored
    end

    if inserted >= receipt.extracted and receipt.error == nil then
        receipt.status = "completed"
    elseif inserted > 0 then
        receipt.status = "partial"
    else
        receipt.status = "failed"
    end

    return receipt
end
