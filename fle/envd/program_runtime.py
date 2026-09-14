"""Provider-independent program admission, execution and public event delivery.

Only the executor touches the worker. Reads are serviced on that same execution
thread at controller safe points, including native action polling loops.
"""

from __future__ import annotations

import copy
import json
import os
import threading
import time
import uuid
from collections import deque
from concurrent.futures import Future
from contextlib import nullcontext
from pathlib import Path

from fle.envd.errors import IdempotencyConflict


class ProgramCancelled(RuntimeError):
    pass


class ProgramRuntime:
    MAX_PENDING = 8
    MAX_EVENTS = 256

    def __init__(
        self,
        root,
        execute,
        checkpoint,
        read_context,
        state=None,
        execution_context=nullcontext,
        poll_events=None,
    ):
        self.condition = threading.Condition(threading.RLock())
        self.runtime_id = (state or {}).get("runtime_id", str(uuid.uuid4()))
        self.directory = Path(root) / "programs" / self.runtime_id
        self.directory.mkdir(parents=True, exist_ok=True)
        self.execute = execute
        self.checkpoint = checkpoint
        self.read_context = read_context
        self.execution_context = execution_context
        self.poll_events = poll_events
        self.last_poll = 0.0
        self.episode_terminal = bool((state or {}).get("episode_terminal", False))
        self.terminal_program_id = (state or {}).get("terminal_program_id")
        self.terminal_event = (state or {}).get("terminal_event")
        self.jobs = copy.deepcopy((state or {}).get("jobs", {}))
        self.cursor = int((state or {}).get("cursor", 0))
        self.events = deque((state or {}).get("events", []), maxlen=self.MAX_EVENTS)
        self.reads = deque()
        self.active = None
        self.closed = False
        self.failure = None
        self.local = threading.local()
        self.latest_checkpoint = None
        self.thread = None
        # The journal covers admissions after the restored world checkpoint.
        # Re-execution is against that restored world, never the old live world.
        journal = self.directory / "admissions.jsonl"
        if journal.exists():
            lines = journal.read_bytes().splitlines(keepends=True)
            valid_bytes = 0
            for index, line in enumerate(lines):
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    if index == len(lines) - 1:
                        with journal.open("r+b") as file:
                            file.truncate(valid_bytes)
                        break  # remove an interrupted final append before reuse
                    raise
                valid_bytes += len(line)
                if not line.endswith(b"\n"):
                    with journal.open("ab") as file:
                        file.write(b"\n")
                if entry["operation"] == "submit":
                    job = entry["job"]
                    self.jobs.setdefault(job["program_id"], job)
                elif entry["operation"] == "cancel":
                    job = self.jobs.get(entry["program_id"])
                    if job and job["status"] in {"queued", "running"}:
                        cancel_suffix = False
                        for key, dependent in self.jobs.items():
                            cancel_suffix = cancel_suffix or key == entry["program_id"]
                            if cancel_suffix and dependent["status"] in {
                                "queued",
                                "running",
                            }:
                                dependent["status"] = "cancelled"
        if any(job["status"] == "running" for job in self.jobs.values()):
            raise ValueError("Cannot restore an in-flight Python stack")
        self.pending = deque(
            key for key, job in self.jobs.items() if job["status"] == "queued"
        )
        self.requests = {job["request_id"]: key for key, job in self.jobs.items()}
        self.recent = deque(self.jobs, maxlen=32)

    def _journal(self, entry):
        with (self.directory / "admissions.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, separators=(",", ":")) + "\n")
            file.flush()
            os.fsync(file.fileno())

    def start(self):
        self.thread = threading.Thread(
            target=self._run, name="factorio-programs", daemon=True
        )
        self.thread.start()

    def export(self):
        with self.condition:
            return copy.deepcopy(
                {
                    "runtime_id": self.runtime_id,
                    "jobs": self.jobs,
                    "cursor": self.cursor,
                    "events": list(self.events),
                    "episode_terminal": self.episode_terminal,
                    "terminal_program_id": self.terminal_program_id,
                    "terminal_event": self.terminal_event,
                }
            )

    def _event(self, kind, job):
        self.cursor += 1
        self.events.append(
            {
                "sequence": self.cursor,
                "kind": kind,
                "program_id": job["program_id"],
                "status": job["status"],
                "tick": job.get("tick"),
                "reason": job.get("error"),
            }
        )
        self.condition.notify_all()

    def submit(self, code, request_id, code_hash, template=None):
        with self.condition:
            existing = self.requests.get(request_id)
            if existing:
                job = self.jobs[existing]
                if job["code_sha256"] != code_hash:
                    raise IdempotencyConflict(
                        "request_id already belongs to a different program"
                    )
                return self._view(job)
            if self.closed or self.failure or self.episode_terminal:
                raise RuntimeError(self.failure or "Program runtime is closed")
            if len(self.pending) + bool(self.active) >= self.MAX_PENDING:
                raise ValueError(
                    "Program queue is full; await an event before submitting more work"
                )
            job = {
                "program_id": str(uuid.uuid4()),
                "request_id": request_id,
                "code": code,
                "code_sha256": code_hash,
                "status": "queued",
                "step": 0,
                "current_action": None,
                "cancel_requested": False,
                "accepted_at": time.time(),
                "template": template,
                "tick": None,
            }
            self._journal({"operation": "submit", "job": job})
            self.jobs[job["program_id"]] = job
            self.pending.append(job["program_id"])
            self.requests[request_id] = job["program_id"]
            self.recent.append(job["program_id"])
            self._event("program_accepted", job)
            return self._view(job)

    def _view(self, job):
        return {
            **copy.deepcopy(
                {
                    key: value
                    for key, value in job.items()
                    if key not in {"code", "request_id", "result_file"}
                }
            ),
            "event_cursor": self.cursor,
            "queue_length": len(self.pending),
        }

    def status(self, program_id=None, include_result=False):
        result_file = None
        with self.condition:
            selected = (
                [self.jobs[program_id]]
                if program_id
                else [self.jobs[key] for key in self.recent]
            )
            result = {
                "schema_version": "factorio-program-status-v1",
                "runtime_id": self.runtime_id,
                "event_cursor": self.cursor,
                "queue_length": len(self.pending),
                "active_program_id": self.active,
                "failure": self.failure,
                "terminal_program_id": self.terminal_program_id,
                "terminal_event": self.terminal_event,
                "programs": [self._view(j) for j in selected],
                "checkpoint": self.latest_checkpoint,
            }
            if include_result and program_id:
                job = self.jobs[program_id]
                result_file = job.get("result_file")
            result = copy.deepcopy(result)
        if include_result and program_id:
            result["result"] = (
                json.loads((self.directory / result_file).read_text(encoding="utf-8"))
                if result_file
                else None
            )
        return result

    def cancel(self, program_id):
        with self.condition:
            job = self.jobs[program_id]
            if job["status"] in {"queued", "running"}:
                self._journal({"operation": "cancel", "program_id": program_id})
                job["cancel_requested"] = True
                if job["status"] == "queued":
                    suffix = list(self.pending)
                    suffix = suffix[suffix.index(program_id) + 1 :]
                    self.pending.remove(program_id)
                    job["status"] = "cancelled"
                    self._event("program_cancelled", job)
                    for key in suffix:
                        self._journal({"operation": "cancel", "program_id": key})
                        dependent = self.jobs[key]
                        dependent["status"] = "cancelled"
                        dependent["cancel_requested"] = True
                        dependent["error"] = "Preceding queued program was cancelled"
                        self.pending.remove(key)
                        self._event("program_cancelled", dependent)
                self.condition.notify_all()
            return self._view(job)

    def cancelled(self):
        with self.condition:
            return bool(self.active and self.jobs[self.active]["cancel_requested"])

    def boundary(self, action=None):
        if getattr(self.local, "reading", False):
            return
        self.pump()
        if self.cancelled():
            raise ProgramCancelled(
                "Program cancelled; completed actions remain applied"
            )
        if self.blocked():
            raise RuntimeError(self.blocked())
        if action:
            with self.condition:
                if self.active:
                    job = self.jobs[self.active]
                    job["step"] += 1
                    job["current_action"] = action

    def blocked(self):
        with self.condition:
            return self.jobs[self.active].get("blocker") if self.active else None

    def action_result(self, action, result):
        if getattr(self.local, "reading", False):
            return
        if action in {
            "place_grid",
            "repeat_pattern",
            "place_path",
            "place_power_line",
            "submit_actions",
            "resume_actions",
        } and isinstance(result, dict):
            if result.get("status") in {"partial", "halted", "failed"}:
                with self.condition:
                    if self.active:
                        self.jobs[self.active]["blocker"] = (
                            f"{action} stopped with a partial result: "
                            + json.dumps(result, default=str)[:1500]
                        )

    def read(self, callback, timeout=10):
        future = Future()
        with self.condition:
            if self.closed or self.failure:
                raise RuntimeError(self.failure or "Program runtime is closed")
            if len(self.reads) >= 32:
                raise ValueError("Too many pending reads")
            self.reads.append((future, callback))
            self.condition.notify_all()
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            raise TimeoutError(
                "No observation safe point reached; inspect program status"
            ) from None

    def pump(self):
        if getattr(self.local, "reading", False):
            return
        self.local.reading = True
        try:
            if (
                self.poll_events
                and not self.episode_terminal
                and time.monotonic() - self.last_poll >= 1
            ):
                self.last_poll = time.monotonic()
                with self.read_context():
                    events = self.poll_events()
                with self.condition:
                    for event in events:
                        self.cursor += 1
                        self.events.append({**event, "sequence": self.cursor})
                        if event.get("terminal"):
                            self.episode_terminal = True
                            self.terminal_event = event
                            if self.active:
                                self.jobs[self.active]["cancel_requested"] = True
                            for key in list(self.pending):
                                self.cancel(key)
                    if events:
                        self.condition.notify_all()
            # Bound each batch so observation traffic cannot starve execution.
            for _ in range(4):
                with self.condition:
                    if not self.reads:
                        break
                    future, callback = self.reads.popleft()
                if not future.set_running_or_notify_cancel():
                    continue
                try:
                    with self.read_context():
                        result = callback()
                    future.set_result(result)
                except Exception as exc:
                    future.set_exception(exc)
        finally:
            self.local.reading = False

    def wait(self, after, timeout=30):
        if after < 0 or not 0 <= timeout <= 30:
            raise ValueError(
                "after must be nonnegative; timeout must be between 0 and 30 seconds"
            )
        deadline = time.monotonic() + timeout
        with self.condition:
            if after > self.cursor:
                raise ValueError("event cursor is ahead of this runtime")
            while self.cursor <= after and not self.closed and not self.failure:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.condition.wait(remaining)
            return {
                "event_cursor": self.cursor,
                "events": copy.deepcopy(
                    [e for e in self.events if e["sequence"] > after]
                ),
                "cursor_expired": bool(
                    self.events and after < self.events[0]["sequence"] - 1
                ),
                "closed": self.closed,
                "failure": self.failure,
            }

    def _run(self):
        try:
            while True:
                with self.execution_context():
                    self.pump()
                with self.condition:
                    if self.closed:
                        return
                    job = self.jobs[self.pending[0]] if self.pending else None
                    if job is None:
                        self.condition.wait(timeout=1)
                        continue
                with self.execution_context():
                    with self.condition:
                        if self.closed or job["status"] != "queued":
                            continue
                        self.pending.popleft()
                        self.active = job["program_id"]
                        job["started_at"] = time.time()
                        job["queue_wait_seconds"] = (
                            job["started_at"] - job["accepted_at"]
                        )
                        job["status"] = "running"
                        self._event("program_started", job)
                    self._run_job(job)
        except Exception as exc:
            with self.condition:
                self.failure = f"Program executor stopped: {type(exc).__name__}: {exc}"
                self.condition.notify_all()
        finally:
            with self.condition:
                for future, _ in self.reads:
                    if not future.done():
                        future.set_exception(
                            RuntimeError(self.failure or "Runtime closed")
                        )
                self.reads.clear()

    def _run_job(self, job):
        infrastructure_error = None
        try:
            result = self.execute(job["code"], job["request_id"], job.get("template"))
            result_file = job["program_id"] + ".json"
            result_path = self.directory / result_file
            temporary = result_path.with_suffix(".tmp")
            temporary.write_text(result.model_dump_json(), encoding="utf-8")
            os.replace(temporary, result_path)
            with self.condition:
                job["result_file"] = result_file
                job.pop("code", None)
                job["tick"] = result.event.ticks
                job["status"] = (
                    "cancelled"
                    if job["cancel_requested"]
                    else ("failed" if result.event.error else "completed")
                )
                if result.event.error:
                    job["error"] = result.event.result[-2000:]
                self.episode_terminal = self.episode_terminal or bool(
                    result.terminal_reason
                    or any(
                        e.kind in {"contract_fulfilled", "contract_expired"}
                        for e in result.events
                    )
                )
                if self.episode_terminal:
                    self.terminal_program_id = job["program_id"]
        except Exception as exc:
            infrastructure_error = exc
            with self.condition:
                job["status"] = "failed"
                job["error"] = f"{type(exc).__name__}: {exc}"
        with self.condition:
            self.active = None
            job["completed_at"] = time.time()
            job["execution_wall_seconds"] = job["completed_at"] - job["started_at"]
            self._event("program_" + job["status"], job)
            if job["status"] != "completed" or self.episode_terminal:
                for key in self.pending:
                    pending = self.jobs[key]
                    pending["status"] = "cancelled"
                    pending["error"] = (
                        "Preceding program failed, was cancelled, or ended the episode"
                    )
                    self._event("program_cancelled", pending)
                self.pending.clear()
        # Do not certify an unknown runtime failure as a resumable world.
        if infrastructure_error:
            raise infrastructure_error
        self.publish_checkpoint(self.checkpoint())

    def publish_checkpoint(self, checkpoint):
        with self.condition:
            self.latest_checkpoint = checkpoint.model_dump(mode="json")
        path = self.directory / "checkpoint.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.latest_checkpoint), encoding="utf-8")
        os.replace(temporary, path)

    def stop_epoch(self):
        """Prevent pending work from crossing a privileged epoch boundary."""
        with self.condition:
            self.episode_terminal = True
            for key in list(self.pending):
                self.cancel(key)
            if self.active:
                self.cancel(self.active)

    def close(self):
        with self.condition:
            self.closed = True
            for key in list(self.pending):
                self.cancel(key)
            if self.active:
                self.jobs[self.active]["cancel_requested"] = True
            self.condition.notify_all()
        if self.thread:
            self.thread.join(timeout=15)
            if self.thread.is_alive():
                raise RuntimeError(
                    "Program executor did not stop; worker remains quarantined"
                )
