import pytest

from fle.envd.backend import ENTITY_DETAILS_QUERY_RADIUS, FLEWorker


pytestmark = pytest.mark.no_factorio


class _Namespace:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def get_entities(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.values


class _Instance:
    def __init__(self, namespace):
        self.first_namespace = namespace


def _worker(values):
    namespace = _Namespace(values)
    worker = FLEWorker.__new__(FLEWorker)
    worker.instance = _Instance(namespace)
    return worker, namespace


def test_entity_details_default_radius_is_bounded_and_disclosed():
    worker, namespace = _worker(
        [{"name": "stone-furnace"}, {"name": "iron-chest"}, {"name": "pipe"}]
    )

    result = worker._query_entity_details(
        entity_type=None, area={"x": 1.0, "y": 2.0}, limit=2
    )

    assert namespace.calls[0][1]["radius"] == ENTITY_DETAILS_QUERY_RADIUS
    assert result["effective_radius"] == ENTITY_DETAILS_QUERY_RADIUS
    assert result["returned"] == 2
    assert result["total"] == 3
    assert result["truncated"] is True


def test_entity_details_explicit_radius_is_respected():
    worker, namespace = _worker([{"name": "stone-furnace"}])

    result = worker._query_entity_details(
        entity_type=None, area={"x": 1.0, "y": 2.0, "radius": 10}, limit=8
    )

    assert namespace.calls[0][1]["radius"] == 10.0
    assert result["effective_radius"] == 10.0
    assert result["truncated"] is False
