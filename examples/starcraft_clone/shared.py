from nanocalibur.dsl_markers import CodeBlock, Game, Multiplayer, Scene


CodeBlock.begin("starcraft_clone_shared")
"""Create shared game + scene objects for the StarCraft clone modules."""

game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)

game.set_multiplayer(
    Multiplayer(
        default_loop="real_time",
        allowed_loops=["real_time", "hybrid", "turn_based"],
        default_visibility="shared",
        tick_rate=20,
        turn_timeout_ms=15_000,
        hybrid_window_ms=500,
        game_time_scale=1.0,
        max_catchup_steps=1,
    )
)

game.add_global("state", "playing")
game.add_global("winner", "")

CodeBlock.end("starcraft_clone_shared")
