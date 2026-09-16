import pytest

from fle.env.entities import Position

pytestmark = pytest.mark.no_factorio


def test_positions_a_tile_apart_are_not_equal():
    assert Position(x=1.0, y=0.0) != Position(x=2.0, y=0.0)
    assert Position(x=0.0, y=0.0) != Position(x=0.0, y=1.0)


def test_exact_positions_are_equal():
    assert Position(x=0.5, y=-1.5) == Position(x=0.5, y=-1.5)


def test_is_close_keeps_its_own_tolerance():
    assert Position(x=0.0, y=0.0).is_close(Position(x=0.4, y=0.0))
