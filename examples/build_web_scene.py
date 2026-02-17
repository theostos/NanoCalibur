#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nanocalibur.exporter import export_project


GENERATED_DIR_NAME = "nanocalibur_generated"


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _bridge_ts_template() -> str:
    return textwrap.dedent(
        """
        import * as ex from 'excalibur';
        import { NanoCaliburInterpreter, NanoCaliburFrameInput } from './interpreter';

        interface ActorState extends Record<string, any> {
          uid: string;
          type: string;
          x?: number;
          y?: number;
          w?: number;
          h?: number;
          active?: boolean;
        }

        interface MapSpec {
          width: number;
          height: number;
          tile_size: number;
          solid_tiles: Array<[number, number]>;
        }

        interface PhasePayload {
          begin: string[];
          on: string[];
          end: string[];
        }

        interface CollisionPair {
          aUid: string;
          bUid: string;
        }

        function diffSets(current: Set<string>, previous: Set<string>): PhasePayload {
          const begin: string[] = [];
          const on: string[] = [];
          const end: string[] = [];

          for (const item of current) {
            on.push(item);
            if (!previous.has(item)) {
              begin.push(item);
            }
          }
          for (const item of previous) {
            if (!current.has(item)) {
              end.push(item);
            }
          }

          return { begin, on, end };
        }

        function getCollider(actor: ActorState): { left: number; right: number; top: number; bottom: number } | null {
          if (actor.active === false) {
            return null;
          }
          const w = Number(actor.w || 24);
          const h = Number(actor.h || 24);
          return {
            left: Number(actor.x || 0) - w / 2,
            right: Number(actor.x || 0) + w / 2,
            top: Number(actor.y || 0) - h / 2,
            bottom: Number(actor.y || 0) + h / 2,
          };
        }

        function overlaps(
          a: { left: number; right: number; top: number; bottom: number },
          b: { left: number; right: number; top: number; bottom: number },
        ): boolean {
          return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
        }

        function detectCollisions(actorStates: ActorState[]): CollisionPair[] {
          const out: CollisionPair[] = [];
          for (let i = 0; i < actorStates.length; i += 1) {
            for (let j = i + 1; j < actorStates.length; j += 1) {
              const a = actorStates[i];
              const b = actorStates[j];
              const boxA = getCollider(a);
              const boxB = getCollider(b);
              if (!boxA || !boxB) {
                continue;
              }
              if (overlaps(boxA, boxB)) {
                out.push({ aUid: a.uid, bUid: b.uid });
              }
            }
          }
          return out;
        }

        function colorForType(actorType: string): ex.Color {
          if (actorType === 'Player') return ex.Color.fromRGB(80, 180, 255);
          if (actorType === 'Enemy') return ex.Color.fromRGB(230, 90, 90);
          if (actorType === 'Coin') return ex.Color.fromRGB(255, 220, 80);
          return ex.Color.White;
        }

        export class NanoCaliburBridge {
          private readonly scene: ex.Scene;
          private readonly interpreter: NanoCaliburInterpreter;
          private readonly actorViews: Map<string, ex.Actor> = new Map();
          private readonly previousPositions: Map<string, { x: number; y: number }> = new Map();
          private readonly keyDown = new Set<string>();
          private prevKeyDown = new Set<string>();
          private readonly mouseDown = new Set<string>();
          private prevMouseDown = new Set<string>();
          private readonly mapSpec: MapSpec | null;

          constructor(scene: ex.Scene, interpreter: NanoCaliburInterpreter) {
            this.scene = scene;
            this.interpreter = interpreter;
            const state = this.interpreter.getState();
            this.mapSpec = (state.map as MapSpec | null) || null;

            this.installInputListeners();
            this.buildMapLayer();
            for (const actor of state.actors as ActorState[]) {
              this.ensureView(actor);
            }
          }

          getInterpreter(): NanoCaliburInterpreter {
            return this.interpreter;
          }

          tick(): void {
            const before = this.interpreter.getState();
            const beforeActors = before.actors as ActorState[];
            this.rememberPositions(beforeActors);

            const frame: NanoCaliburFrameInput = {
              keyboard: diffSets(this.keyDown, this.prevKeyDown),
              mouse: diffSets(this.mouseDown, this.prevMouseDown),
              collisions: detectCollisions(beforeActors),
            };

            this.prevKeyDown = new Set(this.keyDown);
            this.prevMouseDown = new Set(this.mouseDown);

            this.interpreter.tick(frame);
            const state = this.interpreter.getState();

            for (const actorState of state.actors as ActorState[]) {
              this.clampToWorld(actorState);
              this.resolveSolidCollision(actorState);

              const view = this.ensureView(actorState);
              view.pos.x = Number(actorState.x || 0);
              view.pos.y = Number(actorState.y || 0);
              view.color = colorForType(actorState.type);
              view.graphics.opacity = actorState.active === false ? 0.2 : 1;
            }

            this.applyCamera();
          }

          private installInputListeners(): void {
            window.addEventListener('keydown', (event: KeyboardEvent) => {
              this.keyDown.add(event.key);
            });
            window.addEventListener('keyup', (event: KeyboardEvent) => {
              this.keyDown.delete(event.key);
            });
            window.addEventListener('mousedown', (event: MouseEvent) => {
              this.mouseDown.add(this.mouseButtonName(event.button));
            });
            window.addEventListener('mouseup', (event: MouseEvent) => {
              this.mouseDown.delete(this.mouseButtonName(event.button));
            });
          }

          private mouseButtonName(buttonCode: number): string {
            if (buttonCode === 0) return 'left';
            if (buttonCode === 1) return 'middle';
            if (buttonCode === 2) return 'right';
            return `button_${buttonCode}`;
          }

          private ensureView(actorState: ActorState): ex.Actor {
            const existing = this.actorViews.get(actorState.uid);
            if (existing) {
              return existing;
            }

            const actor = new ex.Actor({
              x: Number(actorState.x || 0),
              y: Number(actorState.y || 0),
              width: Number(actorState.w || 24),
              height: Number(actorState.h || 24),
              color: colorForType(actorState.type),
              collisionType: ex.CollisionType.PreventCollision,
            });
            actor.z = 10;
            this.scene.add(actor);
            this.actorViews.set(actorState.uid, actor);
            return actor;
          }

          private buildMapLayer(): void {
            if (!this.mapSpec || !Array.isArray(this.mapSpec.solid_tiles)) {
              return;
            }

            for (const [tileX, tileY] of this.mapSpec.solid_tiles) {
              const tile = new ex.Actor({
                x: tileX * this.mapSpec.tile_size + this.mapSpec.tile_size / 2,
                y: tileY * this.mapSpec.tile_size + this.mapSpec.tile_size / 2,
                width: this.mapSpec.tile_size,
                height: this.mapSpec.tile_size,
                color: ex.Color.fromRGB(56, 64, 79),
                collisionType: ex.CollisionType.PreventCollision,
              });
              tile.z = 1;
              this.scene.add(tile);
            }
          }

          private rememberPositions(actors: ActorState[]): void {
            this.previousPositions.clear();
            for (const actor of actors) {
              this.previousPositions.set(actor.uid, {
                x: Number(actor.x || 0),
                y: Number(actor.y || 0),
              });
            }
          }

          private clampToWorld(actor: ActorState): void {
            if (!this.mapSpec) {
              return;
            }

            const width = Number(actor.w || 24);
            const height = Number(actor.h || 24);
            const worldWidth = this.mapSpec.width * this.mapSpec.tile_size;
            const worldHeight = this.mapSpec.height * this.mapSpec.tile_size;

            const minX = width / 2;
            const maxX = worldWidth - width / 2;
            const minY = height / 2;
            const maxY = worldHeight - height / 2;

            actor.x = Math.max(minX, Math.min(maxX, Number(actor.x || 0)));
            actor.y = Math.max(minY, Math.min(maxY, Number(actor.y || 0)));
          }

          private resolveSolidCollision(actor: ActorState): void {
            if (actor.active === false) {
              return;
            }
            const previous = this.previousPositions.get(actor.uid);
            if (!previous) {
              return;
            }
            if (!this.isTouchingSolid(actor)) {
              return;
            }

            actor.x = previous.x;
            actor.y = previous.y;
          }

          private isTouchingSolid(actor: ActorState): boolean {
            if (!this.mapSpec) {
              return false;
            }

            const w = Number(actor.w || 24);
            const h = Number(actor.h || 24);
            const x = Number(actor.x || 0);
            const y = Number(actor.y || 0);

            const corners: Array<[number, number]> = [
              [x - w / 2 + 1, y - h / 2 + 1],
              [x + w / 2 - 1, y - h / 2 + 1],
              [x - w / 2 + 1, y + h / 2 - 1],
              [x + w / 2 - 1, y + h / 2 - 1],
            ];

            return corners.some(([cx, cy]) => this.interpreter.isSolidAtWorld(cx, cy));
          }

          private applyCamera(): void {
            const camera = this.interpreter.getCameraState();
            if (!camera) {
              return;
            }
            if (camera.mode === 'follow' || camera.mode === 'fixed') {
              this.scene.camera.pos = ex.vec(Number(camera.x || 0), Number(camera.y || 0));
            }
          }
        }
        """
    ).strip() + "\n"


def _index_ts_template() -> str:
    return textwrap.dedent(
        """
        import * as ex from 'excalibur';
        import * as gameLogic from './game_logic';
        import { NanoCaliburInterpreter } from './interpreter';
        import { NanoCaliburBridge } from './bridge';

        type Callable = (...args: any[]) => any;

        declare const require: any;

        const spec = require('./game_spec.json') as Record<string, any>;

        function pickFunctions(names: string[]): Record<string, Callable> {
          const out: Record<string, Callable> = {};
          const moduleObj = gameLogic as Record<string, unknown>;

          for (const name of names) {
            const fn = moduleObj[name];
            if (typeof fn === 'function') {
              out[name] = fn as Callable;
            }
          }
          return out;
        }

        export function createNanoCaliburInterpreter(): NanoCaliburInterpreter {
          const actionNames = Array.isArray(spec.actions) ? (spec.actions as string[]) : [];
          const predicateNames = Array.isArray(spec.predicates)
            ? spec.predicates.map((item: any) => (typeof item === 'string' ? item : item.name))
            : [];

          const actions = pickFunctions(actionNames);
          const predicates = pickFunctions(predicateNames);
          return new NanoCaliburInterpreter(spec, actions, predicates);
        }

        export function attachNanoCalibur(scene: ex.Scene): NanoCaliburBridge {
          const interpreter = createNanoCaliburInterpreter();
          return new NanoCaliburBridge(scene, interpreter);
        }

        export { NanoCaliburBridge, NanoCaliburInterpreter };
        """
    ).strip() + "\n"


def _generated_readme_template() -> str:
    return textwrap.dedent(
        """
        # NanoCalibur Generated Excalibur Input

        This folder is generated by `examples/build_web_scene.py`.

        Included files:
        - `game_spec.json`
        - `game_ir.json`
        - `game_logic.ts`
        - `interpreter.ts`
        - `bridge.ts`
        - `index.ts`

        ## Usage in an Excalibur TypeScript project

        1. Place this folder in your project under `src/nanocalibur_generated`.

        2. In your Excalibur entry file (for example `src/main.ts`), add:

        ```ts
        import { attachNanoCalibur } from './nanocalibur_generated';

        const bridge = attachNanoCalibur(game.currentScene);
        game.on('postupdate', () => {
          bridge.tick();
        });
        ```

        3. Build and run your Excalibur app (`npm run dev` in `sample-tiled-webpack`).

        Notes:
        - The bridge renders simple colored actors by default.
        - You can replace visuals with sprite logic while keeping `bridge.tick()` unchanged.
        - Runtime logic is driven by the generated `game_spec.json` + `game_logic.ts` pair.
        """
    ).strip() + "\n"


def build_excalibur_input(scene_path: Path, output_dir: Path) -> Path:
    if not scene_path.exists():
        raise FileNotFoundError(f"Scene file not found: {scene_path}")

    source = scene_path.read_text(encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)

    export_project(source, str(output_dir))

    runtime_dir = ROOT / "nanocalibur" / "runtime"
    shutil.copy2(runtime_dir / "interpreter.ts", output_dir / "interpreter.ts")
    shutil.copy2(runtime_dir / "interpreter.js", output_dir / "interpreter.js")
    shutil.copy2(runtime_dir / "interpreter.mjs", output_dir / "interpreter.mjs")

    _write_text(output_dir / "bridge.ts", _bridge_ts_template())
    _write_text(output_dir / "index.ts", _index_ts_template())
    _write_text(output_dir / "README.generated.md", _generated_readme_template())

    return output_dir


def sync_into_excalibur_project(bundle_dir: Path, project_dir: Path) -> Path:
    src_dir = project_dir / "src"
    if not src_dir.exists():
        raise FileNotFoundError(
            f"Excalibur project src directory not found: {src_dir}"
        )

    target_dir = src_dir / GENERATED_DIR_NAME
    if bundle_dir.resolve() == target_dir.resolve():
        return target_dir
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(bundle_dir, target_dir)
    return target_dir


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compile a NanoCalibur Python scene and generate an Excalibur-consumable "
            "input bundle."
        )
    )
    parser.add_argument(
        "scene",
        help="Path to the Python DSL scene file to compile.",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "build" / GENERATED_DIR_NAME),
        help="Directory where the generated bundle will be written.",
    )
    parser.add_argument(
        "--project",
        default=None,
        help=(
            "Optional Excalibur project root directory. If provided, the generated "
            "bundle is copied to <project>/src/nanocalibur_generated."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    scene_path = Path(args.scene).resolve()
    output_dir = Path(args.output).resolve()

    bundle_dir = build_excalibur_input(scene_path, output_dir)

    print(f"Generated NanoCalibur bundle: {bundle_dir}")
    print(f"- {bundle_dir / 'game_spec.json'}")
    print(f"- {bundle_dir / 'game_ir.json'}")
    print(f"- {bundle_dir / 'game_logic.ts'}")
    print(f"- {bundle_dir / 'interpreter.ts'}")
    print(f"- {bundle_dir / 'bridge.ts'}")
    print(f"- {bundle_dir / 'index.ts'}")

    if args.project:
        project_dir = Path(args.project).resolve()
        target_dir = sync_into_excalibur_project(bundle_dir, project_dir)
        print(f"Copied bundle to Excalibur project: {target_dir}")


if __name__ == "__main__":
    main()
