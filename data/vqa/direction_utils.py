"""Direction utilities for VQA tasks."""

import enum
from typing import Union, Optional

from data.vqa.blueprint_transforms import DirectionSystem


class Direction(enum.Enum):
    """Direction enum matching Factorio's 2.0 direction system."""

    UP = NORTH = 0
    RIGHT = EAST = 4
    DOWN = SOUTH = 8
    LEFT = WEST = 12

    @classmethod
    def opposite(cls, direction: "Direction") -> "Direction":
        """Get the opposite direction."""
        return cls((direction.value + 8) % 16)

    @classmethod
    def next_clockwise(cls, direction: "Direction") -> "Direction":
        """Get the next direction clockwise."""
        return cls((direction.value + 4) % 16)

    @classmethod
    def next_counterclockwise(cls, direction: "Direction") -> "Direction":
        """Get the next direction counterclockwise."""
        return cls((direction.value - 4) % 16)

    @classmethod
    def to_factorio_direction(cls, direction: "Direction") -> int:
        """Convert to Factorio's cardinal index (0-3)."""
        return direction.value // 4

    @classmethod
    def from_factorio_direction(cls, direction: int) -> "Direction":
        """Convert from Factorio's cardinal index (0-3) to enum."""
        return cls(direction * 4)

    @classmethod
    def from_value(
        cls,
        v: Union[int, float, str],
        direction_system: DirectionSystem = DirectionSystem.NEW_SYSTEM,
    ) -> Optional["Direction"]:
        """Convert a value (int or string) to Direction enum."""
        if isinstance(v, (int, float)):
            value = int(round(v))
            if direction_system == DirectionSystem.OLD_SYSTEM:
                legacy = {0: cls.NORTH, 2: cls.EAST, 4: cls.SOUTH, 6: cls.WEST}
                if value in legacy:
                    return legacy[value]
                if 0 <= value <= 3:
                    return cls.from_factorio_direction(value)
                return None
            return cls(((value % 16 + 2) // 4 * 4) % 16)

        elif isinstance(v, str):
            # Handle string names, including aliases such as UP/NORTH
            value_upper = v.upper()
            if value_upper in cls.__members__:
                return cls.__members__[value_upper]
        return None

    def to_compass_string(self) -> str:
        """Get lowercase compass direction string."""
        if self == Direction.NORTH:
            return "north"
        elif self == Direction.EAST:
            return "east"
        elif self == Direction.SOUTH:
            return "south"
        elif self == Direction.WEST:
            return "west"

    def to_relative_string(self) -> str:
        """Get relative direction string."""
        if self == Direction.UP:
            return "up"
        elif self == Direction.RIGHT:
            return "right"
        elif self == Direction.DOWN:
            return "down"
        elif self == Direction.LEFT:
            return "left"


def convert_numeric_direction(
    direction_value: Union[int, float, str], direction_system
) -> str:
    """
    Convert numeric direction to compass string.

    Args:
        direction_value: Numeric direction (0/4/8/12 in 2.0, or legacy 0/2/4/6
            when ``direction_system`` is OLD_SYSTEM) or string

    Returns:
        Compass direction string (north/east/south/west)
    """
    if isinstance(direction_value, (int, float)):
        direction = Direction.from_value(int(direction_value), direction_system)
        if direction:
            return direction.to_compass_string()
    return str(direction_value)


def format_direction_in_text(text: str) -> str:
    """
    Replace numeric directions in text with compass directions.

    Args:
        text: Text containing direction references

    Returns:
        Text with compass directions
    """
    import re

    # Pattern to match direction references
    patterns = [
        (r"\bdirection\s*=?\s*(\d{1,2})", "direction_equals"),
        (r"\bfacing\s+(\d{1,2})", "facing"),
        (r"\bdirection\s+(\d{1,2})", "direction"),
    ]

    result = text
    for pattern, pattern_type in patterns:
        matches = list(re.finditer(pattern, result, re.IGNORECASE))

        # Process matches in reverse to preserve positions
        for match in reversed(matches):
            dir_value = int(match.group(1))
            direction = Direction.from_value(dir_value)

            if direction:
                compass = direction.to_compass_string()
                if pattern_type == "direction_equals":
                    replacement = f"facing {compass}"
                elif pattern_type == "facing":
                    replacement = f"facing {compass}"
                else:
                    replacement = f"facing {compass}"

                result = result[: match.start()] + replacement + result[match.end() :]

    return result
