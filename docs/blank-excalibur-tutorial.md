# NanoCalibur Blank Excalibur Project Tutorial

This tutorial shows a full end-to-end flow:

1. Create a blank Excalibur TypeScript project.
2. Write a DSL scene in Python.
3. Generate NanoCalibur output with `examples/build_web_scene.py`.
4. Run the game in your browser.

## Prerequisites

- Python 3.10+
- Node.js + npm
- This NanoCalibur repository available locally

Check your environment:

```bash
python --version
node -v
npm -v
```

If Node.js is missing, install via `nvm`:

```bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
# restart shell
nvm install --lts
nvm use --lts
node -v
npm -v
```

## 1. Create a Blank Excalibur Project

```bash
mkdir -p ~/nanocalibur-blank-demo/src
cd ~/nanocalibur-blank-demo
```

Create `package.json`:

```json
{
  "name": "nanocalibur-blank-demo",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "webpack serve --mode development --open",
    "build": "webpack --mode development"
  },
  "dependencies": {
    "excalibur": "0.30.2"
  },
  "devDependencies": {
    "copy-webpack-plugin": "^13.0.1",
    "ts-loader": "9.5.1",
    "typescript": "5.7.2",
    "webpack": "5.97.1",
    "webpack-cli": "6.0.1",
    "webpack-dev-server": "5.2.0"
  }
}
```

Create `tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "es2019",
    "module": "commonjs",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "exclude": ["dist"]
}
```

Create `webpack.config.js`:

```js
const path = require('path');
const CopyPlugin = require('copy-webpack-plugin');

module.exports = {
  entry: './src/main.ts',
  mode: 'development',
  devtool: 'source-map',
  devServer: {
    port: 9000,
    devMiddleware: {
      writeToDisk: true
    },
    static: {
      directory: path.resolve(__dirname)
    }
  },
  plugins: [
    new CopyPlugin({
      patterns: ['index.html']
    })
  ],
  resolve: {
    extensions: ['.ts', '.js']
  },
  output: {
    filename: '[name].js',
    sourceMapFilename: '[file].map',
    path: path.resolve(__dirname, 'dist')
  },
  module: {
    rules: [
      {
        test: /\.ts?$/,
        use: 'ts-loader',
        exclude: /node_modules/
      }
    ]
  }
};
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
      html, body { margin: 0; padding: 0; background: #0f172a; color: #e2e8f0; }
      #game { display: block; margin: 0 auto; }
    </style>
  </head>
  <body>
    <canvas id="game"></canvas>
    <script src="./main.js"></script>
  </body>
</html>
```

Create `src/main.ts`:

```ts
import * as ex from 'excalibur';
import { attachNanoCalibur } from './nanocalibur_generated';

const game = new ex.Engine({
  width: 800,
  height: 600,
  canvasElementId: 'game'
});

const scene = new ex.Scene();
game.add('main', scene);
game.goToScene('main');

const bridge = attachNanoCalibur(scene);
game.on('postupdate', () => {
  bridge.tick();
});

game.start();
```

## 2. Create a DSL Scene File

Create `scene.py` in project root:

```python
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


def collect_coin(hero: Player["hero"], coin: Coin["coin_1"], score: Global["score"]):
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
game.add_rule(CollisionRelated(WithUID(Player, "hero"), WithUID(Coin, "coin_1")), collect_coin)
game.set_camera(Camera.follow("hero"))
game.set_map(TileMap(width=30, height=20, tile_size=32, solid=[(0, 0), (1, 0), (2, 0)]))
```

## 3. Generate NanoCalibur Output

Run from the blank project directory:

```bash
python /home/theo/Documents/github/NanoCalibur/examples/build_web_scene.py ./scene.py --project .
```

This writes generated files to:

`src/nanocalibur_generated/`

Key generated files:

- `src/nanocalibur_generated/game_spec.json`
- `src/nanocalibur_generated/game_logic.ts`
- `src/nanocalibur_generated/interpreter.ts`
- `src/nanocalibur_generated/bridge.ts`
- `src/nanocalibur_generated/index.ts`

## 4. Install Dependencies and Run

```bash
npm install
npm run dev
```

Open:

`http://localhost:9000`

You can move with arrow keys and trigger collision logic with the coin.

## Optional Build Check

```bash
npm run build
```

If it succeeds, your generated NanoCalibur integration compiles correctly in TypeScript.
