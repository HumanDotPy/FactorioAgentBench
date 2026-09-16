import pytest

from fle.env.tools.agent.connect_entities.client import ConnectEntities

pytestmark = pytest.mark.no_factorio


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ([{"name": "pipe"}], [{"name": "pipe"}]),
        ({1: {"name": "pipe"}}, [{"name": "pipe"}]),
    ],
)
def test_entity_values_accept_list_and_dictionary_payloads(payload, expected):
    assert list(ConnectEntities._entity_values(payload)) == expected


@pytest.mark.parametrize(
    ("target", "source", "expected"),
    [
        (["existing"], ["new"], ["existing", "new"]),
        ({1: "existing"}, {1: "new"}, {1: "existing", 2: "new"}),
    ],
)
def test_appending_entity_payloads_preserves_target_shape(target, source, expected):
    ConnectEntities._append_entity_values(target, source)
    assert target == expected
