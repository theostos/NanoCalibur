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
