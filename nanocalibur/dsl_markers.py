"""Public marker classes for authoring NanoCalibur DSL scenes.

These symbols are parsed from source with ``ast`` and are never executed at runtime.
"""

from enum import Enum
from typing import Any, Callable, TypeVar

try:
    from enum import StrEnum  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - Python < 3.11 fallback
    class StrEnum(str, Enum):
        pass


class Global:
    """Binding marker used in action signatures for global variables.

    Example:
        ``score: Global["score"]``
    """

    def __class_getitem__(cls, item):
        """Allow ``Global[...]`` syntax in type annotations.

        Accepted forms:
        - ``Global["score"]``
        - ``Global["score", int]``
        """
        return cls

    def __getattr__(self, _name: str) -> Any:
        """Expose dynamic attribute access for static-analysis friendliness."""
        return None

    def __add__(self, _other: object) -> Any:
        return None

    def __radd__(self, _other: object) -> Any:
        return None

    def __sub__(self, _other: object) -> Any:
        return None

    def __rsub__(self, _other: object) -> Any:
        return None

    def __mul__(self, _other: object) -> Any:
        return None

    def __rmul__(self, _other: object) -> Any:
        return None

    def __truediv__(self, _other: object) -> Any:
        return None

    def __rtruediv__(self, _other: object) -> Any:
        return None

    def __mod__(self, _other: object) -> Any:
        return None

    def __rmod__(self, _other: object) -> Any:
        return None


class Actor:
    """Actor base class and binding marker used in DSL.

    Built-in engine-managed fields:
    - ``uid`` stable actor identifier
    - ``x``, ``y`` world position
    - ``vx``, ``vy`` linear velocity (units/second)
    - ``w``, ``h`` collider/render size
    - ``active`` lifecycle flag
    - ``block_mask`` tile-blocking priority (``None`` disables tile blocking)

    Binding examples:
    - ``player: Actor["Player"]``
    - ``actor: Actor[-1]``
    """

    uid: str
    x: float
    y: float
    vx: float
    vy: float
    w: float
    h: float
    active: bool
    block_mask: int | None
    z: float
    parent: str
    sprite: str

    def __class_getitem__(cls, item):
        """Allow ``Actor[...]`` syntax in type annotations."""
        return cls

    def __init__(
        self,
        uid: str | None = None,
        *,
        x: float = 0.0,
        y: float = 0.0,
        vx: float = 0.0,
        vy: float = 0.0,
        w: float | None = None,
        h: float | None = None,
        z: float = 0.0,
        active: bool = True,
        block_mask: int | None = None,
        parent: str | None = None,
        sprite: str | None = None,
        **_fields: Any,
    ) -> None:
        """Describe an actor instance payload for scene/game registration."""
        return None

    def play(self, _clip: str):
        """Request playback of a named animation clip on this actor."""
        return None

    def destroy(self):
        """Request destruction/despawn of this actor."""
        return None

    def attached_to(self, _parent: "Actor | str"):
        """Attach this actor to a parent actor (or parent uid)."""
        return None

    def detached(self):
        """Detach this actor from any parent."""
        return None


class Scene:
    """Scene descriptor and scene-level game content container.

    ``Scene(...)`` is used in ``game.set_scene(...)``.
    ``scene: Scene`` is used in action bindings.

    Read-only runtime field:
    - ``elapsed`` number of ticks since game start.
    """

    elapsed: int

    def __class_getitem__(cls, item):
        """Allow ``Scene[...]`` syntax if needed for compatibility."""
        return cls

    def __init__(
        self,
        *,
        gravity: bool = False,
        keyboard_aliases: dict[str, str | list[str]] | None = None,
    ):
        """Declare scene-level runtime options."""
        return None

    def add_actor(self, _actor: Actor):
        """Declare an initial actor instance inside this scene."""
        return None

    def add_rule(self, _condition, _action: Callable[..., Any]):
        """Register a rule mapping condition to action inside this scene."""
        return None

    def set_map(self, _map):
        """Configure the tile map for this scene."""
        return None

    def set_camera(self, _camera):
        """Configure camera behavior for this scene."""
        return None

    def set_interface(self, _html: str):
        """Configure an HTML overlay rendered above the canvas for this scene."""
        return None

    def enable_gravity(self):
        """Enable gravity in the current scene."""
        return None

    def disable_gravity(self):
        """Disable gravity in the current scene."""
        return None

    def spawn(self, _actor: Actor):
        """Spawn a new actor instance inside the current scene."""
        return None

    def next_turn(self):
        """Advance the session turn in turn-based or hybrid loop modes."""
        return None


class Tick:
    """Action parameter marker for per-frame wait tokens.

    Example:
        ``def action(player: Player, tick: Tick):``
        ``    yield tick``
    """


class Sprite:
    """Sprite declaration object consumed by :meth:`Game.add_sprite`.

    Binding can be provided through one of:
    - ``name="hero"`` (attach by actor ``sprite`` field)
    - ``uid="hero"``
    - ``actor_type=Player``
    - ``bind=Player["hero"]``
    - ``bind=Player``
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        uid=None,
        actor_type=None,
        bind=None,
        resource: str,
        frame_width: int,
        frame_height: int,
        clips,
        default_clip: str | None = None,
        symbol: str | None = None,
        description: str | None = None,
        row: int = 0,
        scale: float = 1.0,
        flip_x: bool = True,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ):
        """Build a sprite declaration payload for the compiler."""
        return None


class Multiplayer:
    """Multiplayer runtime defaults and loop controls."""

    def __init__(
        self,
        *,
        default_loop: str = "real_time",
        allowed_loops: list[str] | None = None,
        default_visibility: str = "shared",
        tick_rate: int = 20,
        turn_timeout_ms: int = 15_000,
        hybrid_window_ms: int = 500,
        game_time_scale: float = 1.0,
        max_catchup_steps: int = 1,
    ):
        return None


class RoleKind(StrEnum):
    """Role kind for multiplayer slot assignment."""

    HUMAN = "human"
    AI = "ai"
    HYBRID = "hybrid"


class Role:
    """Role declaration for multiplayer sessions."""

    id: str
    required: bool
    kind: str

    def __class_getitem__(cls, item):
        """Allow ``Role[...]`` syntax in type annotations."""
        return cls

    def __init__(
        self,
        *,
        id: str,
        required: bool = True,
        kind: RoleKind | str = RoleKind.HYBRID,
        **_fields: Any,
    ):
        return None


class Game:
    """Top-level DSL game container."""

    def add_global(self, _name_or_global, _value: Any = None):
        """Declare a global variable.

        Accepted forms:
        - ``game.add_global("score", 0)``
        - ``game.add_global(GlobalVariable(int, "score", 0))``
        """
        return None

    def add_actor(self, _actor: Actor):
        """Legacy shortcut for scene-level actor declaration."""
        return None

    def add_rule(self, _condition, _action: Callable[..., Any]):
        """Legacy shortcut for scene-level rule declaration."""
        return None

    def set_map(self, _map):
        """Legacy shortcut for scene-level map configuration."""
        return None

    def set_camera(self, _camera):
        """Legacy shortcut for scene-level camera configuration."""
        return None

    def set_scene(self, _scene: Scene):
        """Configure scene runtime settings."""
        return None

    def set_multiplayer(self, _multiplayer: Multiplayer):
        """Configure multiplayer loop and pacing defaults."""
        return None

    def add_role(self, _role: Role):
        """Declare a multiplayer role that can join sessions."""
        return None

    def add_resource(self, _name: str, _path: str):
        """Declare an image resource by name and path."""
        return None

    def add_sprite(self, _sprite: "Sprite"):
        """Declare sprite animation bindings."""
        return None


class KeyboardCondition:
    """Keyboard input condition helpers."""

    @staticmethod
    def begin_press(_key: str | list[str], id: str):
        """Trigger when a key is pressed this frame."""
        return None

    @staticmethod
    def on_press(_key: str | list[str], id: str):
        """Trigger while a key is held."""
        return None

    @staticmethod
    def end_press(_key: str | list[str], id: str):
        """Trigger when a key is released this frame."""
        return None


class Random:
    """Deterministic-friendly random helpers for action expressions."""

    @staticmethod
    def int(_min_inclusive: int, _max_inclusive: int) -> int:
        return 0

    @staticmethod
    def bool() -> bool:
        return False

    @staticmethod
    def string(_length: int, _alphabet: str | None = None) -> str:
        return ""

    @staticmethod
    def float(_min_value: float, _max_value: float) -> float:
        return 0.0

    @staticmethod
    def uniform(_min_value: float, _max_value: float) -> float:
        return 0.0

    @staticmethod
    def normal(_mean: float, _stddev: float) -> float:
        return 0.0


class GlobalVariable:
    """Named global declaration payload for ``game.add_global``."""

    def __init__(self, _type, _name: str, _value: Any):
        return None


class MouseCondition:
    """Mouse input condition helpers."""

    @staticmethod
    def begin_click(_button: str = "left", *, id: str):
        """Trigger when a mouse button is pressed this frame."""
        return None

    @staticmethod
    def on_click(_button: str = "left", *, id: str):
        """Trigger while a mouse button is held."""
        return None

    @staticmethod
    def end_click(_button: str = "left", *, id: str):
        """Trigger when a mouse button is released this frame."""
        return None


class Camera:
    """Camera configuration helpers."""

    @staticmethod
    def fixed(_x: int, _y: int):
        """Lock camera to fixed world coordinates."""
        return None

    @staticmethod
    def follow(_uid: str):
        """Follow an actor by uid."""
        return None


class TileMap:
    """Tile map descriptor used in ``game.set_map``.

    ``grid`` and ``tiles`` are required.
    In ``grid``, ``0`` means empty tile, and ``> 0`` indexes the ``tiles`` palette.
    ``grid`` can be either ``list[list[int]]`` or a relative/absolute path to a text
    file containing a matrix of integers.
    """

    def __init__(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
        tile_size: int,
        grid: list[list[int]] | str,
        tiles: dict[int, "Tile"],
    ):
        """Declare map size, tile size, and tile palette grid."""
        return None


class Color:
    """Tile color definition.

    ``symbol`` and ``description`` are used by symbolic rendering.
    """

    def __init__(
        self,
        r: int,
        g: int,
        b: int,
        *,
        symbol: str | None = None,
        description: str | None = None,
    ):
        return None


class Tile:
    """Tile definition used in ``TileMap(..., tiles={...})``.

    Use either ``color=Color(...)`` or ``sprite="sprite_name"``.
    ``block_mask`` controls tile-vs-actor blocking (``None`` means non-blocking).
    """

    def __init__(
        self,
        *,
        block_mask: int | None = None,
        color: Color | None = None,
        sprite: str | None = None,
    ):
        return None


def OnOverlap(_left, _right):
    """Condition helper for overlap checks between two selectors."""
    return None


def OnContact(_left, _right):
    """Condition helper for blocking-contact checks between two selectors."""
    return None


def OnLogicalCondition(_predicate, _selector):
    """Condition helper applying a predicate to selected actors."""
    return None


def OnToolCall(_name: str, _tool_docstring: str, id: str):
    """Condition helper exposing an action as an external LLM-callable tool."""
    return None


def OnButton(_name: str):
    """Condition helper for UI button clicks.

    Usage:
        ``@condition(OnButton("spawn_bonus"))``
    """
    return None


F = TypeVar("F", bound=Callable[..., Any])


def condition(_condition_expr) -> Callable[[F], F]:
    """Attach a rule condition directly to an action function.

    Example:
        ``@condition(KeyboardCondition.begin_press("g", id="human_1"))``
    """

    def _decorate(fn: F) -> F:
        return fn

    return _decorate


def callable(fn: F) -> F:
    """Mark a helper function callable from actions/predicates expressions."""
    return fn
