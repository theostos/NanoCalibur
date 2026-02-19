# NanoCalibur Blank Web Canvas Tutorial

This tutorial shows a full standalone flow:

1. Create a blank TypeScript web project.
2. Write a NanoCalibur DSL scene in Python.
3. Generate `src/nanocalibur_generated` with `build_web_scene.py`.
4. Start the browser app and run the scene.

## Prerequisites

- Python 3.10+
- Node.js + npm
- Local clone of this NanoCalibur repository

Check your environment:

```bash
python --version
node -v
npm -v
```

## 1. Create a Blank TypeScript Web Project

```bash
mkdir -p ~/nanocalibur-blank-demo/src
cd ~/nanocalibur-blank-demo
npm init -y
npm install --save-dev typescript vite
npx tsc --init
```

Update `package.json` scripts:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  }
}
```

Create `index.html`:

```html
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>NanoCalibur Blank Demo</title>
    <style>
      html, body { margin: 0; padding: 0; background: #0f172a; }
      #game { display: block; margin: 0 auto; }
    </style>
  </head>
  <body>
    <canvas id="game" width="960" height="640"></canvas>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

Create `src/main.ts`:

```ts
import { attachNanoCalibur } from './nanocalibur_generated';

const canvas = document.getElementById('game');
if (!(canvas instanceof HTMLCanvasElement)) {
  throw new Error('Canvas element #game not found.');
}

const host = attachNanoCalibur(canvas);

void host.start();
```

## 2. Create a DSL Scene File

Create `scene.py` in project root:

```python
from nanocalibur.dsl_markers import (
    Actor,
    Camera,
    Game,
    KeyboardCondition,
    Role,
    RoleKind,
    Scene,
)


class Player(Actor):
    speed: int


def move_right(player: Player["hero"]):
    player.x = player.x + player.speed


game = Game()
scene = Scene(gravity=False)
game.set_scene(scene)
game.add_role(Role(id="human_1", required=True, kind=RoleKind.HUMAN))

scene.add_actor(Player(uid="hero", x=100, y=100, speed=3))
scene.add_rule(KeyboardCondition.on_press("d", id="human_1"), move_right)
scene.set_camera(Camera.follow("hero"))
```

Note: interface HTML is not injected by default. Add it explicitly only when needed:

```python
scene.set_interface("<div>Score: {{score}}</div>")
```

## 3. Generate NanoCalibur Output

Run from your project directory:

```bash
python /path/to/NanoCalibur/nanocalibur/build_web_scene.py ./scene.py --project .
```

This writes:

- `src/nanocalibur_generated/game_spec.json`
- `src/nanocalibur_generated/game_ir.json`
- `src/nanocalibur_generated/game_logic.ts`
- `src/nanocalibur_generated/interpreter.ts`
- `src/nanocalibur_generated/canvas_host.ts`
- `src/nanocalibur_generated/canvas/*.ts`
- `src/nanocalibur_generated/bridge.ts`
- `src/nanocalibur_generated/index.ts`

## 4. Run

```bash
npm run dev
```

Open the URL printed by Vite (usually `http://localhost:5173`).

## Optional Build Check

```bash
npm run build
```

If it succeeds, your generated NanoCalibur integration compiles correctly.
