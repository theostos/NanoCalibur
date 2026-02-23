from nanocalibur.dsl_markers import Camera, CodeBlock, Color, Role, Tile, TileMap, View

from .shared import (
    MAP_HEIGHT_TILES,
    MAP_WIDTH_TILES,
    MINIMAP_VIEW_H,
    MINIMAP_VIEW_W,
    MINIMAP_VIEW_X,
    MINIMAP_VIEW_Y,
    TILE_SIZE,
    VIEWPORT_TILES_H,
    VIEWPORT_TILES_W,
    WORLD_HEIGHT_PX,
    WORLD_WIDTH_PX,
    scene,
)


CodeBlock.begin("world_layout")
"""Large map + per-role cameras for multiplayer RTS debugging."""

camera_human_1 = Camera(
    "camera_human_1",
    Role["human_1"],
    width=VIEWPORT_TILES_W,
    height=VIEWPORT_TILES_H,
    x=256,
    y=336,
)
scene.add_camera(camera_human_1)

camera_human_1_minimap = Camera(
    "camera_human_1_minimap",
    Role["human_1"],
    width=MAP_WIDTH_TILES,
    height=MAP_HEIGHT_TILES,
    x=WORLD_WIDTH_PX / 2,
    y=WORLD_HEIGHT_PX / 2,
)
scene.add_camera(camera_human_1_minimap)

camera_human_2 = Camera(
    "camera_human_2",
    Role["human_2"],
    width=VIEWPORT_TILES_W,
    height=VIEWPORT_TILES_H,
    x=WORLD_WIDTH_PX - 256,
    y=WORLD_HEIGHT_PX - 336,
)
scene.add_camera(camera_human_2)

camera_human_2_minimap = Camera(
    "camera_human_2_minimap",
    Role["human_2"],
    width=MAP_WIDTH_TILES,
    height=MAP_HEIGHT_TILES,
    x=WORLD_WIDTH_PX / 2,
    y=WORLD_HEIGHT_PX / 2,
)
scene.add_camera(camera_human_2_minimap)

scene.add_view(
    View(
        "main_h1",
        Role["human_1"],
        camera=Camera["camera_human_1"],
        x=0.0,
        y=0.0,
        width=1.0,
        height=1.0,
        z=0,
        interactive=True,
        symbolic=True,
    )
)
scene.add_view(
    View(
        "minimap_h1",
        Role["human_1"],
        camera=Camera["camera_human_1_minimap"],
        x=MINIMAP_VIEW_X,
        y=MINIMAP_VIEW_Y,
        width=MINIMAP_VIEW_W,
        height=MINIMAP_VIEW_H,
        z=5,
        interactive=True,
        symbolic=True,
    )
)
scene.add_view(
    View(
        "main_h2",
        Role["human_2"],
        camera=Camera["camera_human_2"],
        x=0.0,
        y=0.0,
        width=1.0,
        height=1.0,
        z=0,
        interactive=True,
        symbolic=True,
    )
)
scene.add_view(
    View(
        "minimap_h2",
        Role["human_2"],
        camera=Camera["camera_human_2_minimap"],
        x=MINIMAP_VIEW_X,
        y=MINIMAP_VIEW_Y,
        width=MINIMAP_VIEW_W,
        height=MINIMAP_VIEW_H,
        z=5,
        interactive=True,
        symbolic=True,
    )
)

scene.set_map(
    TileMap(
        width=MAP_WIDTH_TILES,
        height=MAP_HEIGHT_TILES,
        tile_size=TILE_SIZE,
        grid="grid/rts_large_map.txt",
        tiles={
            1: Tile(
                color=Color(
                    54,
                    98,
                    58,
                    symbol=".",
                    description="open grass terrain",
                ),
            ),
            2: Tile(
                block_mask=2,
                color=Color(
                    42,
                    49,
                    60,
                    symbol="#",
                    description="high cliff wall",
                ),
            ),
        },
    )
)

CodeBlock.end("world_layout")
