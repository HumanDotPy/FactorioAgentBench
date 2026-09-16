from typing import Dict, Callable
from PIL import ImageDraw

from fle.env.tools.admin.render.layers.layer_renderer import LayerRenderer
from fle.env.tools.admin.render.utils.tile_renderer import TileRenderer


class WaterLayerRenderer(LayerRenderer):
    """Renderer for water tiles"""

    def __init__(self, config):
        super().__init__(config)
        self.tile_renderer = TileRenderer(config)

    @property
    def layer_name(self) -> str:
        return "water"

    def render(
        self,
        draw: ImageDraw.ImageDraw,
        game_to_img_func: Callable,
        boundaries: Dict[str, float],
        **kwargs,
    ) -> None:
        """Draw water tiles on the map"""
        self.tile_renderer.draw_water_tiles(
            draw, kwargs.get("water_tiles", []), game_to_img_func, boundaries
        )
