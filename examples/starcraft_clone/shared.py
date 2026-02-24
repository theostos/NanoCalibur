from nanocalibur.dsl_markers import CodeBlock, Game, Multiplayer, Scene


CodeBlock.begin("shared_context")
"""Shared RTS sandbox context reused by independent starcraft_clone features."""

TILE_SIZE = 32
MAP_WIDTH_TILES = 96
MAP_HEIGHT_TILES = 72

VIEWPORT_TILES_W = 30
VIEWPORT_TILES_H = 20
VIEWPORT_WIDTH_PX = VIEWPORT_TILES_W * TILE_SIZE
VIEWPORT_HEIGHT_PX = VIEWPORT_TILES_H * TILE_SIZE

MINIMAP_VIEW_X = 0.78
MINIMAP_VIEW_Y = 0.72
MINIMAP_VIEW_W = 0.20
MINIMAP_VIEW_H = 0.24
MINIMAP_GRID_SIZE = 32

WORLD_WIDTH_PX = MAP_WIDTH_TILES * TILE_SIZE
WORLD_HEIGHT_PX = MAP_HEIGHT_TILES * TILE_SIZE
MINIMAP_WORLD_PX = MINIMAP_GRID_SIZE * TILE_SIZE
HALF_VIEW_W_PX = VIEWPORT_WIDTH_PX / 2
HALF_VIEW_H_PX = VIEWPORT_HEIGHT_PX / 2
WORKER_MOVE_SPEED = 300
CAMERA_PAN_SPEED = 8

game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)

game.set_multiplayer(
    Multiplayer(
        default_loop="real_time",
        allowed_loops=["real_time", "hybrid", "turn_based"],
        default_visibility="shared",
        tick_rate=60,
        turn_timeout_ms=15000,
        hybrid_window_ms=600,
        game_time_scale=1.0,
        max_catchup_steps=1,
    )
)

CodeBlock.end("shared_context")
