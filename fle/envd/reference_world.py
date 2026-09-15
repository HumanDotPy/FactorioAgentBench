"""Lease-owned creative Factorio processes, allocated lazily through Docker.

Native Lua runs only in the disposable process. The parent worker is never
passed to the runner; blueprint strings are its only factory transfer format.
"""

from __future__ import annotations

import json
import hashlib
import shutil
from pathlib import Path
import subprocess
import threading
import time
import uuid

from fle.envd.errors import CapacityExhausted

HELPERS = Path(__file__).with_suffix(".lua").read_text(encoding="utf-8")


class ReferenceWorld:
    def __init__(self, root: Path, snapshot: dict | None = None):
        self.world_id = uuid.uuid4().hex
        self.root = root / self.world_id
        self.project = f"fle-blueprint-{self.world_id}"
        self.client = None
        self.lock = threading.RLock()
        self.sequence = 0
        self.closed = False
        self.snapshot = snapshot
        self.saved_sequence = None
        self.saved_snapshot = None

    def _compose(self, *args):
        return subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                self.project,
                "-f",
                str(self.root / "compose.yaml"),
                *args,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout

    def start(self):
        from factorio_rcon import RCONClient
        from fle.cluster.run_envs import ComposeGenerator, FACTORIO_VERSION
        import yaml

        self.root.mkdir(parents=True, exist_ok=True)
        generator = ComposeGenerator(state_dir=self.root / "state", work_dir=self.root)
        service = next(iter(generator.services_dict(1).values()))
        # Docker allocates a free host port, avoiding races with active workers.
        service["ports"] = ["127.0.0.1::27015/tcp"]
        service["restart"] = "no"
        service["labels"]["fle.reference-world"] = "true"
        saves = self.root / "state" / "saves"
        saves.mkdir(parents=True, exist_ok=True)
        service["volumes"].append(
            {
                "type": "bind",
                "source": str(saves.resolve()),
                "target": "/opt/factorio/saves",
            }
        )
        if self.snapshot:
            source = Path(self.snapshot["path"]).resolve()
            if not source.is_relative_to(self.root.parent.resolve()):
                raise ValueError("Reference checkpoint is outside the reference pool")
            if (
                hashlib.sha256(source.read_bytes()).hexdigest()
                != self.snapshot["sha256"]
            ):
                raise ValueError("Reference checkpoint digest mismatch")
            shutil.copy2(source, saves / "resume.zip")
            service["command"] = service["command"].replace(
                "--start-server-load-scenario open_world",
                "--start-server /opt/factorio/saves/resume.zip",
            )
        (self.root / "compose.yaml").write_text(
            yaml.safe_dump({"services": {"reference": service}})
        )
        try:
            self._compose("up", "-d")
            endpoint = self._compose("port", "reference", "27015").strip()
            port = int(endpoint.rsplit(":", 1)[1])
            self.port = port
            deadline = time.monotonic() + 60
            while True:
                try:
                    self.client = RCONClient("127.0.0.1", port, "factorio", timeout=10)
                    version = self.client.send_command(
                        "/sc rcon.print(script.active_mods.base)"
                    ).strip()
                    if version != FACTORIO_VERSION:
                        raise ValueError(
                            f"Reference version {version} != {FACTORIO_VERSION}"
                        )
                    break
                except Exception:
                    if self.client:
                        self.client.close()
                        self.client = None
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.25)
            if self.snapshot:
                self.sequence = int(self.snapshot["sequence"])
                return self.status()
            initialized = self._call(
                """
                game.tick_paused=true; game.ticks_to_run=0
                local s=game.create_surface("reference", {autoplace_settings={
                    entity={treat_missing_as_default=false},
                    tile={treat_missing_as_default=false},
                    decorative={treat_missing_as_default=false}}})
                s.request_to_generate_chunks({0,0}, 2); s.force_generate_chunk_requests()
                s.always_day=true
                local tiles={}
                for x=-64,63 do for y=-64,63 do
                    tiles[#tiles+1]={name="lab-dark-1",position={x,y}}
                end end
                s.set_tiles(tiles)
                game.forces.player.research_all_technologies()
                game.forces.player.chart(s,{{-64,-64},{64,64}})
                return {version=script.active_mods.base,tick=game.tick}
            """,
                helpers=False,
            )
            if initialized.get("error"):
                raise RuntimeError(initialized["error"])
        except Exception:
            self.close()
            raise
        return self.status()

    def _call(self, code: str, *, helpers=True):
        if self.closed or self.client is None:
            raise ValueError("Reference world is closed")
        # A quoted string preserves comments/newlines and cannot escape /sc.
        body = (HELPERS + "\n" if helpers else "") + code
        command = (
            "/sc local f,e=load(" + json.dumps(body) + "); "
            "if not f then rcon.print(helpers.table_to_json({error=e})) else "
            "local ok,r=pcall(f); if not ok then rcon.print(helpers.table_to_json({error=tostring(r)})) "
            "else rcon.print(helpers.table_to_json({result=r or {},tick=game.tick})) end end"
        )
        try:
            raw = self.client.send_command(command)
        except Exception:
            # A runaway native script must not keep burning a CPU after RCON
            # times out. Its disposable process is quarantined immediately.
            self.close()
            raise
        try:
            result = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Reference engine returned invalid JSON: {str(raw)[:1000]}"
            ) from exc
        return result

    def status(self):
        return {
            "world_id": self.world_id,
            "kind": "creative-reference",
            "sequence": self.sequence,
            "closed": self.closed,
            "transfer": "blueprint-exchange-only",
        }

    def execute(self, code: str, *, internal: bool = False):
        if (
            not isinstance(code, str)
            or not code.strip()
            or len(code.encode()) > (2 * 1024 * 1024 if internal else 32768)
        ):
            raise ValueError("Reference Lua code must contain 1–32768 bytes")
        try:
            result = self._call(code)
        finally:
            self.sequence += 1
            if not self.closed:
                self._call(
                    "game.tick_paused=true; game.ticks_to_run=0; return {}",
                    helpers=False,
                )
        return {**self.status(), **result}

    def checkpoint(self):
        if self.saved_sequence == self.sequence:
            return self.saved_snapshot
        filename = "checkpoint-" + uuid.uuid4().hex
        result = self._call(
            "game.tick_paused=true; game.ticks_to_run=0; game.server_save("
            + json.dumps(filename)
            + "); return {}",
            helpers=False,
        )
        if result.get("error"):
            raise RuntimeError(result["error"])
        source = self.root / "state" / "saves" / (filename + ".zip")
        deadline = time.monotonic() + 30
        while not source.exists():
            if time.monotonic() > deadline:
                raise TimeoutError("Reference native save was not written")
            time.sleep(0.05)
        target = self.root / "checkpoints" / source.name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(source, target)
        self.saved_snapshot = {
            "path": str(target.resolve()),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "sequence": self.sequence,
        }
        self.saved_sequence = self.sequence
        return self.saved_snapshot

    def run(self, ticks: int, speed: float = 10):
        if (
            isinstance(ticks, bool)
            or not isinstance(ticks, int)
            or not 1 <= ticks <= 216000
        ):
            raise ValueError("ticks must be an integer from 1 to 216000 (one hour)")
        if not isinstance(speed, (int, float)) or not 0 < speed <= 1000:
            raise ValueError("speed must be greater than zero and at most 1000")
        self.sequence += 1
        before = self._call(
            f"game.tick_paused=true; game.speed={speed}; game.ticks_to_run={ticks}; return game.tick",
            helpers=False,
        )
        if before.get("error"):
            return before
        start = before["result"]
        deadline = time.monotonic() + 120
        try:
            while True:
                state = self._call(
                    "return {remaining=game.ticks_to_run}", helpers=False
                )
                if state.get("error"):
                    return state
                if state["result"]["remaining"] == 0:
                    return {
                        **self.status(),
                        "start_tick": start,
                        "end_tick": state["tick"],
                        "advanced_ticks": state["tick"] - start,
                    }
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "Reference simulation exceeded 120 seconds; remaining ticks cancelled"
                    )
                time.sleep(0.05)
        finally:
            if not self.closed:
                self._call(
                    "game.tick_paused=true; game.ticks_to_run=0; return {}",
                    helpers=False,
                )

    def close(self):
        if self.closed:
            return
        if (self.root / "compose.yaml").exists():
            self._compose("down", "--remove-orphans")
        if self.client:
            self.client.close()
        self.closed = True


class ReferenceWorldPool:
    def __init__(self, root: Path, capacity: int):
        if capacity < 1:
            raise ValueError("Reference capacity must be positive")
        self.root = root.resolve()
        self.capacity = capacity
        self.worlds = {}
        self.lock = threading.RLock()

    def create(self, owner: str, snapshot: dict | None = None):
        with self.lock:
            if owner in self.worlds:
                return self.worlds[owner].status()
            if len(self.worlds) >= self.capacity:
                raise CapacityExhausted("No reference world capacity available")
            world = ReferenceWorld(self.root, snapshot)
            self.worlds[owner] = world
        try:
            with world.lock:
                return world.start()
        except Exception:
            with self.lock:
                self.worlds.pop(owner, None)
            raise

    def get(self, owner: str):
        with self.lock:
            world = self.worlds.get(owner)
        if world is None:
            raise ValueError("Create a reference world first")
        return world

    def release(self, owner: str):
        with self.lock:
            world = self.worlds.get(owner)
        if world:
            with world.lock:
                world.close()
            with self.lock:
                self.worlds.pop(owner, None)
        return {"released": world is not None}

    def checkpoint(self, owner: str):
        with self.lock:
            world = self.worlds.get(owner)
        if world is None:
            return None
        with world.lock:
            return world.checkpoint()
