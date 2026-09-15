import base64
import zlib
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from fle.envd.api import create_app
from fle.envd.blueprint_exchange import (
    decode_exchange,
    encode_exchange,
    select_blueprint,
)
from fle.envd.blueprints import BlueprintInvalid, BlueprintStore
from fle.envd.errors import IdempotencyConflict, LeaseNotFound
from fle.envd.service import EnvironmentService
from tests.envd.conftest import FakeWorker

pytestmark = pytest.mark.no_factorio

DOCUMENT = {
    "blueprint": {
        "item": "blueprint",
        "version": 562949958467584,
        "label": "test",
        "entities": [
            {
                "entity_number": 1,
                "name": "assembling-machine-2",
                "position": {"x": 0.5, "y": 0.5},
                "recipe": "iron-gear-wheel",
                "control_behavior": {"circuit_enable_disable": True},
            }
        ],
        "tiles": [{"name": "stone-path", "position": {"x": 0, "y": 0}}],
        "wires": [[1, 1, 2, 1]],
        "unknown_future_field": {"keep": True},
    }
}


def test_exchange_preserves_complete_native_document():
    assert decode_exchange(encode_exchange(DOCUMENT)) == DOCUMENT


@pytest.mark.parametrize(
    "content",
    ["bad", "0invalid", "0" + base64.b64encode(zlib.compress(b"[]")).decode()],
)
def test_exchange_rejects_invalid_inputs(content):
    with pytest.raises(BlueprintInvalid):
        decode_exchange(content)


def test_exchange_rejects_decompression_bombs(monkeypatch):
    monkeypatch.setattr("fle.envd.blueprint_exchange.MAX_DOCUMENT_BYTES", 100)
    content = "0" + base64.b64encode(zlib.compress(b" " * 10000)).decode()
    with pytest.raises(BlueprintInvalid):
        decode_exchange(content)


def test_nested_book_selection_uses_native_indices():
    book = {
        "blueprint_book": {
            "item": "blueprint-book",
            "blueprints": [
                {
                    "index": 4,
                    "blueprint_book": {"blueprints": [{"index": 9, **DOCUMENT}]},
                }
            ],
        }
    }
    assert select_blueprint(book, [4, 9]) == DOCUMENT
    with pytest.raises(BlueprintInvalid):
        select_blueprint(book, [0])
    assert decode_exchange(encode_exchange(book)) == book


def test_ephemeral_library_checkpoint_is_exact_and_scope_isolated():
    store = BlueprintStore(None)
    store.save("one", encode_exchange(DOCUMENT), entity_count=1)
    store.record_use("one", 123)
    snapshot = store.export_state()
    store.delete("one")
    restored = BlueprintStore(None)
    restored.restore_state(snapshot)
    assert restored.get("one").times_placed == 1
    assert restored.get("one").last_used_tick == 123
    assert restored.get("one").content == encode_exchange(DOCUMENT)
    assert store.count() == 0
    snapshot[0]["content_sha256"] = "bad"
    with pytest.raises(BlueprintInvalid):
        restored.restore_state(snapshot)
    assert restored.count() == 1


def test_reference_api_is_lease_bound_idempotent_and_not_a_runtime_action(task_spec):
    worker = FakeWorker()
    world = SimpleNamespace(
        lock=threading.RLock(), execute=Mock(return_value={"result": 123})
    )
    pool = Mock()
    pool.get.return_value = world
    pool.create.return_value = {"world_id": "test"}
    service = EnvironmentService([worker], reference_worlds=pool)
    lease = service.lease(task_spec)
    args = {"code": "return 123"}
    first = service.reference_world(lease.lease_id, "execute", args, "same")
    assert first == service.reference_world(lease.lease_id, "execute", args, "same")
    world.execute.assert_called_once_with("return 123")
    assert worker.score == 0
    assert service._leases[lease.lease_id].events == []
    with pytest.raises(IdempotencyConflict):
        service.reference_world(lease.lease_id, "run", {"ticks": 120}, "same")
    with TestClient(create_app(service)) as client:
        result = client.post(
            f"/v1/leases/{lease.lease_id}/reference-world",
            json={"action": "create", "arguments": {}, "request_id": "create"},
        )
        assert result.status_code == 200, result.text
        assert result.json()["world_id"] == "test"
        assert (
            client.post(
                "/v1/leases/other/reference-world",
                json={"action": "create", "request_id": "new"},
            ).status_code
            == 404
        )
    service.release(lease.lease_id)
    pool.release.assert_called_with(lease.lease_id)
    assert worker.release_count == 1
    with pytest.raises(LeaseNotFound):
        service.reference_world(lease.lease_id, "execute", args, "later")


def test_failed_reference_cleanup_still_releases_runtime(task_spec):
    pool = Mock()
    pool.release.side_effect = RuntimeError("docker failed")
    worker = FakeWorker()
    service = EnvironmentService([worker], reference_worlds=pool)
    lease = service.lease(task_spec)
    with pytest.raises(RuntimeError):
        service.release(lease.lease_id)
    assert worker.release_count == 1
    assert service.health().available == 1


def test_mcp_reference_mutation_updates_resume_pointer(monkeypatch, tmp_path):
    import json
    from scripts import factorio_codex_mcp as mcp
    monkeypatch.setenv("LEASE_ID", "owner")
    monkeypatch.setenv("FACTORIO_RESUME_POINTER_FILE", str(tmp_path / "resume.json"))
    monkeypatch.setenv("FACTORIO_CHECKPOINT_EVERY", "1")
    monkeypatch.setattr(mcp, "_terminal_finalization_only", lambda: False)
    calls = []
    def request(method, path, payload=None):
        calls.append((method, path, payload))
        if path.endswith("/checkpoints"):
            return {"checkpoint_id": "lifecycle:workshop:ep1"}
        return {"world_id": "creative", "result": 42}
    monkeypatch.setattr(mcp, "_envd", request)
    result, failed = mcp._call_tool_impl("factorio_reference_world",
        {"action": "execute", "arguments": {"code": "return 42"}}, request_id="logical")
    assert not failed
    assert json.loads(result)["result"] == 42
    assert calls[0][1] == "/v1/leases/owner/reference-world"
    assert calls[0][2]["request_id"]
    assert json.loads((tmp_path / "resume.json").read_text())["checkpoint"]["checkpoint_id"] == "lifecycle:workshop:ep1"
    assert mcp._tool_route("factorio_reference_world")["route"] == "exclusive_mutation"
