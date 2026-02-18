from nanocalibur.dsl_markers import (
    Actor,
    Camera,
    Color,
    CollisionRelated,
    Tick,
    Game,
    Global,
    KeyboardCondition,
    Scene,
    Sprite,
    Tile,
    TileMap,
    ToolCalling,
    condition,
    OnButton,
)


class Player(Actor):
    speed: int


class Coin(Actor):
    pass


@condition(KeyboardCondition.on_press("d"))
def move_right(player: Player["hero"]):
    player.x = player.x + player.speed
    Actor.play(player, "run")

@condition(KeyboardCondition.on_press("q"))
def move_left(player: Player["hero"]):
    player.x = player.x - player.speed
    Actor.play(player, "run")

@condition(KeyboardCondition.on_press("z"))
def move_up(player: Player["hero"]):
    player.y = player.y - player.speed
    Actor.play(player, "run")

@condition(KeyboardCondition.on_press("s"))
def move_down(player: Player["hero"]):
    player.y = player.y + player.speed
    Actor.play(player, "run")


@condition(KeyboardCondition.end_press(["z", "q", "s", "d"]))
def idle(player: Player["hero"]):
    Actor.play(player, "idle")

@condition(CollisionRelated(Player["hero"], Coin))
def collect_coin(
    hero: Player,
    coin: Coin,
    score: Global["score", int],
):
    if coin.active and coin.uid != "coin_pet":
        Actor.destroy(coin)
        score = score + 1


@condition(KeyboardCondition.begin_press("g"))
def enable_gravity(scene: Scene):
    scene.enable_gravity()


@condition(KeyboardCondition.begin_press("h"))
def disable_gravity(scene: Scene):
    scene.disable_gravity()

@condition(KeyboardCondition.begin_press("e"))
@condition(OnButton("spawn_bonus"))
@condition(ToolCalling("spawn_bonus", "Spawn one bonus coin near the hero"))
def spawn_bonus(scene: Scene, tick: Tick, last_coin: Coin[-1]):
    for _ in range(20):
        yield tick
    coin = Coin(x=last_coin.x + 32,
        y=224,
        active=True,
        sprite="coin",
    )
    scene.spawn(coin)


game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_global("score", 0)
game.set_interface(
    """
<div style="position:absolute;left:12px;top:12px;padding:8px 10px;background:rgba(0,0,0,0.55);color:#fff;border-radius:8px;font-family:monospace;">
  <div>Score: {{score}}</div>
  <button data-button="spawn_bonus" style="margin-top:6px;">Spawn Bonus</button>
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

coin = Coin(uid="coin_1", x=320, y=224, active=True, sprite="coin")
scene.add_actor(coin)

coin_pet = Coin(uid="coin_pet", x=200, y=192, block_mask=10, parent="hero", active=True, sprite="coin")
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
