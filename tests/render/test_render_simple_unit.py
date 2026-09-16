import asyncio
import math
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from fle.commons.models.rendered_image import RenderedImage
from fle.env import BoundingBox, Position
from fle.env.protocols._mcp import resources
from fle.env.tools.admin.render_simple.client import RenderSimple

pytestmark = pytest.mark.no_factorio


class _Renderer:
    config = SimpleNamespace(style={"cell_size": 10})

    def render_entities(self, entities, **kwargs):
        return Image.new("RGBA", (4, 4))


def _make_tool():
    tool = RenderSimple.__new__(RenderSimple)
    tool.name = "render_simple"
    tool.player_index = 1
    tool.game_state = SimpleNamespace(player_location=Position(0, 0))
    tool.execute = Mock(return_value=({}, 0))
    tool.get_entities = Mock(return_value=[])
    tool.renderer = _Renderer()
    return tool


def _box(left, top, right, bottom):
    return BoundingBox(
        left_top=Position(left, top),
        right_bottom=Position(right, bottom),
        left_bottom=Position(left, bottom),
        right_top=Position(right, top),
    )


def test_bounding_box_scopes_entity_query_to_the_box():
    tool = _make_tool()
    box = _box(100, 200, 110, 206)
    tool(bounding_box=box)
    assert tool.get_entities.call_args.kwargs["position"] == box.center
    assert tool.get_entities.call_args.kwargs["radius"] == pytest.approx(
        math.hypot(5, 3)
    )


def test_position_query_stays_player_centered():
    tool = _make_tool()
    tool()
    assert tool.get_entities.call_args.kwargs["position"] == Position(0, 0)


def test_render_resource_fallback_uses_supported_arguments(monkeypatch):
    seen = {}

    class _Namespace:
        def _render(self, **kwargs):
            raise RuntimeError("full renderer unavailable")

        def _render_simple(self, **kwargs):
            seen.update(kwargs)
            return RenderedImage(Image.new("RGBA", (2, 2)))

    monkeypatch.setattr(
        resources.state, "active_server", SimpleNamespace(namespace=_Namespace())
    )
    content = asyncio.run(resources.render_at.fn("3", "-2", 12))
    assert seen == {"position": Position(3.0, -2.0)}
    assert content.type == "image"
    assert content.mimeType == "image/png"
