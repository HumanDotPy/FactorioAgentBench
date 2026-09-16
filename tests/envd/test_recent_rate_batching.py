import pytest

from fle.envd.backend import FLEWorker


pytestmark = pytest.mark.no_factorio


RATES = {5: 12.5, 60: 120.0, 300: 299.5}
WINDOWS = [5, 60, 300]
ITEMS = ["copper-plate", "iron-plate"]
RANKED_ITEMS = ["iron-plate", "copper-plate"]
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

    assert namespace.calls == [(RANKED_ITEMS, WINDOWS)]
    for field, expected in _expected_rates().items():
        assert production[field] == expected
        assert list(production[field]) == RANKED_ITEMS
    assert production["automated_rates_available"] is True


def test_snapshot_falls_back_to_per_item_queries_with_identical_values():
    namespace = _LegacyNamespace()
    worker = _worker(namespace)

    production, _ = worker._compact_production_snapshot(STATS, 600)

    assert namespace.calls == [(RANKED_ITEMS, WINDOWS)] + [
        (item, window) for item in RANKED_ITEMS for window in WINDOWS
    ]
    for field, expected in _expected_rates().items():
        assert production[field] == expected
        assert list(production[field]) == RANKED_ITEMS
    assert production["automated_rates_available"] is True


def test_snapshot_falls_back_when_batched_query_raises():
    namespace = _RaisingBatchNamespace()
    worker = _worker(namespace)

    production, _ = worker._compact_production_snapshot(STATS, 600)

    assert namespace.calls == [(RANKED_ITEMS, WINDOWS)] + [
        (item, window) for item in RANKED_ITEMS for window in WINDOWS
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
    assert production["raw_rate_spans_seconds"]["300s"] == 0.0


def test_snapshot_ranks_items_by_counter_and_flags_truncation():
    namespace = _BatchNamespace()
    worker = _worker(namespace)
    stats = {"input": {}, "output": {f"item-{index:02d}": index for index in range(40)}}

    production, _ = worker._compact_production_snapshot(stats, 600)

    assert production["automated_rates_items_truncated"] is True
    assert production["automated_rates_items_omitted"] == 8
    assert "item-39" in production["automated_rates_300s"]
    assert "item-00" not in production["automated_rates_300s"]
    items, _ = namespace.calls[0]
    assert len(items) == 32
    assert items[0] == "item-39"


def test_short_history_exposes_the_effective_rate_span():
    worker = _worker(object())
    worker._record_production_sample(0, {"input": {}, "output": {}})
    worker._record_production_sample(300, {"input": {}, "output": {"iron-plate": 30}})

    production, _ = worker._compact_production_snapshot(
        {"input": {}, "output": {"iron-plate": 60}}, 600
    )

    assert production["raw_rate_spans_seconds"]["300s"] == 10.0
    assert production["raw_rates_300s"]["iron-plate"] == 360.0


def test_history_retention_keeps_more_than_the_old_sample_cap():
    worker = _worker(object())
    for tick in range(301):
        worker._record_production_sample(
            tick, {"input": {}, "output": {"iron-plate": tick}}
        )

    assert len(worker._production_history) == 301


def test_300s_window_spans_the_requested_window_with_one_hz_samples():
    worker = _worker(object())
    for tick in range(0, 400 * 60, 60):
        worker._record_production_sample(
            tick, {"input": {}, "output": {"iron-plate": tick // 60}}
        )

    production, _ = worker._compact_production_snapshot(
        {"input": {}, "output": {"iron-plate": 400}}, 400 * 60
    )

    assert production["raw_rate_spans_seconds"]["300s"] == 300.0


def test_history_drops_samples_older_than_retention_but_keeps_baseline():
    worker = _worker(object())
    for tick in range(0, 600 * 60, 60):
        worker._record_production_sample(
            tick, {"input": {}, "output": {"iron-plate": tick // 60}}
        )

    latest = worker._production_history[-1]["tick"]
    assert worker._production_history[0]["tick"] <= latest - 18000
    assert worker._production_history[1]["tick"] >= latest - 18000
