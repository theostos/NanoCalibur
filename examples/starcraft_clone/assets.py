from nanocalibur.dsl_markers import BlockInSprite, CodeBlock, Color, ColorSprite, Resource

from .shared import game


CodeBlock.begin("starcraft_clone_assets")
"""Resource declarations and sprite bindings with BlockInSprite fallback colors."""

starcraft_sheet = Resource("starcraft_sheet", "img/starcraft/sheet.png")
game.add_resource(starcraft_sheet)

idle = {"idle": {"frames": [0], "ticks_per_frame": 8, "loop": True}}

# Units
game.add_sprite(
    BlockInSprite(
        name="worker",
        resource=Resource["starcraft_sheet"],
        frame_width=16,
        frame_height=16,
        color=Color(220, 205, 120),
        default_clip="idle",
        symbol="w",
        description="worker unit",
        clips=idle,
    )
)

game.add_sprite(
    BlockInSprite(
        name="marine",
        resource=Resource["starcraft_sheet"],
        frame_width=16,
        frame_height=16,
        color=Color(90, 170, 255),
        default_clip="idle",
        symbol="m",
        description="marine unit",
        clips=idle,
    )
)

game.add_sprite(
    BlockInSprite(
        name="marauder",
        resource=Resource["starcraft_sheet"],
        frame_width=16,
        frame_height=16,
        color=Color(255, 120, 90),
        default_clip="idle",
        symbol="M",
        description="marauder unit",
        clips=idle,
    )
)

game.add_sprite(
    BlockInSprite(
        name="medic",
        resource=Resource["starcraft_sheet"],
        frame_width=16,
        frame_height=16,
        color=Color(150, 240, 150),
        default_clip="idle",
        symbol="+",
        description="medic unit",
        clips=idle,
    )
)

game.add_sprite(
    BlockInSprite(
        name="tank",
        resource=Resource["starcraft_sheet"],
        frame_width=16,
        frame_height=16,
        color=Color(170, 150, 230),
        default_clip="idle",
        symbol="T",
        description="tank unit",
        clips=idle,
    )
)

game.add_sprite(
    BlockInSprite(
        name="scout",
        resource=Resource["starcraft_sheet"],
        frame_width=16,
        frame_height=16,
        color=Color(245, 190, 90),
        default_clip="idle",
        symbol="S",
        description="scout unit",
        clips=idle,
    )
)

# Buildings
game.add_sprite(
    BlockInSprite(
        name="hq",
        resource=Resource["starcraft_sheet"],
        frame_width=32,
        frame_height=32,
        color=Color(70, 70, 180),
        default_clip="idle",
        symbol="H",
        description="headquarters building",
        clips=idle,
    )
)

game.add_sprite(
    BlockInSprite(
        name="supply",
        resource=Resource["starcraft_sheet"],
        frame_width=24,
        frame_height=24,
        color=Color(120, 120, 220),
        default_clip="idle",
        symbol="D",
        description="supply depot building",
        clips=idle,
    )
)

game.add_sprite(
    BlockInSprite(
        name="barracks",
        resource=Resource["starcraft_sheet"],
        frame_width=28,
        frame_height=28,
        color=Color(160, 90, 210),
        default_clip="idle",
        symbol="B",
        description="barracks building",
        clips=idle,
    )
)

game.add_sprite(
    BlockInSprite(
        name="refinery",
        resource=Resource["starcraft_sheet"],
        frame_width=24,
        frame_height=24,
        color=Color(90, 190, 120),
        default_clip="idle",
        symbol="R",
        description="refinery building",
        clips=idle,
    )
)

game.add_sprite(
    BlockInSprite(
        name="factory",
        resource=Resource["starcraft_sheet"],
        frame_width=30,
        frame_height=30,
        color=Color(210, 100, 150),
        default_clip="idle",
        symbol="F",
        description="factory building",
        clips=idle,
    )
)

game.add_sprite(
    BlockInSprite(
        name="lab",
        resource=Resource["starcraft_sheet"],
        frame_width=26,
        frame_height=26,
        color=Color(100, 220, 210),
        default_clip="idle",
        symbol="L",
        description="lab building",
        clips=idle,
    )
)

# Resources
game.add_sprite(
    ColorSprite(
        name="mineral",
        frame_width=16,
        frame_height=16,
        color=Color(120, 230, 255),
        symbol="*",
        description="mineral patch",
    )
)

game.add_sprite(
    ColorSprite(
        name="gas",
        frame_width=16,
        frame_height=16,
        color=Color(120, 255, 160),
        symbol="g",
        description="gas geyser",
    )
)

CodeBlock.end("starcraft_clone_assets")
