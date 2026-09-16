from PIL import Image
import pytest

from fle.env.tools.admin.render.client import Render

pytestmark = pytest.mark.no_factorio


class _Renderer:
    def __init__(self, size, offset_x, offset_y):
        self._size = size
        self.offset_x = offset_x
        self.offset_y = offset_y

    def get_size(self):
        return dict(self._size)

    def render(self, width, height, image_resolver):
        return Image.new("RGBA", (width, height))


def _render(monkeypatch, size, offset_x, offset_y, **kwargs):
    tool = Render.__new__(Render)
    tool.image_resolver = object()
    renderer = _Renderer(size, offset_x, offset_y)
    monkeypatch.setattr(
        Render, "get_renderer_from_map", lambda self, *args, **kw: renderer
    )
    return tool(**kwargs)


def test_viewport_center_matches_bounds_for_content_sized_render(monkeypatch):
    size = {
        "minX": -4.0,
        "minY": 2.0,
        "maxX": 6.0,
        "maxY": 12.0,
        "width": 10,
        "height": 10,
    }
    result = _render(monkeypatch, size, 100.0, 50.0, max_render_radius=None)
    viewport = result.viewport
    assert viewport.center_x == pytest.approx(
        (viewport.world_min_x + viewport.world_max_x) / 2
    )
    assert viewport.center_y == pytest.approx(
        (viewport.world_min_y + viewport.world_max_y) / 2
    )
    assert viewport.center_x == pytest.approx(101.0)
    assert viewport.center_y == pytest.approx(57.0)


def test_viewport_center_uses_player_offset_for_max_radius_render(monkeypatch):
    size = {
        "minX": -32.0,
        "minY": -32.0,
        "maxX": 32.0,
        "maxY": 32.0,
        "width": 64,
        "height": 64,
    }
    result = _render(monkeypatch, size, 100.0, 50.0)
    assert result.viewport.center_x == pytest.approx(100.0)
    assert result.viewport.center_y == pytest.approx(50.0)
