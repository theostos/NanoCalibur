from nanocalibur.dsl_markers import Camera, CodeBlock, Color, Tile, TileMap

from .scene_shared import scene


CodeBlock.begin(
    "world_layout",
    descr="Camera + tile map configuration for the shared scene.",
)

scene.set_camera(Camera.follow("hero_1"))
scene.set_map(
    TileMap(
        tile_size=32,
        grid="../nanocalibur-demo/grid/level.txt",
        tiles={
            1: Tile(
                block_mask=2,
                color=Color(
                    68,
                    74,
                    94,
                    symbol="#",
                    description="a solid stone block",
                ),
            ),
        },
    )
)

CodeBlock.end("world_layout")
