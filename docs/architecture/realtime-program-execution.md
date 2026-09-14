# Continuous execution through ordinary MCP harnesses

`FactorioTaskSpec.execution_mode` selects `turn_based` or `realtime`. The adaptive
and progression runners default to realtime for OpenCode and Hermes; select
`--execution-mode turn_based` for a paused evaluation. The native chat-completions
harness retains turn-based execution. No Responses API or provider-specific
asynchronous tool protocol is required.

Realtime is a different evaluation task: the episode runs at 1x during reasoning,
network latency, observations and agent event waits. Agents cannot pause or speed
up this mode. Exact checkpoint capture and privileged episode lifecycle operations
may briefly pause the world. Record execution mode with results and do not compare
its tick deadlines or ratings as if inference time were free. Observations use
the authoritative episode clock, not the legacy action-duration accumulator.

## Admission and execution

`POST /v1/leases/{id}/programs` takes `code` and a required `request_id`. After
bounded source and action-policy validation, envd durably journals admission and
returns HTTP 202 with a program handle, status and event cursor. This confirms
acceptance, never future inventory availability or successful placement. Identical
keyed retries return the same handle; different source with the same key conflicts.
There are at most eight queued/running programs per lease.

A single executor runs accepted programs in order. Character actions never run
concurrently; native factory production, crafting and research may overlap. The
existing Python composition and construction tools remain the instruction set.
The runtime records current semantic action and step count, not a Python program
counter. Programs have a 600-second wall-clock execution failsafe in this mode.

`factorio_execute_program` returns the acceptance immediately without waiting for
execution, checkpoint export, output artifact creation or a camera image.
`factorio_get_program_status(program_id)` returns progress and, after completion,
the normal compact execution receipt backed by a retrievable output artifact.
Program results are stored once on disk; routine status reads include only bounded
recent metadata. Admission lookup and pending-queue operations use indexes rather
than scanning completed results.

Cancellation stops pending work immediately. Active cancellation is cooperative:
AST and semantic-tool boundaries stop further work; walking, harvesting and waits
also check inside their polling loops and clean up the native action. Already
completed interactions remain applied. Structured partial construction failures
stop the program rather than silently treating the batch as complete. Failure or
cancellation cancels the queued dependent suffix; the agent observes and submits
replacement work. Programs are not arbitrary resumable Python coroutines.

## Reads and events

Live observation, camera, render and state-query requests use a bounded mailbox.
The execution thread services it at safe points, including native controller
polls. It does not concurrently mutate the worker's Python namespace. Read
callbacks are excluded from program action attribution. A read that cannot reach
a safe point within ten seconds fails explicitly rather than claiming stale data
is current. Status and cancellation use a separate short-lived synchronization
lock. Memory and template libraries retain their own synchronization.

`factorio_await_events(event_cursor, timeout_seconds=30)` suspends the agent for at
most 30 seconds while execution and the factory continue. It returns ordered
public program/game events; cursor expiry is explicit when the bounded event ring
has evicted older events. Research, attack and new-order notifications are sampled
on the executor, with public terminal conditions checked independently of program
submission. No hidden scoring values are exposed in notifications.

The general prompt tells agents to plan useful independent work while programs
run and await events when progress depends on information. It does not reward
busywork or prohibit waiting. A `wait(...)` inside Python still deliberately
orders subsequent commands in that program. Use the MCP event wait to sleep only
the agent and leave the character executor available.

OpenCode and Hermes receive the same ordinary MCP schemas. Their runners observe
executor status independently of tool calls, persist checkpoint pointers, and
resume the established conversation after a nonterminal provider stop. Pending
work causes an event wait before continuation. Provider transport remains the
harness's responsibility; this implementation does not enable WebSockets.

## Persistence and lifecycle

The admission journal, job metadata, result files and checkpoint manifest live
under `FLE_LIFECYCLE_DIR/programs/<runtime-id>`. Initial provisioning establishes a
world checkpoint before admission. Every completed program produces a world and
service checkpoint under the execution lock before the next program starts.
Checkpoint capture pauses the engine so its multiple reads describe one instant.
An external checkpoint cannot capture a running Python stack.

The service checkpoint includes completed jobs, pending jobs and event cursors.
Restoration reconciles later admissions and cancellations from the journal. Work
after the selected world checkpoint is replayed only against that restored world;
it is never blindly replayed against an existing live world. The operator endpoint
`GET /v1/program-runtimes/{runtime-id}/checkpoint` supplies the latest committed
world when the runner or MCP process missed a pointer update. Arbitrary host Python
stacks are not serialized. Infrastructure failures stop admission/execution rather
than certifying an uncertain state as resumable.

Finalization cancels outstanding work before the epoch boundary. Release waits
for the executor to stop; a worker that fails to stop remains quarantined rather
than being allocated to another lease. Checkpoints and journals must stay together
for recovery. This mode requires a checkpoint-capable local envd worker.

## Verification

`tests/envd/test_program_runtime.py` exercises early admission, ordering, live reads,
idempotency, queue limits, cancellation, event delivery and checkpoint boundaries.
Harness and MCP tests cover provider-independent schemas, pacing prompts and
continuation behavior. Live validation uses an isolated Factorio 2.0.77 instance;
transport/model latency and factory throughput require separate comparative runs.
