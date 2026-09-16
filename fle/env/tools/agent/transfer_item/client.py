from fle.env.entities import Entity, EntityGroup, Position
from fle.env.game_types import Prototype
from fle.env.tools import Tool


class TransferItem(Tool):
    def _rollback(self, item, source, missing, receipt):
        if missing <= 0 or not isinstance(source, Entity):
            receipt["leftover"] = max(0, missing)
            return
        try:
            restored_entity = self.game_state.insert_item(item, source, missing)
            restored = getattr(restored_entity, "inserted", None)
            restored = int(restored) if restored is not None else 0
        except Exception as exc:
            receipt["rollback_error"] = str(exc)
            restored = 0
        restored = max(0, min(restored, missing))
        receipt["returned"] = restored
        receipt["leftover"] = missing - restored

    def __call__(self, item, source, target, quantity=5):
        """Move items from a source entity or position into a target.

        :param item: Prototype of the item to move
        :param source: Entity or Position to extract from
        :param target: Entity or EntityGroup to insert into
        :param quantity: Maximum number of items to move
        :return: {status ("completed"/"partial"/"failed"), item, requested,
                  extracted, inserted, returned, leftover, tick?}. `inserted`
                  counts items that actually reached the target; `returned`
                  counts items put back into the source; `leftover` counts
                  items that stayed in your inventory.
        """
        assert isinstance(item, Prototype), "The first argument must be a Prototype"
        assert isinstance(quantity, int) and not isinstance(quantity, bool), (
            "quantity must be an integer"
        )
        assert quantity > 0, "quantity must be greater than 0"
        if not isinstance(source, (Entity, Position)):
            raise ValueError("source must be an Entity or Position")
        if not isinstance(target, (Entity, EntityGroup)):
            raise ValueError("target must be an Entity or EntityGroup")

        item_name = item.value[0]
        extracted = self.game_state.extract_item(item, source, quantity)
        extracted = int(extracted)
        if extracted <= 0:
            raise Exception(
                f"Could not transfer {item_name}: nothing extracted from the source"
            )

        receipt = {
            "status": "failed",
            "item": item_name,
            "requested": quantity,
            "extracted": extracted,
            "inserted": 0,
            "returned": 0,
            "leftover": extracted,
        }

        try:
            inserted_entity = self.game_state.insert_item(item, target, extracted)
        except Exception as exc:
            receipt["error"] = str(exc)
            self._rollback(item, source, extracted, receipt)
            return receipt

        inserted = getattr(inserted_entity, "inserted", None)
        if inserted is None:
            receipt["error"] = (
                "target insertion did not report how many items it accepted"
            )
            self._rollback(item, source, extracted, receipt)
            return receipt
        inserted = max(0, min(int(inserted), extracted))
        receipt["inserted"] = inserted

        if inserted < extracted:
            self._rollback(item, source, extracted - inserted, receipt)

        if inserted >= extracted:
            receipt["status"] = "completed"
        elif inserted > 0:
            receipt["status"] = "partial"
        else:
            receipt["status"] = "failed"
        return receipt
