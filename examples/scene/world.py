from nanocalibur.dsl_markers import Camera, CodeBlock, Color, Role, Tile, TileMap

from .shared import scene


CodeBlock.begin("world_layout")
"""Camera + tile map configuration for the shared scene."""

camera_human_1 = Camera("camera_human_1", Role["human_1"], width=30, height=18)
camera_human_1.follow("hero_1")
scene.add_camera(camera_human_1)

camera_human_2 = Camera("camera_human_2", Role["human_2"], width=30, height=18)
camera_human_2.follow("hero_2")
scene.add_camera(camera_human_2)

camera_human_3 = Camera("camera_human_3", Role["human_3"], width=30, height=18)
camera_human_3.follow("hero_3")
scene.add_camera(camera_human_3)

camera_human_4 = Camera("camera_human_4", Role["human_4"], width=30, height=18)
camera_human_4.follow("hero_4")
scene.add_camera(camera_human_4)

camera_dummy_1 = Camera("camera_dummy_1", Role["dummy_1"], width=30, height=18)
camera_dummy_1.follow("llm_dummy")
scene.add_camera(camera_dummy_1)
scene.set_map(
    TileMap(
        tile_size=32,
        grid="../../nanocalibur-demo/grid/level.txt",
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
