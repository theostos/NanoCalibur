from nanocalibur.dsl_markers import (
    Actor,
    Camera,
    Color,
    Tick,
    Game,
    Global,
    KeyboardCondition,
    Multiplayer,
    OnOverlap,
    Scene,
    Sprite,
    Tile,
    TileMap,
    OnToolCall,
    condition,
)


class Player(Actor):
    speed: int


class Coin(Actor):
    pass


@condition(KeyboardCondition.on_press("d"))
def move_right(player: Player["hero"]):
    player.x = player.x + player.speed
    player.play("run")

@condition(KeyboardCondition.on_press("q"))
def move_left(player: Player["hero"]):
    player.x = player.x - player.speed
    player.play("run")

@condition(KeyboardCondition.on_press("z"))
def move_up(player: Player["hero"]):
    player.y = player.y - player.speed
    player.play("run")

@condition(KeyboardCondition.on_press("s"))
def move_down(player: Player["hero"]):
    player.y = player.y + player.speed
    player.play("run")


@condition(KeyboardCondition.end_press(["z", "q", "s", "d"]))
def idle(player: Player["hero"]):
    player.play("idle")


@condition(OnToolCall("llm_dummy_move_right", "Move llm_dummy right"))
def llm_dummy_move_right(bot: Player["llm_dummy"]):
    bot.x = bot.x + bot.speed
    bot.play("run")


@condition(OnToolCall("llm_dummy_move_left", "Move llm_dummy left"))
def llm_dummy_move_left(bot: Player["llm_dummy"]):
    bot.x = bot.x - bot.speed
    bot.play("run")


@condition(OnToolCall("llm_dummy_move_up", "Move llm_dummy up"))
def llm_dummy_move_up(bot: Player["llm_dummy"]):
    bot.y = bot.y - bot.speed
    bot.play("run")


@condition(OnToolCall("llm_dummy_move_down", "Move llm_dummy down"))
def llm_dummy_move_down(bot: Player["llm_dummy"]):
    bot.y = bot.y + bot.speed
    bot.play("run")


@condition(OnToolCall("llm_dummy_idle", "Set llm_dummy to idle animation"))
def llm_dummy_idle(bot: Player["llm_dummy"]):
    bot.play("idle")


@condition(OnToolCall("llm_dummy_next_turn", "Advance scene turn"))
def llm_dummy_next_turn(scene: Scene):
    scene.next_turn()

@condition(OnOverlap(Player["hero"], Coin))
def collect_coin(
    hero: Player,
    coin: Coin,
    score: Global["score", int],
):
    if coin.active and coin.uid != "coin_pet":
        coin.destroy()
        score = score + 1


@condition(KeyboardCondition.begin_press("g"))
def enable_gravity(scene: Scene):
    scene.enable_gravity()


@condition(KeyboardCondition.begin_press("h"))
def disable_gravity(scene: Scene):
    scene.disable_gravity()

@condition(KeyboardCondition.begin_press("e"))
@condition(OnToolCall("spawn_bonus", "Spawn one bonus coin near the hero"))
def spawn_bonus(scene: Scene, tick: Tick, last_coin: Coin[-1]):
    for _ in range(20):
        yield tick
    if last_coin is not None and scene.elapsed > 300:
        new_x = last_coin.x + 32
        coin = Coin(x=new_x,
            y=224,
            active=True,
            sprite="coin",
        )
        scene.spawn(coin)
    scene.next_turn()


game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.set_multiplayer(
    Multiplayer(
        default_loop="hybrid",
        allowed_loops=["hybrid", "turn_based", "real_time"],
        default_visibility="shared",
        tick_rate=20,
        turn_timeout_ms=15000,
        hybrid_window_ms=600,
        game_time_scale=0.75,
        max_catchup_steps=1,
    )
)
game.add_global("score", 0)
game.set_interface(
    """
<div style="position:absolute;left:12px;top:12px;padding:8px 10px;background:rgba(8,10,14,0.62);color:#f2f5fa;border-radius:8px;font-family:monospace;">
  <div>Actors: {{__actors_count}}</div>
  <div>Score: {{score}}</div>
</div>
"""
)

hero_player = Player(
        uid="hero",
        x=160,
        y=224,
        w=32,
        h=32,
        speed=5,
        z=1,
        block_mask=1,
        sprite="hero",
    )

scene.add_actor(hero_player)

llm_dummy_player = Player(
        uid="llm_dummy",
        x=96,
        y=224,
        w=32,
        h=32,
        speed=4,
        z=1,
        block_mask=1,
        sprite="hero",
    )

scene.add_actor(llm_dummy_player)

coin = Coin(uid="coin_1", x=320, y=224, active=True, sprite="coin")
scene.add_actor(coin)

coin_pet = Coin(uid="coin_pet", x=200, y=300, block_mask=1, parent="hero", active=True, sprite="coin")
scene.add_actor(coin_pet)

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


scene.set_camera(Camera.follow("hero"))
scene.set_map(
    TileMap(
        tile_size=32,
        grid="../nanocalibur-demo/grid/level.txt",
        tiles={
            1: Tile(
                block_mask=2,
                color=Color(
                    68,
                    74,
                    94,
                    symbol="#",
                    description="a solid stone block",
                )
            ),
        },
    )
)
