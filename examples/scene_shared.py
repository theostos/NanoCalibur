from nanocalibur.dsl_markers import CodeBlock, Game, Multiplayer, Scene


CodeBlock.begin("shared_context")
"""Create game/scene once so every feature module can import and extend them."""

game = Game()
scene = Scene(
    gravity=False,
    keyboard_aliases={
        "z": ["w"],
        "q": ["a"],
    },
)
game.set_scene(scene)

game.set_multiplayer(
    Multiplayer(
        default_loop="hybrid",
        allowed_loops=["hybrid", "turn_based", "real_time"],
        default_visibility="shared",
        tick_rate=30,
        turn_timeout_ms=15000,
        hybrid_window_ms=600,
        game_time_scale=0.75,
        max_catchup_steps=1,
    )
)

game.add_global("global_score", 0)

CodeBlock.end("shared_context")
