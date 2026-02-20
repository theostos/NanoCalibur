# Multi-file game entrypoint.
# Build with:
#   python nanocalibur/build_game.py examples/scene.py --project ./nanocalibur-demo
# This file intentionally only imports local modules. build_game follows these
# imports, concatenates the sources, and compiles one project spec/runtime bundle.

from .scene_shared import game, scene
from .scene_roles import *
from .scene_entities import *
from .scene_controls import *
from .scene_rules import *
from .scene_assets import *
from .scene_world import *
