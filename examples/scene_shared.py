from nanocalibur.dsl_markers import CodeBlock, Game, Multiplayer, Role, Scene


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

game.add_global("score", 0)

scene.set_interface(
    """
<div style="position:absolute;left:12px;top:12px;padding:8px 10px;background:rgba(8,10,14,0.62);color:#f2f5fa;border-radius:8px;font-family:monospace;">
  <div>Actors: {{__actors_count}}</div>
  <div>Score: {{score}}</div>
</div>
""",
    Role["human_1"],
)

CodeBlock.end("shared_context")
