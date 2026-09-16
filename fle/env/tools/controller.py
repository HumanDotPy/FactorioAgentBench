import enum
import re
import time
from timeit import default_timer as timer
from typing import List, Tuple, Dict, Any

# Suppress SyntaxWarning from slpp on Python 3.12+
import warnings

warnings.filterwarnings("ignore", category=SyntaxWarning, module="slpp")

from slpp import ParseError

from fle.env.entities import Direction
from fle.env.lua_manager import LuaScriptManager
from fle.env.namespace import FactorioNamespace
from fle.env.utils.rcon import _lua2python
from fle.commons.profiling import span

COMMAND = "/silent-command"

# Maximum retries for RCON [processing] errors
MAX_PROCESSING_RETRIES = 3
PROCESSING_RETRY_DELAY = 0.1  # seconds

ARGUMENT_TOKEN = re.compile(r"\barg(\d+)\b")

_ENCODING_ERROR = object()


def _lua_quote(text: str) -> str:
    """Quote a Python string as a Lua long-lived literal.

    Lua short strings honour backslash escapes, which slpp cannot decode
    losslessly. Escape every character that Lua or the transport treats
    specially (including newlines) so an argument can never break the command
    or change the number of arguments.
    """
    escaped = []
    for char in text:
        code = ord(char)
        if char == "\\":
            escaped.append("\\\\")
        elif char == '"':
            escaped.append('\\"')
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\r":
            escaped.append("\\r")
        elif char == "\t":
            escaped.append("\\t")
        elif code < 0x20 or code == 0x7F:
            escaped.append("\\%03d" % code)
        else:
            escaped.append(char)
    return '"' + "".join(escaped) + '"'


def _encode_argument(value, path="arg"):
    """Serialize one controller argument into Lua source.

    Returns the Lua literal or ``_ENCODING_ERROR`` when a value has no safe
    representation. It never returns an empty string: silent argument loss
    shifts every later positional argument.
    """
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _lua_quote(value)
    if isinstance(value, Direction):
        return str(value.value)
    if isinstance(value, (list, tuple)):
        parts = []
        for index, item in enumerate(value):
            encoded = _encode_argument(item, f"{path}[{index}]")
            if encoded is _ENCODING_ERROR:
                return _ENCODING_ERROR
            parts.append(encoded)
        return "{" + ",".join(parts) + "}"
    if hasattr(value, "items"):
        parts = []
        for key, item in value.items():
            if isinstance(key, bool):
                return _ENCODING_ERROR
            if isinstance(key, (int, float)):
                key_literal = f"[{key!r}]"
            elif isinstance(key, str):
                key_literal = f"[{_lua_quote(key)}]"
            else:
                return _ENCODING_ERROR
            encoded = _encode_argument(item, f"{path}[{key}]")
            if encoded is _ENCODING_ERROR:
                return _ENCODING_ERROR
            parts.append(f"{key_literal}={encoded}")
        return "{" + ",".join(parts) + "}"
    if hasattr(value, "model_dump"):
        return _encode_argument(value.model_dump(mode="python"), path)
    if isinstance(value, enum.Enum):
        return _encode_argument(value.value, path)
    if isinstance(value, (int, float)):
        return repr(value)
    return _ENCODING_ERROR


class RconProcessingError(Exception):
    """Raised when RCON returns [processing] indicating game engine is busy"""

    pass


class Controller:
    def __init__(
        self,
        lua_script_manager: "LuaScriptManager",
        game_state: "FactorioNamespace",
        *args,
        **kwargs,
    ):
        # assert isinstance(lua_script_manager, LuaScriptManager), f"Not correct: {type(lua_script_manager)}"
        self.connection = lua_script_manager
        self.game_state = game_state
        self.name = self.camel_to_snake(self.__class__.__name__)
        self.lua_script_manager = lua_script_manager
        self.player_index = (
            game_state.agent_index + 1
        )  # +1 because Factorio is 1-indexed

    def clean_response(self, response):
        def is_lua_list(d):
            """Check if dictionary represents a Lua-style list (keys are consecutive numbers from 1)"""
            if not isinstance(d, dict) or not d:
                return False
            keys = set(str(k) for k in d.keys())
            return all(str(i) in keys for i in range(1, len(d) + 1))

        def clean_value(value):
            """Recursively clean a value"""
            if isinstance(value, dict):
                # Handle Lua-style lists
                if is_lua_list(value):
                    # Sort by numeric key and take only the values
                    sorted_items = sorted(value.items(), key=lambda x: int(str(x[0])))
                    return [clean_value(v) for k, v in sorted_items]

                # Handle inventory special case
                if any(isinstance(k, int) for k in value.keys()) and all(
                    isinstance(v, dict) and "name" in v and "count" in v
                    for v in value.values()
                ):
                    cleaned_dict = {}
                    for v in value.values():
                        cleaned_dict[v["name"]] = v["count"]
                    return cleaned_dict

                # Regular dictionary
                return {k: clean_value(v) for k, v in value.items()}

            elif isinstance(value, list):
                return [clean_value(v) for v in value]

            return value

        cleaned_response = {}

        if not hasattr(response, "items"):
            pass

        for key, value in response.items():
            # if key == 'status' and isinstance(value, str):
            # cleaned_response[key] = EntityStatus.from_string(value)
            if key == "direction":
                if isinstance(value, str):
                    cleaned_response[key] = Direction.from_string(value)
                elif isinstance(value, (int, float)):
                    dir_val = int(value)
                    # Factorio 2.0 uses direction values 0,4,8,12 which match our Direction enum
                    # No conversion needed - pass through directly
                    try:
                        cleaned_response[key] = Direction(dir_val)
                    except ValueError:
                        cleaned_response[key] = dir_val
                    continue
            elif not value and key in (
                "warnings",
                "input_connection_points",
                "output_connection_points",
            ):
                cleaned_response[key] = []
            else:
                cleaned_response[key] = clean_value(value)

        return cleaned_response

    def parse_lua_dict(self, d):
        if isinstance(d, (int, str, float)):
            return d

        # Handle lists that were already converted from integer-keyed dicts
        if isinstance(d, list):
            return [self.parse_lua_dict(item) for item in d]

        if isinstance(d, dict) and all(isinstance(k, int) for k in d.keys()):
            # Convert to list if all keys are numeric
            return [self.parse_lua_dict(d[k]) for k in sorted(d.keys())]
        else:
            # Process dictionaries with mixed keys
            new_dict = {}
            last_key = None

            for key in d.keys():
                if isinstance(key, int):
                    if last_key is not None and isinstance(d[key], str):
                        # Concatenate the value to the previous key's value
                        new_dict[last_key] += "-" + d[key]
                else:
                    last_key = key
                    if isinstance(d[key], dict):
                        # Recursively process nested dictionaries
                        new_dict[key] = self.parse_lua_dict(d[key])
                    else:
                        new_dict[key] = d[key]

            return new_dict

    def camel_to_snake(self, camel_str):
        snake_str = ""
        for index, char in enumerate(camel_str):
            if char.isupper():
                if index != 0:
                    snake_str += "_"
                snake_str += char.lower()
            else:
                snake_str += char
        return snake_str

    def _get_command(self, command, parameters=[], measured=True):
        if command in self.script_dict:
            script = f"{COMMAND} " + self.script_dict[command]
            encoded = [self._encode_parameters(parameters)]
            if encoded[0] is None:
                raise TypeError("controller command arguments are not encodable")
            values = encoded[0]

            cursor = 0
            pieces = []
            for match in ARGUMENT_TOKEN.finditer(script):
                pieces.append(script[cursor : match.start()])
                position = int(match.group(1)) - 1
                pieces.append(values[position] if position < len(values) else "nil")
                cursor = match.end()
            pieces.append(script[cursor:])
            script = "".join(pieces)
        else:
            script = command
        return script

    def _encode_parameters(self, parameters) -> list[str] | None:
        encoded = []
        for index, parameter in enumerate(parameters):
            literal = _encode_argument(parameter, f"arg{index + 1}")
            if literal is _ENCODING_ERROR:
                raise TypeError(
                    "cannot serialize controller argument "
                    f"arg{index + 1} ({type(parameter).__name__}); "
                    "pass a string, number, bool, list, dictionary, Position, "
                    "Direction, or entity"
                )
            encoded.append(literal)
        return encoded

    def _check_for_processing_error(self, lua_response: str) -> bool:
        """Check if the RCON response indicates a [processing] error"""
        if lua_response and "[processing]" in lua_response.lower():
            return True
        return False

    def _execute_once(self, *args) -> Tuple[Dict, Any, str]:
        """Execute a single command attempt, returns (result, elapsed, lua_response)"""
        start = time.time()
        parameters = self._encode_parameters(args)
        invocation = self.lua_script_manager.action_invocation(self.name, parameters)
        wrapped = self.lua_script_manager.action_command(self.name, parameters, COMMAND)
        with span("rcon.action." + self.name):
            lua_response = self.connection.rcon_client.send_command(wrapped)

        # Check for [processing] error from RCON layer
        if self._check_for_processing_error(lua_response):
            raise RconProcessingError("Game engine busy (processing), try again")

        with span("lua.decode"):
            parsed, _ = _lua2python(invocation, lua_response, start=start)

        return parsed, lua_response

    def execute(self, *args) -> Tuple[Dict, Any]:
        control = getattr(self.game_state, "_program_runtime", None)
        if control is not None:
            control.pump()
        for attempt in range(MAX_PROCESSING_RETRIES):
            try:
                parsed, lua_response = self._execute_once(*args)

                if parsed is None:
                    raise RuntimeError(f"Invalid action response: {lua_response!r}")

                if not isinstance(parsed, dict):
                    raise RuntimeError(f"Invalid action response: {lua_response!r}")

                if not parsed.get("a") and "b" in parsed:
                    # pcall returned a string diagnostic. The engine may
                    # already have applied (or partially applied) the action,
                    # so never retry it here: retrying duplicates side
                    # effects. Report the diagnostic instead.
                    return parsed["b"], lua_response

                return parsed.get("b", {}), lua_response  # elapsed

            except RconProcessingError:
                if attempt < MAX_PROCESSING_RETRIES - 1:
                    time.sleep(PROCESSING_RETRY_DELAY)
                continue

            except Exception as exc:
                raise RuntimeError(f"RCON action {self.name} failed: {exc}") from exc

        # All retries exhausted
        return (
            "Game engine busy - command could not be executed after multiple retries",
            -1,
        )

    def execute2(self, *args) -> Tuple[Dict, Any]:
        lua_response = ""
        try:
            start = time.time()
            parameters = self._encode_parameters(args)
            invocation = self.lua_script_manager.action_invocation(
                self.name, parameters
            )
            wrapped = self.lua_script_manager.action_command(
                self.name, parameters, COMMAND
            )
            lua_response = self.connection.rcon_client.send_command(wrapped)
            parsed, elapsed = _lua2python(invocation, lua_response, start=start)
            if parsed is None:
                return lua_response, -1
            if not parsed.get("a") and "b" in parsed and isinstance(parsed["b"], str):
                parts = lua_response.split('["b"] = ')
                if len(parts) > 1:
                    value = parts[1]
                    if value.endswith("}"):
                        value = value[:-2]
                    parsed["b"] = value
            if "b" not in parsed:
                return {}, elapsed
        except ParseError as e:
            # If a non-string gets passed back from the Lua script, it will raise a ParseError
            # Split by `["b"] = ` and take the second part, which is the returned value
            try:
                parts = lua_response.split('["b"] = ')
                return parts[1][:-2], -1
            except IndexError:
                return e.args[0], -1
            # return lua_response, -1
        except TypeError:
            return lua_response, -1
        except Exception:
            return lua_response, -1
        return parsed["b"], elapsed

    def send(self, command, *parameters, trace=False) -> List[str]:
        start = timer()
        script = self._get_command(command, parameters=list(parameters), measured=False)
        lua_response = self.connection.send_command(script)
        # print(lua_response)
        return _lua2python(command, lua_response, start=start)
