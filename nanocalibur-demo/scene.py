from nanocalibur.dsl_markers import (
    ActorModel,
    Camera,
    CollisionRelated,
    Game,
    Global,
    KeyboardCondition,
    TileMap,
    WithUID,
)


class Player(ActorModel):
    x: int
    y: int
    w: int
    h: int
    speed: int


class Coin(ActorModel):
    x: int
    y: int
    w: int
    h: int
    active: bool


def move_right(player: Player["hero"]):
    player.x = player.x + player.speed


def move_left(player: Player["hero"]):
    player.x = player.x - player.speed


def move_up(player: Player["hero"]):
    player.y = player.y - player.speed


def move_down(player: Player["hero"]):
    player.y = player.y + player.speed


def collect_coin(
    hero: Player["hero"],
    coin: Coin["coin_1"],
    score: Global["score"],
):
    if coin.active:
        coin.active = False
        score = score + 1


game = Game()
game.add_global("score", 0)
game.add_actor(Player, "hero", x=100, y=100, w=32, h=32, speed=3)
game.add_actor(Coin, "coin_1", x=360, y=220, w=24, h=24, active=True)

game.add_rule(KeyboardCondition.on_press("ArrowRight"), move_right)
game.add_rule(KeyboardCondition.on_press("ArrowLeft"), move_left)
game.add_rule(KeyboardCondition.on_press("ArrowUp"), move_up)
game.add_rule(KeyboardCondition.on_press("ArrowDown"), move_down)

game.add_rule(
    CollisionRelated(WithUID(Player, "hero"), WithUID(Coin, "coin_1")),
    collect_coin,
)
game.set_camera(Camera.follow("hero"))
game.set_map(TileMap(width=30, height=20, tile_size=32, solid=[(0, 0), (1, 0), (2, 0)]))
