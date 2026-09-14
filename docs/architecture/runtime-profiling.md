# Active-run profiling

For [realtime programs](realtime-program-execution.md), the admission request
measures validation and durable registration, not program execution. Job status
records queue wait and execution wall seconds separately. Execution and checkpoint
work occur after the acceptance response; do not compare admission latency to an
old synchronous execution duration as if they measured the same work. Model and
harness timing still require the runner's measurements.

The local envd service supports operator-only, per-lease wall-clock profiling.
Enable it while a run continues; no world reset, lease restart, explicit simulation
advance, or agent tool call is required. The service and MCP process must already
be running code containing this instrumentation. Updating files does not patch
older Python processes in memory. Do not restart an active run just to enable it.
The AgentENV gateway does not expose this local runtime profiler.
An instrumented local service advertises `features.runtime_profiling=true` in
`GET /v1/health`.

From the repository root, with the active lease's `ENVD_URL` and `LEASE_ID`:

```powershell
uv run python scripts/factorio_profile.py enable --seconds 300 --clear
uv run python scripts/factorio_profile.py report --output output/profile.json
uv run python scripts/factorio_profile.py disable
```

Alternatively pass `--url http://host:port --lease <lease-id>` to each command.
`--every 10` samples every tenth HTTP operation, beginning with the first.
Profiling defaults to off, automatically expires after the requested duration
(maximum one hour), and can be disabled without waiting for an executing action.
Settings take effect for new requests. In-flight samples finish normally;
`--clear` also prevents older in-flight samples from repopulating the window.
Configuration does not renew the lease or mutate its intervention sequence.

The corresponding privileged HTTP endpoints are:

- `PUT /v1/leases/{lease_id}/profiling` with
  `{"enabled":true,"duration_seconds":300,"sample_every":1,"clear":true}`.
- `GET /v1/leases/{lease_id}/profiling` returns settings, summaries, and traces.

These use the same operator access boundary as envd's other privileged endpoints;
they are deliberately absent from the MCP tool manifest. Profiles are not included
in observations, execution receipts, scores, checkpoints, or resume state.

## Reading timings

The report retains the latest 128 completed sampled HTTP operations per lease,
with at most 256 stage names per trace. Summaries cover **only that rolling
window**, not the run lifetime. `completed_samples` and `evicted_samples` expose
retention loss. Request summaries show count, mean, p50, p95 (nearest rank), and
maximum milliseconds. Stages show invocation count, inclusive wall time,
maximum call time, and raised-exception count. Nested timings overlap: do not
sum `service.execute`, `runtime.evaluate`, tool, and RCON totals.

Stages distinguish lease-lock contention, Python evaluation, complete tool calls
(including sleeps and polling), RCON action round trips, Lua response decoding,
benchmark telemetry, state hashing, observation capture, checkpoint export and
persistence, and camera work. `rcon.action.*` measures transport plus Factorio
processing and Lua serialization; it does not isolate engine CPU time. This is
wall-clock instrumentation, not a CPU sampling profiler. It does not change
simulation speed, checkpoint policy, or camera settings.
Instrumentation has a small execution cost and can perturb wall-time-sensitive
behavior while Factorio is unpaused; use sampling to reduce that cost.

The service request envelope includes application dispatch and response
construction, but excludes delivery over the network. Trace failure marks HTTP
errors or uncaught exceptions; a semantic action error may still be HTTP 200.
No program source, tool arguments/results, raw RCON commands, or hidden verifier
values are recorded. Context follows evaluation into its worker thread, with
separate collectors for concurrent requests and leases.

## MCP correlation and persistence

When `FACTORIO_TOOL_ARTIFACT_DIR` is configured (as in benchmark runs), the MCP
adapter measures its dispatch envelope, individual envd requests, execution
artifact writing, and camera handling. It sends an opaque call ID; sampled
envd responses return `X-Factorio-Trace-Id`. Only calls with a sampled response
are written to `<artifact-dir>/profiling/mcp-<pid>.jsonl`. Each process rotates
at approximately 5 MB and keeps one previous file. Server trace `correlation_id`
matches the MCP `trace_id`; MCP records also list up to 32 server trace IDs.
Sampling is per HTTP operation, so a call's execute, checkpoint, and camera
requests may not all be sampled.

MCP timings exclude harness scheduling, model thinking, the adapter's dispatch
queue, final JSON-RPC encoding, stdout delivery, and profiling-file writes.
There are no extra profiling HTTP calls, and disabled runs write no profile
files. A small bounded MCP timing envelope is collected before the first HTTP
response signals whether it was sampled. Without an artifact directory, only
the server-side profile is available. File-write failures cannot fail an action.
Use the report command to export server traces before releasing the lease or
restarting envd; server traces are in memory and are not restored with a run.
