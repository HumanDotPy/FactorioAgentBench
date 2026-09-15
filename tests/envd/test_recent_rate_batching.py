import pytest

from fle.envd.backend import FLEWorker


pytestmark = pytest.mark.no_factorio


RATES = {5: 12.5, 60: 120.0, 300: 299.5}
WINDOWS = [5, 60, 300]
ITEMS = ["copper-plate", "iron-plate"]
STATS = {"input": {}, "output": {"iron-plate": 100, "copper-plate": 50}}


class _BatchNamespace:
    def __init__(self):
        self.calls = []

    def _get_recent_rate(self, item_name, window_seconds):
        self.calls.append((item_name, window_seconds))
        if isinstance(item_name, list):
            return {
                "rates": {
                    item: {
                        str(window): {"dynamic_per_minute": RATES[window]}
                        for window in window_seconds
                    }
                    for item in item_name
                },
                "observed_at_tick": 600,
            }
        return {"dynamic_per_minute": RATES[window_seconds]}


class _LegacyNamespace:
    def __init__(self):
        self.calls = []

    def _get_recent_rate(self, item_name, window_seconds):
        self.calls.append((item_name, window_seconds))
        if isinstance(item_name, list):
            return {"error": "item_name must be a non-empty string"}
        return {"dynamic_per_minute": RATES[window_seconds]}


class _RaisingBatchNamespace:
    def __init__(self):
        self.calls = []

    def _get_recent_rate(self, item_name, window_seconds):
        self.calls.append((item_name, window_seconds))
        if isinstance(item_name, list):
            raise TypeError("unsupported batch query")
        return {"dynamic_per_minute": RATES[window_seconds]}


class _Instance:
    def __init__(self, namespace):
        self.first_namespace = namespace


def _worker(namespace):
    worker = FLEWorker.__new__(FLEWorker)
    worker.instance = _Instance(namespace)
    worker._production_history = []
    worker._flow_history = []
    worker._contract_production_baseline = {"input": {}, "output": {}}
    return worker


def _expected_rates():
    return {
        "automated_rates_5s": {"copper-plate": 12.5, "iron-plate": 12.5},
        "automated_rates_60s": {"copper-plate": 120, "iron-plate": 120},
        "automated_rates_300s": {"copper-plate": 299.5, "iron-plate": 299.5},
    }


def test_snapshot_batches_all_items_and_windows_into_one_query():
    namespace = _BatchNamespace()
    worker = _worker(namespace)

    production, _ = worker._compact_production_snapshot(STATS, 600)

    assert namespace.calls == [(ITEMS, WINDOWS)]
    for field, expected in _expected_rates().items():
        assert production[field] == expected
        assert list(production[field]) == ITEMS
    assert production["automated_rates_available"] is True


def test_snapshot_falls_back_to_per_item_queries_with_identical_values():
    namespace = _LegacyNamespace()
    worker = _worker(namespace)

    production, _ = worker._compact_production_snapshot(STATS, 600)

    assert namespace.calls == [(ITEMS, WINDOWS)] + [
        (item, window) for item in ITEMS for window in WINDOWS
    ]
    for field, expected in _expected_rates().items():
        assert production[field] == expected
        assert list(production[field]) == ITEMS
    assert production["automated_rates_available"] is True


def test_snapshot_falls_back_when_batched_query_raises():
    namespace = _RaisingBatchNamespace()
    worker = _worker(namespace)

    production, _ = worker._compact_production_snapshot(STATS, 600)

    assert namespace.calls == [(ITEMS, WINDOWS)] + [
        (item, window) for item in ITEMS for window in WINDOWS
    ]
    for field, expected in _expected_rates().items():
        assert production[field] == expected
    assert production["automated_rates_available"] is True


def test_snapshot_without_rate_endpoint_reports_unavailable():
    worker = _worker(object())

    production, _ = worker._compact_production_snapshot(STATS, 600)

    assert production["automated_rates_5s"] == {}
    assert production["automated_rates_60s"] == {}
    assert production["automated_rates_300s"] == {}
    assert production["automated_rates_available"] is False
