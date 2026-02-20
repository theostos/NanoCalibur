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


class Local:
    """Client-owned role field marker.

    ``Local[...]`` fields are local-only and not synchronized to server state.
    They are intended for interface/client logic.
    """

    def __class_getitem__(cls, item):
        return cls


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
    parent: str | None
    sprite: str | None

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
        parent: "str | type[Actor] | None" = None,
        sprite: "str | type[Sprite] | None" = None,
        **_fields: Any,
    ) -> None:
        """Describe an actor instance payload for scene/game registration."""
        return None

    def play(self, _clip: str):
        """Request playback of a named animation clip on this actor."""
        return None

    def destroy(self) -> None:
        """Request destruction/despawn of this actor."""
        return None

    def attached_to(self, _parent: "str | Actor") -> None:
        """Attach this actor to a parent actor (or parent uid)."""
        return None

    def detached(self) -> None:
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
    ) -> None:
        """Declare scene-level runtime options."""
        return None

    def add_actor(self, _actor: Actor) -> None:
        """Declare an initial actor instance inside this scene."""
        return None

    def add_rule(self, _condition: Any, _action: Callable[..., Any]) -> None:
        """Register a rule mapping condition to action inside this scene."""
        return None

    def set_map(self, _map: Any) -> None:
        """Configure the tile map for this scene."""
        return None

    def add_camera(self, _camera: "Camera") -> None:
        """Attach a camera instance to this scene."""
        return None

    def set_interface(
        self,
        _html_or_interface: "str | Interface",
        _role: "str | Role | type[Role] | None" = None,
    ) -> None:
        """Configure an HTML overlay for one role.

        Accepted forms:
        - ``scene.set_interface("<div>...</div>")``
        - ``scene.set_interface("<div>...</div>", Role["human_1"])``
        - ``scene.set_interface(Interface("ui/hud.html", Role["human_1"]))``
        """
        return None

    def enable_gravity(self) -> None:
        """Enable gravity in the current scene."""
        return None

    def disable_gravity(self) -> None:
        """Disable gravity in the current scene."""
        return None

    def spawn(self, _actor: Actor) -> None:
        """Spawn a new actor instance inside the current scene."""
        return None

    def next_turn(self) -> None:
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

    def __class_getitem__(cls, item):
        """Allow ``Sprite[...]`` selector syntax."""
        return cls

    def __init__(
        self,
        *,
        name: str | None = None,
        uid: str | None = None,
        actor_type: "type[Actor] | None" = None,
        bind: "str | type[Actor] | None" = None,
        resource: "str | Resource | type[Resource]",
        frame_width: int,
        frame_height: int,
        clips: dict[str, Any],
        default_clip: str | None = None,
        symbol: str | None = None,
        description: str | None = None,
        row: int = 0,
        scale: float = 1.0,
        flip_x: bool = True,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> None:
        """Build a sprite declaration payload for the compiler."""
        return None


class Resource:
    """Resource declaration object consumed by :meth:`Game.add_resource`."""

    def __class_getitem__(cls, item):
        """Allow ``Resource[...]`` selector syntax."""
        return cls

    def __init__(self, _name: str, _path: str) -> None:
        return None


class Interface:
    """Interface declaration used by :meth:`Scene.set_interface`.

    By default the first argument is treated as a file path resolved from the
    source file directory. Set ``from_file=False`` to pass inline HTML directly.
    """

    def __init__(
        self,
        _source: str,
        _role: "str | type[Role] | None" = None,
        *,
        from_file: bool = True,
    ) -> None:
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
    ) -> None:
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
    kind: RoleKind | str

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
    ) -> None:
        return None


class HumanRole(Role):
    """Built-in non-editable human role schema with client-local key bindings."""

    keybinds: Local[dict[str, str]]


class Game:
    """Top-level DSL game container."""

    def add_global(self, _name_or_global: Any, _value: Any = None) -> None:
        """Declare a global variable.

        Accepted forms:
        - ``game.add_global("score", 0)``
        - ``game.add_global(GlobalVariable(int, "score", 0))``
        """
        return None

    def add_actor(self, _actor: Actor) -> None:
        """Legacy shortcut for scene-level actor declaration."""
        return None

    def add_rule(self, _condition: Any, _action: Callable[..., Any]) -> None:
        """Legacy shortcut for scene-level rule declaration."""
        return None

    def set_map(self, _map: Any) -> None:
        """Legacy shortcut for scene-level map configuration."""
        return None

    def set_scene(self, _scene: Scene) -> None:
        """Configure scene runtime settings."""
        return None

    def set_multiplayer(self, _multiplayer: Multiplayer) -> None:
        """Configure multiplayer loop and pacing defaults."""
        return None

    def add_role(self, _role: Role) -> None:
        """Declare a multiplayer role that can join sessions."""
        return None

    def add_resource(
        self,
        _resource_or_name: "Resource | str",
        _path: str | None = None,
    ) -> None:
        """Declare an image resource."""
        return None

    def add_sprite(self, _sprite: "Sprite") -> None:
        """Declare sprite animation bindings."""
        return None


class CodeBlock:
    """Top-level structural block marker for DSL authoring."""

    @staticmethod
    def begin(_id: str) -> None:
        """Start a code block identified by ``_id``.

        Put a docstring string literal immediately after this call to describe the block.
        """
        return None

    @staticmethod
    def end(_id: str | None = None) -> None:
        """Close the current code block."""
        return None


class AbstractCodeBlock(CodeBlock):
    """Template block marker that requires explicit ``instantiate(...)`` calls."""

    def __getattr__(self, _name: str) -> Any:
        """Expose template parameters through attribute placeholders.

        This keeps editors/type-checkers happy for patterns like
        ``template.role`` / ``template.hero`` inside abstract blocks.
        """
        return None

    @staticmethod
    def begin(_id: str, **_params: Any) -> "AbstractCodeBlock":
        """Start an abstract code block template.

        Supported keywords:
        - parameter declarations such as ``id=str``, ``hero_name=str``
        - optional ``params={...}`` dict declaration form

        Put a docstring string literal immediately after this call to describe the block.
        """
        return AbstractCodeBlock()

    @staticmethod
    def end(_id: str | None = None) -> None:
        """Close the current abstract code block template."""
        return None

    @staticmethod
    def instantiate(_id: str | None = None, **_values: Any) -> None:
        """Instantiate an abstract block by id with constant values."""
        return None


class KeyboardCondition:
    """Keyboard input condition helpers."""

    @staticmethod
    def begin_press(
        _key: str | list[str],
        _role: "str | type[Role] | None" = None,
        *,
        id: str | None = None,
    ) -> None:
        """Trigger when a key is pressed this frame.

        Prefer ``Role["..."]`` as the role selector. ``id="..."`` is accepted
        for compatibility with existing code.
        """
        return None

    @staticmethod
    def on_press(
        _key: str | list[str],
        _role: "str | type[Role] | None" = None,
        *,
        id: str | None = None,
    ) -> None:
        """Trigger while a key is held.

        Prefer ``Role["..."]`` as the role selector. ``id="..."`` is accepted
        for compatibility with existing code.
        """
        return None

    @staticmethod
    def end_press(
        _key: str | list[str],
        _role: "str | type[Role] | None" = None,
        *,
        id: str | None = None,
    ) -> None:
        """Trigger when a key is released this frame.

        Prefer ``Role["..."]`` as the role selector. ``id="..."`` is accepted
        for compatibility with existing code.
        """
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

    def __init__(self, _type: Any, _name: str, _value: Any) -> None:
        return None


class MouseCondition:
    """Mouse input condition helpers."""

    @staticmethod
    def begin_click(
        _button: "str | type[Role]" = "left",
        _role: "str | type[Role] | None" = None,
        *,
        id: str | None = None,
    ) -> None:
        """Trigger when a mouse button is pressed this frame.

        Prefer ``Role["..."]`` as the role selector. ``id="..."`` is accepted
        for compatibility with existing code.
        """
        return None

    @staticmethod
    def on_click(
        _button: "str | type[Role]" = "left",
        _role: "str | type[Role] | None" = None,
        *,
        id: str | None = None,
    ) -> None:
        """Trigger while a mouse button is held.

        Prefer ``Role["..."]`` as the role selector. ``id="..."`` is accepted
        for compatibility with existing code.
        """
        return None

    @staticmethod
    def end_click(
        _button: "str | type[Role]" = "left",
        _role: "str | type[Role] | None" = None,
        *,
        id: str | None = None,
    ) -> None:
        """Trigger when a mouse button is released this frame.

        Prefer ``Role["..."]`` as the role selector. ``id="..."`` is accepted
        for compatibility with existing code.
        """
        return None


class Camera:
    """Camera declaration and runtime control helpers."""

    name: str
    role_id: str
    x: float
    y: float
    width: int | None
    height: int | None
    target_uid: str | None

    def __class_getitem__(cls, item: Any):
        """Allow ``Camera[\"camera_name\"]`` syntax in type annotations."""
        return cls

    def __init__(
        self,
        _name: str,
        _role: "str | type[Role]",
        *,
        x: float = 0.0,
        y: float = 0.0,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        """Declare a named camera scoped to one role."""
        return None

    def follow(self, _uid: str) -> None:
        """Attach the camera to follow an actor uid."""
        return None

    def detach(self) -> None:
        """Detach camera from current follow target."""
        return None

    def translate(self, _dx: float, _dy: float) -> None:
        """Translate camera position (or follow offset if attached)."""
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
    ) -> None:
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
    ) -> None:
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
        sprite: "str | type[Sprite] | None" = None,
    ) -> None:
        return None


def OnOverlap(_left: Any, _right: Any) -> None:
    """Condition helper for overlap checks between two selectors."""
    return None


def OnContact(_left: Any, _right: Any) -> None:
    """Condition helper for blocking-contact checks between two selectors."""
    return None


def OnLogicalCondition(_predicate: Callable[..., Any], _selector: Any) -> None:
    """Condition helper applying a predicate to selected actors."""
    return None


def OnToolCall(
    _name: str,
    _role: "str | type[Role] | None" = None,
    *,
    id: str | None = None,
) -> None:
    """Condition helper exposing an action as an external LLM-callable tool.

    The tool description is read from the bound action function docstring.
    Prefer ``Role["..."]`` as the role selector. ``id="..."`` is accepted
    for compatibility with existing code.
    """
    return None


def OnButton(_name: str) -> None:
    """Condition helper for UI button clicks.

    Usage:
        ``@unsafe_condition(OnButton("spawn_bonus"))``
    """
    return None


F = TypeVar("F", bound=Callable[..., Any])


def safe_condition(_condition_expr: Any) -> Callable[[F], F]:
    """Attach a server-evaluated condition marker to an action function.

    Intended for conditions resolved from server authoritative state
    (for example overlap/contact/logical conditions).
    """

    def _decorate(fn: F) -> F:
        return fn

    return _decorate


def unsafe_condition(_condition_expr: Any) -> Callable[[F], F]:
    """Attach a client-input-driven condition marker to an action function.

    Intended for conditions that originate from client-emitted events
    (for example keyboard/mouse/tool/button conditions).
    """

    def _decorate(fn: F) -> F:
        return fn

    return _decorate


def callable(fn: F) -> F:
    """Mark a helper function callable from actions/predicates expressions."""
    return fn


def local(_value: Any = None) -> Any:
    """Declare a default value for ``Local[...]`` role fields."""
    return _value


__all__ = [
    "AbstractCodeBlock",
    "Actor",
    "Camera",
    "CodeBlock",
    "Color",
    "Game",
    "Global",
    "GlobalVariable",
    "HumanRole",
    "Interface",
    "KeyboardCondition",
    "Local",
    "MouseCondition",
    "Multiplayer",
    "OnButton",
    "OnContact",
    "OnLogicalCondition",
    "OnOverlap",
    "OnToolCall",
    "Random",
    "Resource",
    "Role",
    "RoleKind",
    "Scene",
    "Sprite",
    "Tick",
    "Tile",
    "TileMap",
    "callable",
    "local",
    "safe_condition",
    "unsafe_condition",
]
