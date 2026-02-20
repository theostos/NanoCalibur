from nanocalibur.dsl_markers import Actor, CodeBlock, Sprite

from .shared import scene


CodeBlock.begin("actors_and_spawn")
"""Actor schemas and initial actor instances shared by all rule modules."""


class Player(Actor):
    speed: int


class Coin(Actor):
    pass


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

CodeBlock.end("actors_and_spawn")
