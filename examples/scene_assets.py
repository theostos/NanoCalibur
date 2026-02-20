from nanocalibur.dsl_markers import CodeBlock, Sprite

from .scene_shared import game


CodeBlock.begin("resources_and_sprites")
"""Load image resources and bind named sprite clips."""

game.add_resource(
    "hero_sheet",
    "img/Solaria Demo Pack Update 03/Solaria Demo Pack Update 03/16x16/Sprites/Hero 01.png",
)
game.add_resource(
    "coin_sheet",
    "img/Solaria Demo Pack Update 03/Solaria Demo Pack Update 03/16x16/Sprites/Slime 01.png",
)

game.add_sprite(
    Sprite(
        name="hero",
        resource="hero_sheet",
        frame_width=16,
        frame_height=16,
        default_clip="idle",
        symbol="@",
        description="the player hero",
        flip_x=True,
        clips={
            "idle": {"frames": [0, 1, 2, 3], "ticks_per_frame": 8, "loop": True},
            "run": {"frames": [8, 9, 10, 11], "ticks_per_frame": 6, "loop": True},
        },
    )
)

game.add_sprite(
    Sprite(
        name="coin",
        resource="coin_sheet",
        frame_width=16,
        frame_height=16,
        default_clip="idle",
        symbol="c",
        description="a coin to collect",
        clips={
            "idle": {"frames": [0, 1, 2, 3], "ticks_per_frame": 7, "loop": True},
        },
    )
)

CodeBlock.end("resources_and_sprites")
