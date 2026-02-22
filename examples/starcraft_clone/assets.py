from nanocalibur.dsl_markers import CodeBlock, Color, ColorSprite

from .shared import game


CodeBlock.begin("resources_and_sprites")
"""Color sprites keep this sandbox dependency-free while staying readable."""

game.add_sprite(
    ColorSprite(
        name="worker_p1",
        frame_width=20,
        frame_height=20,
        color=Color(72, 141, 255, symbol="w", description="player 1 worker"),
        symbol="w",
        description="player 1 worker",
    )
)
game.add_sprite(
    ColorSprite(
        name="worker_p2",
        frame_width=20,
        frame_height=20,
        color=Color(227, 98, 83, symbol="w", description="player 2 worker"),
        symbol="w",
        description="player 2 worker",
    )
)
game.add_sprite(
    ColorSprite(
        name="hq_p1",
        frame_width=64,
        frame_height=64,
        color=Color(76, 199, 233, symbol="H", description="player 1 HQ"),
        symbol="H",
        description="player 1 HQ",
    )
)
game.add_sprite(
    ColorSprite(
        name="hq_p2",
        frame_width=64,
        frame_height=64,
        color=Color(233, 171, 70, symbol="H", description="player 2 HQ"),
        symbol="H",
        description="player 2 HQ",
    )
)
game.add_sprite(
    ColorSprite(
        name="selection_marker_p1",
        frame_width=20,
        frame_height=20,
        color=Color(
            70,
            240,
            112,
            a=0.45,
            symbol="*",
            description="player 1 selection marker",
        ),
        symbol="*",
        description="player 1 selection marker",
    )
)
game.add_sprite(
    ColorSprite(
        name="selection_marker_p2",
        frame_width=20,
        frame_height=20,
        color=Color(
            70,
            240,
            112,
            a=0.45,
            symbol="*",
            description="player 2 selection marker",
        ),
        symbol="*",
        description="player 2 selection marker",
    )
)
game.add_sprite(
    ColorSprite(
        name="drag_select_rect_p1",
        frame_width=16,
        frame_height=16,
        color=Color(
            95,
            255,
            140,
            a=0.25,
            symbol="+",
            description="player 1 drag select rectangle",
        ),
        symbol="+",
        description="player 1 drag select rectangle",
    )
)
game.add_sprite(
    ColorSprite(
        name="drag_select_rect_p2",
        frame_width=16,
        frame_height=16,
        color=Color(
            95,
            255,
            140,
            a=0.25,
            symbol="+",
            description="player 2 drag select rectangle",
        ),
        symbol="+",
        description="player 2 drag select rectangle",
    )
)
game.add_sprite(
    ColorSprite(
        name="mineral_node",
        frame_width=48,
        frame_height=48,
        color=Color(96, 209, 255, a=0.95, symbol="M", description="mineral field"),
        symbol="M",
        description="mineral field",
    )
)
game.add_sprite(
    ColorSprite(
        name="gas_node",
        frame_width=44,
        frame_height=44,
        color=Color(130, 255, 152, a=0.92, symbol="G", description="vespene geyser"),
        symbol="G",
        description="vespene geyser",
    )
)

CodeBlock.end("resources_and_sprites")
