class Global:
    def __class_getitem__(cls, item):
        return cls


class Actor:
    def __class_getitem__(cls, item):
        return cls


class ActorModel:
    pass


class Game:
    def add_global(self, *_args, **_kwargs):
        return None

    def add_actor(self, *_args, **_kwargs):
        return None

    def add_rule(self, *_args, **_kwargs):
        return None

    def addRules(self, *_args, **_kwargs):
        return None

    def set_map(self, *_args, **_kwargs):
        return None

    def set_camera(self, *_args, **_kwargs):
        return None


class KeyboardCondition:
    @staticmethod
    def begin_press(_key: str):
        return None

    @staticmethod
    def on_press(_key: str):
        return None

    @staticmethod
    def end_press(_key: str):
        return None

    @staticmethod
    def is_pressed(_key: str):
        return None

    @staticmethod
    def pressed(_key: str):
        return None

    @staticmethod
    def just_pressed(_key: str):
        return None

    @staticmethod
    def just_released(_key: str):
        return None


class MouseCondition:
    @staticmethod
    def begin_click(_button: str = "left"):
        return None

    @staticmethod
    def on_click(_button: str = "left"):
        return None

    @staticmethod
    def end_click(_button: str = "left"):
        return None

    @staticmethod
    def clicked(_button: str = "left"):
        return None

    @staticmethod
    def is_clicked(_button: str = "left"):
        return None

    @staticmethod
    def just_clicked(_button: str = "left"):
        return None


class Camera:
    @staticmethod
    def fixed(_x: int, _y: int):
        return None

    @staticmethod
    def follow(_uid: str):
        return None


class TileMap:
    def __init__(self, *, width: int, height: int, tile_size: int, solid):
        self.width = width
        self.height = height
        self.tile_size = tile_size
        self.solid = solid


def Any(_actor_type):
    return None


def WithUID(_actor_type, _uid: str):
    return None


def CollisionRelated(_left, _right):
    return None


def LogicalRelated(_predicate, _selector):
    return None
