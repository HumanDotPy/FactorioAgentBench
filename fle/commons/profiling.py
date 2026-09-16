"""Bounded, operator-only wall-clock profiling; never part of saved game state."""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import math
import json
import os
from pathlib import Path
import threading
import time
import uuid


TRACE_LIMIT = 128
STAGE_LIMIT = 256
_active: ContextVar[Trace | None] = ContextVar("factorio_profile", default=None)
_file_lock = threading.Lock()


class Trace:
    def __init__(self, operation: str, correlation_id: str | None = None):
        self.trace_id = uuid.uuid4().hex
        self.operation = operation
        self.correlation_id = correlation_id
        self.started_at = time.time()
        self.started = time.perf_counter()
        self.duration_ms = 0.0
        self.failed = False
        self.stages: dict[str, dict] = {}
        self.server_trace_ids: list[str] = []
        self._lock = threading.Lock()
        self._closed = False

    def record(self, name: str, duration_ms: float, failed: bool) -> None:
        with self._lock:
            if self._closed:
                return
            if name not in self.stages and len(self.stages) >= STAGE_LIMIT - 1:
                name = "other"
            stage = self.stages.setdefault(
                name, {"count": 0, "total_ms": 0.0, "max_ms": 0.0, "errors": 0}
            )
            stage["count"] += 1
            stage["total_ms"] += duration_ms
            stage["max_ms"] = max(stage["max_ms"], duration_ms)
            stage["errors"] += int(failed)

    def finish(self) -> None:
        with self._lock:
            self.duration_ms = (time.perf_counter() - self.started) * 1000
            self._closed = True

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "trace_id": self.trace_id,
                "correlation_id": self.correlation_id,
                "operation": self.operation,
                "started_at_unix": self.started_at,
                "duration_ms": self.duration_ms,
                "failed": self.failed,
                "stages": {name: dict(values) for name, values in self.stages.items()},
                "server_trace_ids": list(self.server_trace_ids),
            }


def current_trace() -> Trace | None:
    return _active.get()


def accept_server_trace(headers) -> None:
    trace = current_trace()
    if trace is None or headers is None:
        return
    value = headers.get("X-Factorio-Trace-Id", "")
    if len(value) == 32 and all(char in "0123456789abcdef" for char in value):
        if len(trace.server_trace_ids) < 32:
            trace.server_trace_ids.append(value)


def persist_trace(directory: Path, trace: Trace, max_bytes: int = 5_000_000) -> None:
    """Two bounded files per MCP process; diagnostics must never fail an action."""
    try:
        encoded = (
            json.dumps({"schema_version": "factorio-profile-v1", **trace.snapshot()})
            + "\n"
        ).encode()
        with _file_lock:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"mcp-{os.getpid()}.jsonl"
            if path.exists() and path.stat().st_size + len(encoded) > max_bytes:
                os.replace(path, path.with_suffix(".previous.jsonl"))
            with path.open("ab") as stream:
                stream.write(encoded)
    except OSError:
        # Diagnostics cannot invalidate a successfully committed world mutation.
        pass


@contextmanager
def activate(trace: Trace | None):
    token = _active.set(trace)
    try:
        yield trace
    except BaseException:
        if trace is not None:
            trace.failed = True
        raise
    finally:
        _active.reset(token)
        if trace is not None:
            trace.finish()


@contextmanager
def span(name: str):
    trace = _active.get()
    if trace is None:
        yield
        return
    started = time.perf_counter()
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        trace.record(name, (time.perf_counter() - started) * 1000, failed)


def timed(name: str):
    """Instrument synchronous stages without inspecting arguments or results."""

    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if _active.get() is None:
                return function(*args, **kwargs)
            with span(name):
                return function(*args, **kwargs)

        return wrapped

    return decorate


@contextmanager
def profiled_lock(lock):
    with span("lease.lock_wait"):
        lock.acquire()
    try:
        yield
    finally:
        lock.release()


class ProfileStore:
    """Per-lease rolling window. Configuration never waits for the world lock."""

    def __init__(self):
        self._lock = threading.Lock()
        self._traces: deque[dict] = deque(maxlen=TRACE_LIMIT)
        self._until = 0.0
        self._sample_every = 1
        self._seen = 0
        self._completed = 0
        self._generation = 0

    def configure(
        self,
        *,
        enabled: bool,
        duration_seconds: int = 300,
        sample_every: int = 1,
        clear: bool = False,
    ) -> dict:
        if not 1 <= duration_seconds <= 3600 or not 1 <= sample_every <= 1000:
            raise ValueError("duration_seconds must be 1..3600; sample_every 1..1000")
        with self._lock:
            if clear:
                self._traces.clear()
                self._completed = 0
                self._generation += 1
            self._seen = 0
            self._sample_every = sample_every
            self._until = time.monotonic() + duration_seconds if enabled else 0.0
        return self.report()

    def begin(self, operation: str, correlation_id: str | None = None):
        with self._lock:
            if time.monotonic() >= self._until:
                return None
            self._seen += 1
            if (self._seen - 1) % self._sample_every:
                return None
            return self._generation, Trace(operation, correlation_id)

    def complete(self, generation: int, trace: Trace) -> None:
        snapshot = trace.snapshot()
        with self._lock:
            if generation == self._generation:
                self._traces.append(snapshot)
                self._completed += 1

    def report(self) -> dict:
        with self._lock:
            traces = list(self._traces)
            remaining = max(0.0, self._until - time.monotonic())
            settings = {
                "enabled": remaining > 0,
                "remaining_seconds": remaining,
                "sample_every": self._sample_every,
                "completed_samples": self._completed,
                "evicted_samples": max(0, self._completed - len(traces)),
            }
        # Completed snapshots are immutable internally; copy outside the lock
        # so an operator's large report cannot stall completion or toggling.
        traces = [
            {
                **trace,
                "stages": {
                    name: dict(values) for name, values in trace["stages"].items()
                },
                "server_trace_ids": list(trace["server_trace_ids"]),
            }
            for trace in traces
        ]
        operations: dict[str, list[float]] = {}
        stages: dict[str, dict] = {}
        for trace in traces:
            operations.setdefault(trace["operation"], []).append(trace["duration_ms"])
            for name, values in trace["stages"].items():
                row = stages.setdefault(
                    name, {"count": 0, "total_ms": 0.0, "max_ms": 0.0, "errors": 0}
                )
                for key in ("count", "total_ms", "errors"):
                    row[key] += values[key]
                row["max_ms"] = max(row["max_ms"], values["max_ms"])
        summaries = {}
        for name, values in operations.items():
            ordered = sorted(values)
            summaries[name] = {
                "count": len(values),
                "mean_ms": sum(values) / len(values),
                "p50_ms": ordered[math.ceil(len(values) * 0.50) - 1],
                "p95_ms": ordered[math.ceil(len(values) * 0.95) - 1],
                "max_ms": ordered[-1],
            }
        return {
            "schema_version": "factorio-profile-v1",
            **settings,
            "trace_limit": TRACE_LIMIT,
            "timing_semantics": "inclusive wall time; nested stages must not be summed",
            "operations": summaries,
            "stages": stages,
            "traces": traces,
        }
