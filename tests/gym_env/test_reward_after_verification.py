from types import SimpleNamespace

import pytest

from fle.agents import TaskResponse
from fle.commons.models.research_state import ResearchState
from fle.env.entities import Inventory
from fle.env.gym_env.action import Action
from fle.env.gym_env.environment import FactorioGymEnv


class FakeNamespace:
    def __init__(self, instance):
        self.instance = instance
        self._last_score = None
        self.persistent_vars = {}
        self.player_location = SimpleNamespace(x=0.0, y=0.0)

    def _get_production_stats(self):
        return {
            "input": {},
            "output": {"iron-plate": self.instance.production},
            "crafted": [],
            "harvested": {},
        }

    def score(self):
        return self.instance.production, self.instance.production

    def _refresh_score(self):
        self._last_score = self.score()
        return self._last_score

    def _save_entity_state(self, compress=True, encode=True):
        return ""

    def _save_research_state(self):
        return ResearchState(
            technologies={},
            current_research=None,
            research_progress=0.0,
            research_queue=[],
            progress={},
        )

    def get_entities(self):
        return []

    def inspect_inventory(self):
        return Inventory()

    def get_messages(self):
        return []

    def get_functions(self):
        return []


class FakeInstance:
    def __init__(self, production=10, num_agents=1):
        self.production = production
        self.num_agents = num_agents
        self.namespaces = [FakeNamespace(self) for _ in range(num_agents)]

    @property
    def first_namespace(self):
        return self.namespaces[0]

    def get_speed(self):
        return 1.0

    def set_speed_and_unpause(self, speed):
        return None

    def get_elapsed_ticks(self):
        return 0

    def pause(self):
        return None

    def eval(self, code, agent_idx=0, timeout=60):
        namespace = self.namespaces[agent_idx]
        namespace._last_score = (self.production, self.production)
        return self.production, 0.0, "ok"


class AdvancingTask:
    trajectory_length = 2
    goal_description = "test goal"
    task_key = "test-task"
    agent_instructions = None

    def __init__(self, advance):
        self.advance = advance

    def get_agent_instructions(self, agent_idx):
        return None

    def verify(self, score, instance, step_statistics):
        self.advance(instance)
        return TaskResponse(success=False, meta={})

    def enhance_response_with_task_output(self, response, task_response):
        return response


def _env(instance, task):
    return FactorioGymEnv(
        instance, task=task, pause_after_action=False, enable_vision=False
    )


@pytest.mark.no_factorio
def test_reward_reflects_production_after_verification_without_eval():
    instance = FakeInstance(production=10)
    task = AdvancingTask(lambda inst: setattr(inst, "production", inst.production + 50))
    env = _env(instance, task)

    _, reward, _, _, info = env.step(Action(agent_idx=0, code="pass"))

    assert info["production_score"] == 60
    assert info["automated_production_score"] == 60
    assert reward == 50.0


@pytest.mark.no_factorio
def test_reward_reflects_post_verification_score_for_non_acting_namespace():
    instance = FakeInstance(production=10, num_agents=2)

    def advance(inst):
        inst.production = 60
        inst.namespaces[0]._last_score = (60, 60)

    task = AdvancingTask(advance)
    env = _env(instance, task)

    _, reward, _, _, info = env.step(Action(agent_idx=1, code="pass"))

    assert info["production_score"] == 60
    assert reward == 50.0
