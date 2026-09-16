from pydantic import BaseModel
from fle.commons.models.game_state import GameState


def test_game_state_research(instance):
    class DummyObject(BaseModel):
        game_state: GameState = None

    zero_state = GameState.from_instance(instance)
    # this tests for validation errors in the original zero states
    new_object = DummyObject(game_state=zero_state)  # noqa
