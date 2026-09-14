REALTIME_PROMPT = """This episode runs continuously at 1x, including while you reason.
factorio_execute_program returns an acceptance receipt and program_id, not an
execution result. Accepted programs run in order on one character executor.
Do useful independent planning and queue bounded follow-up work while execution
continues. Acceptance does not guarantee success: inventory and geometry are
checked when actions run. On failure or cancellation, the completed prefix stays
applied and dependent queued programs are cancelled; observe before replanning.
Use factorio_get_program_status for progress and completed execution receipts.
Use observations when a decision needs fresh state; snapshots report their tick.
Use factorio_cancel_program to stop work at the next safe boundary. Walking and
waits are interruptible; an already-issued atomic interaction finishes first.
When progress depends on new information, call factorio_await_events with the last
event_cursor instead of repeatedly polling or performing unnecessary actions.
Waiting never accelerates the game. A wait inside a submitted Python program
orders that program's subsequent actions; use factorio_await_events to sleep only
the agent. Keep the executor supplied with useful work, not a long speculative
backlog. Use the existing bulk construction tools for repeated placements.
An acceptance receipt never establishes objective completion. Retrieve results
and observe the authoritative terminal state before ending the interaction.
"""
