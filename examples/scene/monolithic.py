from nanocalibur.dsl_markers import (
    Actor,
    Camera,
    CodeBlock,
    Color,
    Game,
    Global,
    Interface,
    KeyboardCondition,
    Multiplayer,
    OnOverlap,
    OnToolCall,
    Resource,
    Role,
    RoleKind,
    Scene,
    Sprite,
    Tick,
    Tile,
    TileMap,
    safe_condition,
    unsafe_condition,
)


CodeBlock.begin("main")
"""Complete multiplayer sample packed into one code block."""

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


class Player(Actor):
    speed: int


class Coin(Actor):
    pass


class HeroRole(Role):
    score: int


hero_sheet = Resource(
    "hero_sheet",
    "img/Solaria Demo Pack Update 03/Solaria Demo Pack Update 03/16x16/Sprites/Hero 01.png",
)
coin_sheet = Resource(
    "coin_sheet",
    "img/Solaria Demo Pack Update 03/Solaria Demo Pack Update 03/16x16/Sprites/Slime 01.png",
)
game.add_resource(hero_sheet)
game.add_resource(coin_sheet)

game.add_sprite(
    Sprite(
        name="hero",
        resource=Resource["hero_sheet"],
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
        resource=Resource["coin_sheet"],
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

for k in range(1, 5):
    game.add_role(
        HeroRole(
            id=f"human_{k}",
            required=(k == 1),
            kind=RoleKind.HUMAN,
            score=0,
        )
    )
game.add_role(HeroRole(id="dummy_1", required=False, kind=RoleKind.AI))

scene.set_interface(Interface("ui/hud_human.html", HeroRole["human_1"]))
scene.set_interface(Interface("ui/hud_human.html", HeroRole["human_2"]))
scene.set_interface(Interface("ui/hud_human.html", HeroRole["human_3"]))
scene.set_interface(Interface("ui/hud_human.html", HeroRole["human_4"]))

camera_h1 = Camera("camera_human_1", Role["human_1"], width=30, height=18)
camera_h1.follow("hero_1")
scene.add_camera(camera_h1)

scene.set_map(
    TileMap(
        tile_size=32,
        grid="../../nanocalibur-demo/grid/level.txt",
        tiles={
            1: Tile(
                block_mask=2,
                color=Color(
                    68,
                    74,
                    94,
                    symbol="#",
                    description="a solid stone block",
                ),
            ),
        },
    )
)

scene.add_actor(
    Player(
        uid="hero_1",
        x=160,
        y=224,
        w=32,
        h=32,
        speed=180,
        z=1,
        block_mask=1,
        sprite=Sprite["hero"],
    )
)
scene.add_actor(
    Player(
        uid="hero_2",
        x=192,
        y=224,
        w=32,
        h=32,
        speed=170,
        z=1,
        block_mask=1,
        sprite=Sprite["hero"],
    )
)
scene.add_actor(
    Player(
        uid="hero_3",
        x=224,
        y=224,
        w=32,
        h=32,
        speed=170,
        z=1,
        block_mask=1,
        sprite=Sprite["hero"],
    )
)
scene.add_actor(
    Player(
        uid="hero_4",
        x=256,
        y=224,
        w=32,
        h=32,
        speed=170,
        z=1,
        block_mask=1,
        sprite=Sprite["hero"],
    )
)
scene.add_actor(
    Player(
        uid="llm_dummy",
        x=96,
        y=224,
        w=32,
        h=32,
        speed=140,
        z=1,
        block_mask=1,
        sprite=Sprite["hero"],
    )
)
scene.add_actor(Coin(uid="coin_1", x=320, y=224, active=True, sprite=Sprite["coin"]))
scene.add_actor(
    Coin(
        uid="coin_pet",
        x=200,
        y=300,
        block_mask=1,
        parent="hero_1",
        active=True,
        sprite=Sprite["coin"],
    )
)


@unsafe_condition(KeyboardCondition.on_press("d", Role["human_1"]))
def human_1_move_right(player: Player["hero_1"]):
    player.vx = player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press("q", Role["human_1"]))
def human_1_move_left(player: Player["hero_1"]):
    player.vx = -player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press("z", Role["human_1"]))
def human_1_move_up(player: Player["hero_1"]):
    player.vy = -player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press("s", Role["human_1"]))
def human_1_move_down(player: Player["hero_1"]):
    player.vy = player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.end_press(["q", "d"], Role["human_1"]))
def human_1_stop_horizontal(player: Player["hero_1"]):
    player.vx = 0
    if player.vy == 0:
        player.play("idle")


@unsafe_condition(KeyboardCondition.end_press(["z", "s"], Role["human_1"]))
def human_1_stop_vertical(player: Player["hero_1"]):
    player.vy = 0
    if player.vx == 0:
        player.play("idle")


@unsafe_condition(KeyboardCondition.on_press("l", Role["human_2"]))
def human_2_move_right(player: Player["hero_2"]):
    player.vx = player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press("j", Role["human_2"]))
def human_2_move_left(player: Player["hero_2"]):
    player.vx = -player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press("i", Role["human_2"]))
def human_2_move_up(player: Player["hero_2"]):
    player.vy = -player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press("k", Role["human_2"]))
def human_2_move_down(player: Player["hero_2"]):
    player.vy = player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.end_press(["j", "l"], Role["human_2"]))
def human_2_stop_horizontal(player: Player["hero_2"]):
    player.vx = 0
    if player.vy == 0:
        player.play("idle")


@unsafe_condition(KeyboardCondition.end_press(["i", "k"], Role["human_2"]))
def human_2_stop_vertical(player: Player["hero_2"]):
    player.vy = 0
    if player.vx == 0:
        player.play("idle")


@unsafe_condition(KeyboardCondition.on_press("ArrowRight", Role["human_3"]))
def human_3_move_right(player: Player["hero_3"]):
    player.vx = player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press("ArrowLeft", Role["human_3"]))
def human_3_move_left(player: Player["hero_3"]):
    player.vx = -player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press("ArrowUp", Role["human_3"]))
def human_3_move_up(player: Player["hero_3"]):
    player.vy = -player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press("ArrowDown", Role["human_3"]))
def human_3_move_down(player: Player["hero_3"]):
    player.vy = player.speed
    player.play("run")


@unsafe_condition(
    KeyboardCondition.end_press(["ArrowLeft", "ArrowRight"], Role["human_3"])
)
def human_3_stop_horizontal(player: Player["hero_3"]):
    player.vx = 0
    if player.vy == 0:
        player.play("idle")


@unsafe_condition(KeyboardCondition.end_press(["ArrowUp", "ArrowDown"], Role["human_3"]))
def human_3_stop_vertical(player: Player["hero_3"]):
    player.vy = 0
    if player.vx == 0:
        player.play("idle")


@unsafe_condition(KeyboardCondition.on_press("h", Role["human_4"]))
def human_4_move_right(player: Player["hero_4"]):
    player.vx = player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press("f", Role["human_4"]))
def human_4_move_left(player: Player["hero_4"]):
    player.vx = -player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press("t", Role["human_4"]))
def human_4_move_up(player: Player["hero_4"]):
    player.vy = -player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.on_press("g", Role["human_4"]))
def human_4_move_down(player: Player["hero_4"]):
    player.vy = player.speed
    player.play("run")


@unsafe_condition(KeyboardCondition.end_press(["f", "h"], Role["human_4"]))
def human_4_stop_horizontal(player: Player["hero_4"]):
    player.vx = 0
    if player.vy == 0:
        player.play("idle")


@unsafe_condition(KeyboardCondition.end_press(["t", "g"], Role["human_4"]))
def human_4_stop_vertical(player: Player["hero_4"]):
    player.vy = 0
    if player.vx == 0:
        player.play("idle")


@unsafe_condition(OnToolCall("llm_dummy_move_right", Role["dummy_1"]))
def llm_dummy_move_right(bot: Player["llm_dummy"]):
    """Move llm_dummy right."""
    bot.vx = bot.speed
    bot.play("run")


@unsafe_condition(OnToolCall("llm_dummy_move_left", Role["dummy_1"]))
def llm_dummy_move_left(bot: Player["llm_dummy"]):
    """Move llm_dummy left."""
    bot.vx = -bot.speed
    bot.play("run")


@unsafe_condition(OnToolCall("llm_dummy_move_up", Role["dummy_1"]))
def llm_dummy_move_up(bot: Player["llm_dummy"]):
    """Move llm_dummy up."""
    bot.vy = -bot.speed
    bot.play("run")


@unsafe_condition(OnToolCall("llm_dummy_move_down", Role["dummy_1"]))
def llm_dummy_move_down(bot: Player["llm_dummy"]):
    """Move llm_dummy down."""
    bot.vy = bot.speed
    bot.play("run")


@unsafe_condition(OnToolCall("llm_dummy_idle", Role["dummy_1"]))
def llm_dummy_idle(bot: Player["llm_dummy"]):
    """Set llm_dummy to idle animation."""
    bot.vx = 0
    bot.vy = 0
    bot.play("idle")


@safe_condition(OnOverlap(Player["hero_1"], Coin))
def collect_coin_for_player_1(
    hero: Player,
    coin: Coin,
    role: HeroRole["human_1"],
    global_score: Global["global_score", int],
):
    if coin.active and coin.uid != "coin_pet":
        coin.destroy()
        role.score = role.score + 1
        global_score = global_score + 1


@safe_condition(OnOverlap(Player["hero_2"], Coin))
def collect_coin_for_player_2(
    hero: Player,
    coin: Coin,
    role: HeroRole["human_2"],
    global_score: Global["global_score", int],
):
    if coin.active and coin.uid != "coin_pet":
        coin.destroy()
        role.score = role.score + 1
        global_score = global_score + 1


@safe_condition(OnOverlap(Player["hero_3"], Coin))
def collect_coin_for_player_3(
    hero: Player,
    coin: Coin,
    role: HeroRole["human_3"],
    global_score: Global["global_score", int],
):
    if coin.active and coin.uid != "coin_pet":
        coin.destroy()
        role.score = role.score + 1
        global_score = global_score + 1


@safe_condition(OnOverlap(Player["hero_4"], Coin))
def collect_coin_for_player_4(
    hero: Player,
    coin: Coin,
    role: HeroRole["human_4"],
    global_score: Global["global_score", int],
):
    if coin.active and coin.uid != "coin_pet":
        coin.destroy()
        role.score = role.score + 1
        global_score = global_score + 1


@safe_condition(OnOverlap(Player["llm_dummy"], Coin))
def collect_coin_for_dummy(
    hero: Player,
    coin: Coin,
    role: HeroRole["dummy_1"],
    global_score: Global["global_score", int],
):
    if coin.active and coin.uid != "coin_pet":
        coin.destroy()
        role.score = role.score + 1
        global_score = global_score + 1


@unsafe_condition(KeyboardCondition.begin_press("g", Role["human_1"]))
def enable_gravity(scene: Scene):
    scene.enable_gravity()


@unsafe_condition(KeyboardCondition.begin_press("h", Role["human_1"]))
def disable_gravity(scene: Scene):
    scene.disable_gravity()


@unsafe_condition(KeyboardCondition.begin_press("e", Role["human_1"]))
@unsafe_condition(OnToolCall("spawn_bonus", Role["human_1"]))
def spawn_bonus(scene: Scene, tick: Tick, last_coin: Coin[-1]):
    """Spawn one bonus coin near hero_1."""
    for _ in range(20):
        yield tick
    if last_coin is not None and scene.elapsed > 300:
        scene.spawn(
            Coin(
                x=last_coin.x + 32,
                y=224,
                active=True,
                sprite="coin",
            )
        )
    scene.next_turn()


@unsafe_condition(OnToolCall("llm_dummy_next_turn", Role["dummy_1"]))
def llm_dummy_next_turn(scene: Scene):
    """Advance scene turn."""
    scene.next_turn()


CodeBlock.end("main")
