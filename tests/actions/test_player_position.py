from types import SimpleNamespace

import pytest

from fle.env.entities import Position
from fle.env.instance import FactorioInstance
from fle.env.namespace import FactorioNamespace

pytestmark = pytest.mark.no_factorio


def test_namespace_player_position_reads_and_writes_the_player_location():
    namespace = FactorioNamespace(SimpleNamespace(tcp_port=25575), 0)
    assert isinstance(namespace.player_position, Position)

    namespace.player_location = Position(x=3.5, y=-2.0)
    assert (namespace.player_position.x, namespace.player_position.y) == (3.5, -2.0)

    namespace.player_position = Position(x=1.25, y=4.0)
    assert (namespace.player_location.x, namespace.player_location.y) == (1.25, 4.0)


def test_instance_player_position_forwards_to_the_first_namespace():
    namespace = FactorioNamespace(SimpleNamespace(tcp_port=25575), 0)
    namespace.player_location = Position(x=7.0, y=8.5)
    instance = FactorioInstance.__new__(FactorioInstance)
    instance.namespaces = [namespace]

    assert (instance.player_position.x, instance.player_position.y) == (7.0, 8.5)


def test_player_position_is_readable_inside_a_program():
    namespace = FactorioNamespace(SimpleNamespace(tcp_port=25575), 0)
    namespace.player_location = Position(x=9.5, y=1.5)
    namespace.capture_whole_output = True
    namespace.score = lambda: (0, 0)

    _, _, output = namespace.eval_with_timeout("player_position")

    assert "Position(x=9.5, y=1.5)" in output
