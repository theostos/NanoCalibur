from nanocalibur.dsl_markers import CodeBlock, Color, ColorSprite

from .shared import game
from .shared import TILE_SIZE


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
        name="marine_p1",
        frame_width=20,
        frame_height=20,
        color=Color(96, 176, 255, symbol="m", description="player 1 marine"),
        symbol="m",
        description="player 1 marine",
    )
)
game.add_sprite(
    ColorSprite(
        name="marine_p2",
        frame_width=20,
        frame_height=20,
        color=Color(232, 128, 112, symbol="m", description="player 2 marine"),
        symbol="m",
        description="player 2 marine",
    )
)
game.add_sprite(
    ColorSprite(
        name="flamethrower_p1",
        frame_width=20,
        frame_height=20,
        color=Color(110, 206, 255, symbol="f", description="player 1 flamethrower"),
        symbol="f",
        description="player 1 flamethrower",
    )
)
game.add_sprite(
    ColorSprite(
        name="flamethrower_p2",
        frame_width=20,
        frame_height=20,
        color=Color(245, 145, 108, symbol="f", description="player 2 flamethrower"),
        symbol="f",
        description="player 2 flamethrower",
    )
)
game.add_sprite(
    ColorSprite(
        name="drone_p1",
        frame_width=20,
        frame_height=20,
        color=Color(120, 220, 255, symbol="d", description="player 1 drone"),
        symbol="d",
        description="player 1 drone",
    )
)
game.add_sprite(
    ColorSprite(
        name="drone_p2",
        frame_width=20,
        frame_height=20,
        color=Color(255, 165, 126, symbol="d", description="player 2 drone"),
        symbol="d",
        description="player 2 drone",
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
game.add_sprite(
    ColorSprite(
        name="supply_depot_p1",
        frame_width=48,
        frame_height=48,
        color=Color(103, 214, 186, symbol="S", description="player 1 supply depot"),
        symbol="S",
        description="player 1 supply depot",
    )
)
game.add_sprite(
    ColorSprite(
        name="supply_depot_p2",
        frame_width=48,
        frame_height=48,
        color=Color(214, 147, 103, symbol="S", description="player 2 supply depot"),
        symbol="S",
        description="player 2 supply depot",
    )
)
game.add_sprite(
    ColorSprite(
        name="barracks_p1",
        frame_width=56,
        frame_height=56,
        color=Color(86, 178, 241, symbol="B", description="player 1 barracks"),
        symbol="B",
        description="player 1 barracks",
    )
)
game.add_sprite(
    ColorSprite(
        name="barracks_p2",
        frame_width=56,
        frame_height=56,
        color=Color(220, 130, 90, symbol="B", description="player 2 barracks"),
        symbol="B",
        description="player 2 barracks",
    )
)
game.add_sprite(
    ColorSprite(
        name="academy_p1",
        frame_width=54,
        frame_height=54,
        color=Color(126, 169, 255, symbol="A", description="player 1 academy"),
        symbol="A",
        description="player 1 academy",
    )
)
game.add_sprite(
    ColorSprite(
        name="academy_p2",
        frame_width=54,
        frame_height=54,
        color=Color(230, 136, 124, symbol="A", description="player 2 academy"),
        symbol="A",
        description="player 2 academy",
    )
)
game.add_sprite(
    ColorSprite(
        name="starport_p1",
        frame_width=60,
        frame_height=60,
        color=Color(92, 162, 255, symbol="P", description="player 1 starport"),
        symbol="P",
        description="player 1 starport",
    )
)
game.add_sprite(
    ColorSprite(
        name="starport_p2",
        frame_width=60,
        frame_height=60,
        color=Color(219, 126, 102, symbol="P", description="player 2 starport"),
        symbol="P",
        description="player 2 starport",
    )
)
game.add_sprite(
    ColorSprite(
        name="health_bar_bg",
        frame_width=2,
        frame_height=2,
        color=Color(18, 18, 18, a=0.92, symbol="-", description="health bar background"),
        symbol="-",
        description="health bar background",
    )
)
game.add_sprite(
    ColorSprite(
        name="health_bar_fill_ok",
        frame_width=2,
        frame_height=2,
        color=Color(88, 226, 104, a=0.95, symbol="-", description="health bar high"),
        symbol="-",
        description="health bar high",
    )
)
game.add_sprite(
    ColorSprite(
        name="health_bar_fill_mid",
        frame_width=2,
        frame_height=2,
        color=Color(226, 198, 90, a=0.95, symbol="-", description="health bar medium"),
        symbol="-",
        description="health bar medium",
    )
)
game.add_sprite(
    ColorSprite(
        name="health_bar_fill_low",
        frame_width=2,
        frame_height=2,
        color=Color(225, 85, 85, a=0.95, symbol="-", description="health bar low"),
        symbol="-",
        description="health bar low",
    )
)
game.add_sprite(
    ColorSprite(
        name="fog_unexplored",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(4, 4, 8, a=0.98, symbol="?", description="unexplored shroud"),
        symbol="?",
        description="unexplored shroud",
    )
)
game.add_sprite(
    ColorSprite(
        name="fog_explored",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(18, 20, 24, a=0.95, symbol=":", description="explored fog"),
        symbol=":",
        description="explored fog",
    )
)
game.add_sprite(
    ColorSprite(
        name="minimap_background",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(28, 40, 58, a=0.96, symbol=".", description="minimap background"),
        symbol=".",
        description="minimap background",
    )
)
game.add_sprite(
    ColorSprite(
        name="minimap_fog_explored",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(12, 16, 24, a=0.95, symbol=":", description="minimap explored fog"),
        symbol=":",
        description="minimap explored fog",
    )
)
game.add_sprite(
    ColorSprite(
        name="minimap_fog_unexplored",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(3, 4, 7, a=0.98, symbol="?", description="minimap unexplored fog"),
        symbol="?",
        description="minimap unexplored fog",
    )
)
game.add_sprite(
    ColorSprite(
        name="minimap_blip_self",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(84, 150, 255, a=0.94, symbol="S", description="self unit/building"),
        symbol="S",
        description="self unit/building",
    )
)
game.add_sprite(
    ColorSprite(
        name="minimap_blip_enemy",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(232, 98, 90, a=0.94, symbol="E", description="adversary unit/building"),
        symbol="E",
        description="adversary unit/building",
    )
)
game.add_sprite(
    ColorSprite(
        name="fog_memory_hq",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(44, 52, 64, a=0.97, symbol="h", description="last seen HQ"),
        symbol="h",
        description="last seen HQ",
    )
)
game.add_sprite(
    ColorSprite(
        name="fog_memory_supply_depot",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(40, 58, 58, a=0.97, symbol="s", description="last seen supply depot"),
        symbol="s",
        description="last seen supply depot",
    )
)
game.add_sprite(
    ColorSprite(
        name="fog_memory_barracks",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(44, 52, 68, a=0.97, symbol="b", description="last seen barracks"),
        symbol="b",
        description="last seen barracks",
    )
)
game.add_sprite(
    ColorSprite(
        name="fog_memory_academy",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(50, 52, 70, a=0.97, symbol="a", description="last seen academy"),
        symbol="a",
        description="last seen academy",
    )
)
game.add_sprite(
    ColorSprite(
        name="fog_memory_starport",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(40, 48, 72, a=0.97, symbol="p", description="last seen starport"),
        symbol="p",
        description="last seen starport",
    )
)
game.add_sprite(
    ColorSprite(
        name="fog_memory_mineral",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(48, 66, 78, a=0.97, symbol="m", description="last seen mineral"),
        symbol="m",
        description="last seen mineral",
    )
)
game.add_sprite(
    ColorSprite(
        name="fog_memory_gas",
        frame_width=TILE_SIZE,
        frame_height=TILE_SIZE,
        color=Color(42, 74, 56, a=0.97, symbol="g", description="last seen gas"),
        symbol="g",
        description="last seen gas",
    )
)

CodeBlock.end("resources_and_sprites")
