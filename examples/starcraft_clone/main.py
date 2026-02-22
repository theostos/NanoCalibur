# Multi-file RTS sandbox entrypoint.
# Build with:
#   nanocalibur-build-game examples/starcraft_clone/main.py --project ./nanocalibur-demo

from .shared import game, scene
from .roles import *
from .data import *
from .assets import *
from .world import *
from .controls import *
