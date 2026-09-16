from types import SimpleNamespace

from fle.env.gym_env.system_prompt_formatter import SystemPromptFormatter


def test_format_prefers_the_current_goal_field():
    formatter = SystemPromptFormatter()
    task = SimpleNamespace(goal="Produce 10 gears", goal_description="Legacy goal")

    text = formatter.format(task, "follow the profile")

    assert "## Task\nProduce 10 gears" in text
    assert "Legacy goal" not in text
    assert "## Instructions\nfollow the profile" in text


def test_format_falls_back_to_goal_description_and_handles_no_task():
    formatter = SystemPromptFormatter()
    legacy = SimpleNamespace(goal_description="Legacy goal")

    assert "Legacy goal" in formatter.format(legacy)
    assert formatter.format(None) == ""
