# StarCraft clone example (multi-file).
# Build with:
#   nanocalibur-build-game examples/starcraft_clone/main.py --project ./nanocalibur-demo

from .shared import game, scene
from .constants import *
from .schemas import *
from .roles import *
from .assets import *
from .world import *
from .economy import *
from .production import *
from .controls import *
from .combat import *
from .visibility import *
