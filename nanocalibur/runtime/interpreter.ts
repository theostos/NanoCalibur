export interface FramePhaseInput {
  begin?: string[];
  on?: string[];
  end?: string[];
}

export interface CollisionFrameInput {
  a?: Record<string, any>;
  b?: Record<string, any>;
  aUid?: string;
  bUid?: string;
  uids?: string[];
}

export interface NanoCaliburFrameInput {
  keyboard?: FramePhaseInput;
  mouse?: FramePhaseInput;
  collisions?: CollisionFrameInput[];
  keysJustPressed?: string[];
  keysBegin?: string[];
  keysPressed?: string[];
  keysDown?: string[];
  keysJustReleased?: string[];
  keysEnd?: string[];
  mouseButtonsJustPressed?: string[];
  mouseButtons?: string[];
  mouseButtonsJustReleased?: string[];
  mouseClicked?: boolean | { button?: string };
}

export interface InterpreterState {
  globals: Record<string, any>;
  actors: Record<string, any>[];
  camera: Record<string, any> | null;
  map: Record<string, any> | null;
}

type ActionFn = (ctx: Record<string, any>) => void;
type PredicateFn = (actor: Record<string, any>) => boolean;

export class NanoCaliburInterpreter {
  private readonly spec: Record<string, any>;
  private readonly actionFns: Record<string, ActionFn>;
  private readonly predicateFns: Record<string, PredicateFn>;
  private readonly actors: Record<string, any>[];
  private readonly globals: Record<string, any>;
  private readonly rules: Record<string, any>[];
  private readonly map: Record<string, any> | null;
  private readonly cameraConfig: Record<string, any> | null;
  private readonly predicateMeta: Record<string, { actor_type: string | null }>;
  private readonly solidTiles: Set<string>;

  constructor(
    spec: Record<string, any>,
    actionFns: Record<string, ActionFn>,
    predicateFns: Record<string, PredicateFn> = {},
  ) {
    this.spec = spec || {};
    this.actionFns = actionFns || {};
    this.predicateFns = predicateFns || {};

    this.actors = this.initActors(this.spec.actors || []);
    this.globals = this.initGlobals(this.spec.globals || []);
    this.rules = this.spec.rules || [];
    this.map = this.spec.map || null;
    this.cameraConfig = this.spec.camera || null;
    this.predicateMeta = this.buildPredicateMeta(this.spec.predicates || []);
    this.solidTiles = this.buildSolidTileSet(this.map);
  }

  tick(frame: NanoCaliburFrameInput = {}): void {
    const context = this.buildContext();
    for (const rule of this.rules) {
      if (this.conditionMatches(rule.condition, frame)) {
        const fn = this.actionFns[rule.action];
        if (typeof fn !== "function") {
          throw new Error(`Missing action function '${rule.action}'.`);
        }
        fn(context);
      }
    }
  }

  getState(): InterpreterState {
    return {
      globals: this.globals,
      actors: this.actors,
      camera: this.getCameraState(),
      map: this.map,
    };
  }

  getCameraState(): Record<string, any> | null {
    if (!this.cameraConfig) {
      return null;
    }
    if (this.cameraConfig.mode === "fixed") {
      return {
        mode: "fixed",
        x: this.cameraConfig.x,
        y: this.cameraConfig.y,
      };
    }
    if (this.cameraConfig.mode === "follow") {
      const actor = this.getActorByUid(this.cameraConfig.target_uid);
      return {
        mode: "follow",
        target_uid: this.cameraConfig.target_uid,
        x: actor && typeof actor.x === "number" ? actor.x : 0,
        y: actor && typeof actor.y === "number" ? actor.y : 0,
      };
    }
    return null;
  }

  isSolidAtWorld(worldX: number, worldY: number): boolean {
    if (!this.map) {
      return false;
    }
    const tileSize = this.map.tile_size;
    const tileX = Math.floor(worldX / tileSize);
    const tileY = Math.floor(worldY / tileSize);
    return this.solidTiles.has(`${tileX},${tileY}`);
  }

  private buildContext(): Record<string, any> {
    return {
      globals: this.globals,
      actors: this.actors,
      getActorByUid: (uid: string) => this.getActorByUid(uid),
    };
  }

  private initGlobals(globalsSpec: Record<string, any>[]): Record<string, any> {
    const globals: Record<string, any> = {};
    for (const globalVar of globalsSpec) {
      if (globalVar.kind === "actor_ref") {
        const payload = globalVar.value || {};
        globals[globalVar.name] = this.getActorByUid(payload.uid);
      } else {
        globals[globalVar.name] = globalVar.value;
      }
    }
    return globals;
  }

  private initActors(actorSpecs: Record<string, any>[]): Record<string, any>[] {
    return actorSpecs.map((actor) => ({
      uid: actor.uid,
      type: actor.type,
      ...(actor.fields || {}),
    }));
  }

  private buildSolidTileSet(mapSpec: Record<string, any> | null): Set<string> {
    const tiles = new Set<string>();
    if (!mapSpec || !Array.isArray(mapSpec.solid_tiles)) {
      return tiles;
    }
    for (const tile of mapSpec.solid_tiles) {
      if (Array.isArray(tile) && tile.length === 2) {
        tiles.add(`${tile[0]},${tile[1]}`);
      }
    }
    return tiles;
  }

  private buildPredicateMeta(
    predicateDefs: Array<string | { name?: string; actor_type?: string | null }>,
  ): Record<string, { actor_type: string | null }> {
    const out: Record<string, { actor_type: string | null }> = {};
    for (const item of predicateDefs) {
      if (typeof item === "string") {
        out[item] = { actor_type: null };
      } else if (item && typeof item.name === "string") {
        out[item.name] = { actor_type: item.actor_type || null };
      }
    }
    return out;
  }

  private conditionMatches(condition: Record<string, any>, frame: NanoCaliburFrameInput): boolean {
    if (!condition || typeof condition !== "object") {
      return false;
    }

    if (condition.kind === "keyboard" || condition.kind === "keyboard_pressed") {
      const phase = condition.phase || "on";
      return this.matchKeyboardPhase(frame, phase, condition.key);
    }

    if (condition.kind === "mouse" || condition.kind === "mouse_clicked") {
      const phase = condition.phase || "on";
      return this.matchMousePhase(frame, phase, condition.button || "left");
    }

    if (condition.kind === "collision") {
      const collisions = Array.isArray(frame.collisions) ? frame.collisions : [];
      for (const collision of collisions) {
        const [a, b] = this.resolveCollisionPair(collision);
        if (!a || !b) {
          continue;
        }
        const direct =
          this.matchesSelector(condition.left, a) &&
          this.matchesSelector(condition.right, b);
        const swapped =
          this.matchesSelector(condition.left, b) &&
          this.matchesSelector(condition.right, a);
        if (direct || swapped) {
          return true;
        }
      }
      return false;
    }

    if (condition.kind === "logical") {
      const fn = this.predicateFns[condition.predicate];
      if (typeof fn !== "function") {
        throw new Error(`Missing predicate function '${condition.predicate}'.`);
      }
      const predicateType =
        this.predicateMeta[condition.predicate] &&
        this.predicateMeta[condition.predicate].actor_type;
      const selected = this.selectActors(condition.target).filter((actor) => {
        if (!predicateType) {
          return true;
        }
        return actor.type === predicateType;
      });
      return selected.some((actor) => Boolean(fn(actor)));
    }

    return false;
  }

  private resolveCollisionPair(
    collision: CollisionFrameInput,
  ): [Record<string, any> | null, Record<string, any> | null] {
    if (!collision || typeof collision !== "object") {
      return [null, null];
    }
    if (collision.a && collision.b) {
      return [collision.a, collision.b];
    }
    if (collision.aUid && collision.bUid) {
      return [this.getActorByUid(collision.aUid), this.getActorByUid(collision.bUid)];
    }
    if (Array.isArray(collision.uids) && collision.uids.length === 2) {
      return [
        this.getActorByUid(collision.uids[0]),
        this.getActorByUid(collision.uids[1]),
      ];
    }
    return [null, null];
  }

  private matchKeyboardPhase(
    frame: NanoCaliburFrameInput,
    phase: string,
    key: string,
  ): boolean {
    const keyboard = frame.keyboard || {};
    const begin = this.normalizeStringArray(
      keyboard.begin || frame.keysJustPressed || frame.keysBegin || [],
    );
    const on = this.normalizeStringArray(
      keyboard.on || frame.keysPressed || frame.keysDown || [],
    );
    const end = this.normalizeStringArray(
      keyboard.end || frame.keysJustReleased || frame.keysEnd || [],
    );
    return this.phaseArrayContains(phase, begin, on, end, key);
  }

  private matchMousePhase(
    frame: NanoCaliburFrameInput,
    phase: string,
    button: string,
  ): boolean {
    const mouse = frame.mouse || {};
    const begin = this.normalizeStringArray(
      mouse.begin || frame.mouseButtonsJustPressed || [],
    );
    const on = this.normalizeStringArray(mouse.on || frame.mouseButtons || []);
    const end = this.normalizeStringArray(
      mouse.end || frame.mouseButtonsJustReleased || [],
    );

    if (phase === "on" && begin.length === 0 && on.length === 0 && end.length === 0) {
      const clicked = frame.mouseClicked;
      if (typeof clicked === "boolean") {
        return clicked;
      }
      if (clicked && typeof clicked === "object" && typeof clicked.button === "string") {
        return clicked.button === button;
      }
    }

    return this.phaseArrayContains(phase, begin, on, end, button);
  }

  private phaseArrayContains(
    phase: string,
    begin: string[],
    on: string[],
    end: string[],
    value: string,
  ): boolean {
    if (phase === "begin") {
      return begin.includes(value);
    }
    if (phase === "end") {
      return end.includes(value);
    }
    return on.includes(value);
  }

  private normalizeStringArray(value: unknown): string[] {
    if (!Array.isArray(value)) {
      return [];
    }
    return value
      .filter((item): item is string => typeof item === "string")
      .map((item) => item);
  }

  private selectActors(selector: Record<string, any>): Record<string, any>[] {
    if (!selector || typeof selector !== "object") {
      return [];
    }
    if (selector.kind === "with_uid") {
      const actor = this.getActorByUid(selector.uid);
      if (!actor) {
        return [];
      }
      if (selector.actor_type && actor.type !== selector.actor_type) {
        return [];
      }
      return [actor];
    }

    if (selector.kind === "any") {
      if (!selector.actor_type) {
        return [...this.actors];
      }
      return this.actors.filter((actor) => actor.type === selector.actor_type);
    }

    return [];
  }

  private matchesSelector(selector: Record<string, any>, actor: Record<string, any>): boolean {
    if (!actor || !selector) {
      return false;
    }
    if (selector.kind === "with_uid") {
      if (selector.uid !== actor.uid) {
        return false;
      }
      if (selector.actor_type && selector.actor_type !== actor.type) {
        return false;
      }
      return true;
    }
    if (selector.kind === "any") {
      if (!selector.actor_type) {
        return true;
      }
      return selector.actor_type === actor.type;
    }
    return false;
  }

  private getActorByUid(uid: string): Record<string, any> | null {
    return this.actors.find((actor) => actor.uid === uid) || null;
  }
}
