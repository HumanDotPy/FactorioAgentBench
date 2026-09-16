import contextlib
import json
import math
from time import sleep
from typing import Iterable

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.instance import NONE
from fle.env.lua_manager import LuaScriptManager
from fle.env.tools import Tool
from fle.env.tools.admin.get_path.client import GetPath
from fle.env.tools.admin.request_path.client import RequestPath


class MoveTo(Tool):
    """Walk the character over live Factorio ticks."""

    UNSTICK_ATTEMPTS = 2
    WALKABLE_FALLBACK_RADIUS = 8
    WALKABLE_FALLBACK_LIMIT = 8
    WALKABLE_ENTITY_TYPES = frozenset(
        {
            "transport-belt",
            "underground-belt",
            "splitter",
            "lane-splitter",
            "loader",
            "linked-belt",
        }
    )
    WALKABLE_ENTITY_PROTOTYPES = frozenset(
        {
            "transport-belt",
            "fast-transport-belt",
            "express-transport-belt",
            "underground-belt",
            "fast-underground-belt",
            "express-underground-belt",
            "splitter",
            "fast-splitter",
            "express-splitter",
        }
    )

    def __init__(self, connection: LuaScriptManager, game_state):
        super().__init__(connection, game_state)
        self.request_path = RequestPath(connection, game_state)
        self.get_path = GetPath(connection, game_state)
        self.last_receipt: dict | None = None

    def refresh_player_location(self) -> Position:
        current = self.game_state.player_location
        try:
            response, _ = self.execute(self.player_index, "__position__", NONE, NONE, 0)
        except Exception:
            return current
        if isinstance(response, dict):
            x = response.get("x")
            y = response.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                current = Position(x=float(x), y=float(y))
                self.game_state.player_location = current
        return current

    def __call__(
        self,
        position: Position,
        laying: Prototype = None,
        leading: Prototype = None,
        stop_distance: float = 0,
        mode: str = "walk",
        waypoints: Iterable[Position] | None = None,
        interrupt_on: Iterable[str] | None = None,
        timeout_ticks: int = 60 * 60 * 10,
    ) -> Position:
        if mode.lower() != "walk":
            raise ValueError("move_to currently supports mode='walk' only")
        if stop_distance < 0:
            raise ValueError("stop_distance must be non-negative")
        route = list(waypoints or []) + [position]
        final = self.game_state.player_location
        receipts = []
        for index, target in enumerate(route):
            final, receipt = self._move_one(
                target,
                laying=laying,
                leading=leading,
                stop_distance=stop_distance if index == len(route) - 1 else 0,
                interrupt_on={str(value).lower() for value in (interrupt_on or ())},
                timeout_ticks=timeout_ticks,
            )
            receipts.append(receipt)
            if receipt["status"] != "completed":
                break
        self.last_receipt = {
            "status": receipts[-1]["status"] if receipts else "completed",
            "position": {"x": final.x, "y": final.y},
            "ticks_elapsed": sum(item["ticks_elapsed"] for item in receipts),
            "stop_reason": receipts[-1]["stop_reason"] if receipts else "arrived",
            "requested": receipts[-1].get("requested") if receipts else None,
            "distance_to_requested": (
                receipts[-1].get("distance_to_requested") if receipts else 0.0
            ),
            "fallback": receipts[-1].get("fallback") if receipts else None,
            "segments": receipts,
        }
        return final

    def _move_one(
        self, position, *, laying, leading, stop_distance, interrupt_on, timeout_ticks
    ):
        if not isinstance(position, Position):
            position = getattr(position, "position", None)
        if not isinstance(position, Position):
            raise ValueError("move_to target must be a Position or Entity")
        if timeout_ticks <= 0:
            raise ValueError("timeout_ticks must be positive")

        requested = position
        current = self.refresh_player_location()
        distance = math.hypot(requested.x - current.x, requested.y - current.y)
        if distance <= stop_distance:
            return current, self._move_receipt(
                "completed", 0, "already_in_range", requested, current
            )
        if (math.floor(current.x), math.floor(current.y)) == (
            math.floor(requested.x),
            math.floor(requested.y),
        ):
            return current, self._move_receipt(
                "completed", 0, "already_in_range", requested, current
            )

        goal = requested
        fallback = None
        path_handle = None
        unstick = None
        last_error = None
        for attempt in range(self.UNSTICK_ATTEMPTS + 1):
            try:
                path_handle = self._request_path_handle(goal, stop_distance)
                break
            except Exception as exc:
                last_error = exc
                if not self._start_failure(exc):
                    raise
                if self._walkable_start_failure(exc):
                    break
                if attempt == self.UNSTICK_ATTEMPTS:
                    break
                unstick = self.self_unstick(goal)
                if not unstick or not unstick.get("moved"):
                    break

        if path_handle is None:
            if self._genuinely_blocked(unstick):
                raise self._blocked_start_error(requested, unstick) from last_error
            try:
                path_handle = self._request_path_handle(goal, stop_distance, True)
            except Exception as exc:
                last_error = exc
            if path_handle is None:
                goal, path_handle, fallback = self._walkable_fallback(requested)
                if path_handle is None:
                    raise self._no_walkable_error(requested) from last_error

        start_tick = self._game_tick()
        trailing_name, trailing_mode = NONE, NONE
        if laying is not None:
            trailing_name, trailing_mode = laying.value[0], 1
        elif leading is not None:
            trailing_name, trailing_mode = leading.value[0], 0
        response, _ = self.execute(
            self.player_index, path_handle, trailing_name, trailing_mode, 0
        )
        if isinstance(response, str) or response in ({}, 0, None):
            raise Exception(f"Cannot move to ({goal.x}, {goal.y}): {response}")

        if self.game_state.instance.fast:
            final = Position(x=response["x"], y=response["y"])
            self.game_state.player_location = final
            return final, self._move_receipt(
                "completed",
                max(self._game_tick() - start_tick, 0),
                "arrived",
                requested,
                final,
                fallback,
            )

        deadline = start_tick + timeout_ticks
        status = {"active": True}
        while status.get("active"):
            sleep(0.1)
            status, _ = self.execute(self.player_index, "__status__", NONE, NONE, 0)
            control = getattr(self.game_state, "_program_runtime", None)
            if control is not None and control.cancelled():
                status, _ = self.execute(self.player_index, "__cancel__", NONE, NONE, 0)
                self.game_state.player_location = Position(
                    x=float(status["x"]), y=float(status["y"])
                )
                control.boundary()
            if not isinstance(status, dict):
                raise Exception(f"Cannot read walking status: {status}")
            tick = status.get("tick")
            if tick is None:
                tick = self._game_tick()
            if tick >= deadline:
                status, _ = self.execute(self.player_index, "__cancel__", NONE, NONE, 0)
                status["stop_reason"] = "timeout"
            event = str(status.get("event") or "").lower()
            if event and event in interrupt_on:
                status, _ = self.execute(self.player_index, "__cancel__", NONE, NONE, 0)
                status["stop_reason"] = event

        final = Position(x=float(status["x"]), y=float(status["y"]))
        self.game_state.player_location = final
        reason = str(status.get("stop_reason") or "arrived")
        if reason == "blocked_no_progress":
            raise RuntimeError(
                f"Movement blocked near ({final.x:.2f}, {final.y:.2f}); "
                f"could not escape toward ({requested.x:.2f}, {requested.y:.2f}). "
                "The requested destination may be occupied; use a positive "
                "stop_distance or call the intended interaction action directly."
            )
        return final, self._move_receipt(
            "completed" if reason in {"arrived", "already_in_range"} else "partial",
            max(self._game_tick() - start_tick, 0),
            reason,
            requested,
            final,
            fallback,
        )

    @staticmethod
    def _start_failure(exc: Exception) -> bool:
        text = str(exc)
        return "not_found" in text or "empty_path" in text

    @staticmethod
    def _move_receipt(
        status: str,
        ticks_elapsed: int,
        stop_reason: str,
        requested: Position,
        final: Position,
        fallback: dict | None = None,
    ) -> dict:
        return {
            "status": status,
            "ticks_elapsed": ticks_elapsed,
            "stop_reason": stop_reason,
            "requested": {"x": requested.x, "y": requested.y},
            "distance_to_requested": round(
                math.hypot(final.x - requested.x, final.y - requested.y), 3
            ),
            "fallback": fallback,
        }

    @staticmethod
    def _failure_diagnostics(exc: Exception) -> dict | None:
        text = str(exc)
        start = text.find("{")
        if start < 0:
            return None
        try:
            payload = json.loads(text[start:])
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        diagnostics = payload.get("diagnostics")
        return diagnostics if isinstance(diagnostics, dict) else None

    @classmethod
    def _diagnostic_entities(cls, value) -> list:
        if isinstance(value, dict):
            return [value[key] for key in sorted(value, key=int)]
        if isinstance(value, list):
            return value
        return []

    @classmethod
    def _is_walkable_entity(cls, entity) -> bool:
        if not isinstance(entity, dict):
            return False
        if entity.get("type") in cls.WALKABLE_ENTITY_TYPES:
            return True
        prototype = entity.get("prototype") or entity.get("name")
        return prototype in cls.WALKABLE_ENTITY_PROTOTYPES

    def _walkable_start_failure(self, exc: Exception) -> bool:
        diagnostics = self._failure_diagnostics(exc)
        if not diagnostics:
            return False
        start = diagnostics.get("start")
        if not isinstance(start, dict):
            return False
        entities = self._diagnostic_entities(start.get("overlapping_entities"))
        if not entities:
            return False
        return all(self._is_walkable_entity(entity) for entity in entities)

    @staticmethod
    def _genuinely_blocked(unstick: dict | None) -> bool:
        if not isinstance(unstick, dict):
            return False
        return unstick.get("reason") not in (None, "start_free")

    def _walkable_candidates(self, requested: Position) -> list[Position]:
        response = None
        with contextlib.suppress(Exception):
            response, _ = self.execute(
                self.player_index,
                "__nearest_walkable__",
                float(requested.x),
                float(requested.y),
                float(self.WALKABLE_FALLBACK_RADIUS),
            )
        if not isinstance(response, dict) or response.get("status") != "ok":
            return []
        raw = self._diagnostic_entities(response.get("candidates"))
        candidates = []
        for item in raw[: self.WALKABLE_FALLBACK_LIMIT]:
            if not isinstance(item, dict):
                continue
            try:
                candidates.append(Position(x=float(item["x"]), y=float(item["y"])))
            except (KeyError, TypeError, ValueError):
                continue
        return candidates

    def _walkable_fallback(self, requested: Position):
        for candidate in self._walkable_candidates(requested):
            with contextlib.suppress(Exception):
                path_handle = self._request_path_handle(candidate, 0)
                fallback = {
                    "kind": "nearest_walkable",
                    "position": {"x": candidate.x, "y": candidate.y},
                    "distance": round(
                        math.hypot(
                            candidate.x - requested.x, candidate.y - requested.y
                        ),
                        3,
                    ),
                    "radius": self.WALKABLE_FALLBACK_RADIUS,
                }
                return candidate, path_handle, fallback
        return requested, None, None

    def _no_walkable_error(self, requested: Position) -> RuntimeError:
        return RuntimeError(
            f"Could not reach ({requested.x:.2f}, {requested.y:.2f}): no reachable "
            f"walkable tile within {self.WALKABLE_FALLBACK_RADIUS} tiles of the "
            "requested target; choose another destination or a stop_distance that "
            "permits an approach"
        )

    def _fetch_path(
        self,
        current: Position,
        goal: Position,
        stop_distance: float,
        allow_own_entities: bool,
        resolution: int,
    ) -> int:
        path_handle = self.request_path(
            start=Position(x=current.x, y=current.y),
            finish=goal,
            allow_paths_through_own_entities=allow_own_entities,
            resolution=resolution,
            radius=max(stop_distance, 0.15),
            entity_size=None,
        )
        waypoints = self.get_path(path_handle)
        if not waypoints:
            raise RuntimeError('{"status": "empty_path"}')
        return path_handle

    def _request_path_handle(
        self, goal: Position, stop_distance: float, allow_own_entities: bool = False
    ) -> int:
        current = self.game_state.player_location
        last_error = None
        for resolution in (0, -1):
            try:
                return self._fetch_path(
                    current, goal, stop_distance, allow_own_entities, resolution
                )
            except Exception as exc:
                last_error = exc
                if resolution == -1 or not self._start_failure(exc):
                    break
        raise last_error

    def self_unstick(
        self, position: Position | None = None, attempts: int | None = None
    ) -> dict | None:
        if not isinstance(position, Position):
            position = getattr(self.game_state, "player_location", None)
        reference = position or Position(x=0.0, y=0.0)
        request = self.UNSTICK_ATTEMPTS if attempts is None else attempts
        try:
            info, _ = self.execute(
                self.player_index, "__unstick__", NONE, NONE, request
            )
        except Exception:
            return None
        if not isinstance(info, dict) or not isinstance(info.get("position"), dict):
            return None
        moved = info["position"]
        self.game_state.player_location = Position(
            x=float(moved.get("x", reference.x)), y=float(moved.get("y", reference.y))
        )
        return info

    def _blocked_start_error(
        self, goal: Position, unstick: dict | None
    ) -> RuntimeError:
        current = self.game_state.player_location
        reason = (unstick or {}).get("reason") or "unknown"
        steps = (unstick or {}).get("steps") or 0
        if reason == "start_free":
            if (unstick or {}).get("moved"):
                detail = (
                    f"character start was freed after {steps} self-unstick step(s); "
                    "the requested goal may be unreachable"
                )
            else:
                detail = (
                    "the character start tile was already free; "
                    "the requested goal may be unreachable"
                )
        else:
            detail = f"character start still blocked; blocking reason: {reason}"
        return RuntimeError(
            f"Could not get path from ({current.x:.2f}, {current.y:.2f}) to "
            f"({goal.x:.2f}, {goal.y:.2f}): {detail}"
        )

    def _game_tick(self) -> int:
        raw = self.connection.rcon_client.send_command("/sc rcon.print(game.tick)")
        return int(raw or 0)
