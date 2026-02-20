# Multi-file game entrypoint.
# Build with:
#   nanocalibur-build-game examples/scene/main.py --project ./nanocalibur-demo
# This file intentionally only imports local modules. build_game follows these
# imports, concatenates the sources, and compiles one project spec/runtime bundle.

from .shared import game, scene
from .roles import *
from .entities import *
from .controls import *
from .rules import *
from .assets import *
from .world import *
