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

export interface ToolFrameInput {
  name: string;
  payload?: Record<string, any>;
}

export interface NanoCaliburFrameInput {
  keyboard?: FramePhaseInput;
  mouse?: FramePhaseInput;
  uiButtons?: string[];
  collisions?: CollisionFrameInput[];
  toolCalls?: Array<string | ToolFrameInput>;
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

export interface InterpreterSceneState {
  gravityEnabled: boolean;
}

export interface InterpreterState {
  globals: Record<string, any>;
  actors: Record<string, any>[];
  camera: Record<string, any> | null;
  map: Record<string, any> | null;
  scene: InterpreterSceneState;
}

export interface RuntimeHooks {
  playAnimation?: (actor: Record<string, any>, clipName: string) => void;
  destroyActor?: (actor: Record<string, any>) => void;
  scene?: {
    setGravityEnabled?: (enabled: boolean) => void;
    spawnActor?: (actor: Record<string, any>) => void;
  };
}

interface ConditionMatchResult {
  matched: boolean;
  collisionPair?: [Record<string, any>, Record<string, any>];
  toolCall?: ToolFrameInput;
}

type ActionGenerator = Iterator<unknown, void, unknown>;
type ActionFn = (ctx: Record<string, any>) => void | ActionGenerator;
type PredicateFn = (actor: Record<string, any>) => boolean;

const COLLISION_LEFT_BINDING_UID = "__nanocalibur_collision_left__";
const COLLISION_RIGHT_BINDING_UID = "__nanocalibur_collision_right__";

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
  private readonly maskedTiles: Set<string>;
  private readonly actorRefGlobals = new Map<string, string>();
  private readonly runningActions: ActionGenerator[] = [];
  private readonly sceneState: InterpreterSceneState;
  private runtimeHooks: RuntimeHooks;

  constructor(
    spec: Record<string, any>,
    actionFns: Record<string, ActionFn>,
    predicateFns: Record<string, PredicateFn> = {},
    runtimeHooks: RuntimeHooks = {},
  ) {
    this.spec = spec || {};
    this.actionFns = actionFns || {};
    this.predicateFns = predicateFns || {};
    this.runtimeHooks = runtimeHooks || {};

    this.actors = this.initActors(this.spec.actors || []);
    this.globals = this.initGlobals(this.spec.globals || []);
    this.rules = this.spec.rules || [];
    this.map = this.spec.map || null;
    this.cameraConfig = this.spec.camera || null;
    this.predicateMeta = this.buildPredicateMeta(this.spec.predicates || []);
    this.maskedTiles = this.buildMaskedTileSet(this.map);
    this.sceneState = this.initSceneState(this.spec.scene || null);
  }

  tick(frame: NanoCaliburFrameInput = {}): void {
    const previousPositions = this.captureActorPositions();
    this.advanceRunningActions();
    for (const rule of this.rules) {
      const match = this.conditionMatches(rule.condition, frame);
      if (!match.matched) {
        continue;
      }

      const fn = this.actionFns[rule.action];
      if (typeof fn !== "function") {
        throw new Error(`Missing action function '${rule.action}'.`);
      }
      const context = this.buildContext(match.collisionPair || null, match.toolCall || null);
      const result = fn(context);
      if (this.isActionGenerator(result)) {
        this.runningActions.push(result);
      }
    }
    this.applyParentBindings(previousPositions);
  }

  getState(): InterpreterState {
    return {
      globals: this.globals,
      actors: this.actors,
      camera: this.getCameraState(),
      map: this.map,
      scene: { gravityEnabled: this.sceneState.gravityEnabled },
    };
  }

  getSpec(): Record<string, any> {
    return this.spec;
  }

  getSceneState(): InterpreterSceneState {
    return { gravityEnabled: this.sceneState.gravityEnabled };
  }

  getTools(): Array<{ name: string; tool_docstring: string; action: string }> {
    const fromSpec = Array.isArray(this.spec.tools) ? this.spec.tools : [];
    const out: Array<{ name: string; tool_docstring: string; action: string }> = [];
    const seen = new Set<string>();
    for (const item of fromSpec) {
      if (!item || typeof item.name !== "string" || !item.name) {
        continue;
      }
      if (seen.has(item.name)) {
        continue;
      }
      seen.add(item.name);
      out.push({
        name: item.name,
        tool_docstring:
          typeof item.tool_docstring === "string" ? item.tool_docstring : "",
        action: typeof item.action === "string" ? item.action : "",
      });
    }
    return out;
  }

  setRuntimeHooks(runtimeHooks: RuntimeHooks): void {
    this.runtimeHooks = runtimeHooks || {};
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
    return this.maskedTiles.has(`${tileX},${tileY}`);
  }

  private buildContext(
    collisionPair: [Record<string, any>, Record<string, any>] | null,
    toolCall: ToolFrameInput | null,
  ): Record<string, any> {
    return {
      globals: this.globals,
      actors: this.actors,
      tick: 1,
      getActorByUid: (uid: string) => {
        if (collisionPair) {
          if (uid === COLLISION_LEFT_BINDING_UID) {
            return collisionPair[0];
          }
          if (uid === COLLISION_RIGHT_BINDING_UID) {
            return collisionPair[1];
          }
        }
        return this.getActorByUid(uid);
      },
      playAnimation: this.runtimeHooks.playAnimation,
      destroyActor: (actor: Record<string, any>) => this.destroyActor(actor),
      scene: {
        gravityEnabled: this.sceneState.gravityEnabled,
        setGravityEnabled: (enabled: boolean) => this.setGravityEnabled(enabled),
        spawnActor: (
          actorType: string,
          uid: string,
          fields?: Record<string, any>,
        ) => this.spawnActor(actorType, uid, fields || {}),
      },
      tool: toolCall,
    };
  }

  private advanceRunningActions(): void {
    if (this.runningActions.length === 0) {
      return;
    }
    let writeIndex = 0;
    for (const action of this.runningActions) {
      const result = action.next();
      if (!result.done) {
        this.runningActions[writeIndex] = action;
        writeIndex += 1;
      }
    }
    this.runningActions.length = writeIndex;
  }

  private isActionGenerator(value: unknown): value is ActionGenerator {
    if (!value || typeof value !== "object") {
      return false;
    }
    return typeof (value as ActionGenerator).next === "function";
  }

  private initGlobals(globalsSpec: Record<string, any>[]): Record<string, any> {
    const globals: Record<string, any> = {};
    for (const globalVar of globalsSpec) {
      if (globalVar.kind === "actor_ref") {
        const payload = globalVar.value || {};
        const uid = typeof payload.uid === "string" ? payload.uid : "";
        if (uid) {
          this.actorRefGlobals.set(globalVar.name, uid);
        }
        globals[globalVar.name] = uid ? this.getActorByUid(uid) : null;
      } else {
        globals[globalVar.name] = globalVar.value;
      }
    }
    return globals;
  }

  private initActors(actorSpecs: Record<string, any>[]): Record<string, any>[] {
    return actorSpecs.map((actor) => {
      const out = {
        ...(actor.fields || {}),
        uid: actor.uid,
        type: actor.type,
      } as Record<string, any>;
      if (typeof out.active !== "boolean") {
        out.active = true;
      }
      if (typeof out.z !== "number") {
        out.z = 0;
      }
      return out;
    });
  }

  private initSceneState(sceneSpec: Record<string, any> | null): InterpreterSceneState {
    return {
      gravityEnabled: Boolean(sceneSpec && sceneSpec.gravity_enabled),
    };
  }

  private buildMaskedTileSet(mapSpec: Record<string, any> | null): Set<string> {
    const tiles = new Set<string>();
    if (!mapSpec) {
      return tiles;
    }

    if (Array.isArray(mapSpec.tile_grid)) {
      for (let tileY = 0; tileY < mapSpec.tile_grid.length; tileY += 1) {
        const row = mapSpec.tile_grid[tileY];
        if (!Array.isArray(row)) {
          continue;
        }
        for (let tileX = 0; tileX < row.length; tileX += 1) {
          const tileIdRaw = row[tileX];
          if (typeof tileIdRaw !== "number" || !Number.isFinite(tileIdRaw)) {
            continue;
          }
          const tileId = Math.trunc(tileIdRaw);
          if (tileId === 0) {
            continue;
          }
          const tileDef = mapSpec.tile_defs?.[String(tileId)];
          if (!tileDef || typeof tileDef !== "object") {
            continue;
          }
          if (typeof tileDef.block_mask !== "number" || !Number.isFinite(tileDef.block_mask)) {
            continue;
          }
          tiles.add(`${tileX},${tileY}`);
        }
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

  private conditionMatches(
    condition: Record<string, any>,
    frame: NanoCaliburFrameInput,
  ): ConditionMatchResult {
    if (!condition || typeof condition !== "object") {
      return { matched: false };
    }

    if (condition.kind === "keyboard" || condition.kind === "keyboard_pressed") {
      const phase = condition.phase || "on";
      return { matched: this.matchKeyboardPhase(frame, phase, condition.key) };
    }

    if (condition.kind === "mouse" || condition.kind === "mouse_clicked") {
      const phase = condition.phase || "on";
      return {
        matched: this.matchMousePhase(frame, phase, condition.button || "left"),
      };
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
          return {
            matched: true,
            collisionPair: direct ? [a, b] : [b, a],
          };
        }
      }
      return { matched: false };
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
      return { matched: selected.some((actor) => Boolean(fn(actor))) };
    }

    if (condition.kind === "tool") {
      const toolName = typeof condition.name === "string" ? condition.name : "";
      if (!toolName) {
        return { matched: false };
      }
      const toolCalls = this.normalizeToolCalls(frame.toolCalls);
      for (const toolCall of toolCalls) {
        if (toolCall.name === toolName) {
          return { matched: true, toolCall };
        }
      }
      return { matched: false };
    }

    if (condition.kind === "button") {
      const buttonName = typeof condition.name === "string" ? condition.name : "";
      if (!buttonName) {
        return { matched: false };
      }
      const buttons = this.normalizeStringArray(frame.uiButtons || []);
      return { matched: buttons.includes(buttonName) };
    }

    return { matched: false };
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
    key: string | string[],
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
    if (Array.isArray(key)) {
      for (const item of key) {
        if (this.phaseArrayContains(phase, begin, on, end, item)) {
          return true;
        }
      }
      return false;
    }
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

  private normalizeToolCalls(value: unknown): ToolFrameInput[] {
    if (!Array.isArray(value)) {
      return [];
    }
    const out: ToolFrameInput[] = [];
    for (const item of value) {
      if (typeof item === "string" && item) {
        out.push({ name: item, payload: {} });
        continue;
      }
      if (
        item &&
        typeof item === "object" &&
        typeof (item as ToolFrameInput).name === "string" &&
        (item as ToolFrameInput).name
      ) {
        out.push({
          name: (item as ToolFrameInput).name,
          payload:
            (item as ToolFrameInput).payload &&
            typeof (item as ToolFrameInput).payload === "object"
              ? (item as ToolFrameInput).payload
              : {},
        });
      }
    }
    return out;
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

  private setGravityEnabled(enabled: boolean): void {
    const normalized = Boolean(enabled);
    if (this.sceneState.gravityEnabled === normalized) {
      return;
    }
    this.sceneState.gravityEnabled = normalized;
    if (this.runtimeHooks.scene?.setGravityEnabled) {
      this.runtimeHooks.scene.setGravityEnabled(normalized);
    }
  }

  private spawnActor(
    actorType: string,
    uid: string,
    fields: Record<string, any>,
  ): Record<string, any> | null {
    if (typeof actorType !== "string" || !actorType) {
      return null;
    }
    const resolvedUid = typeof uid === "string" && uid ? uid : this.generateActorUid(actorType);

    const existing = this.getActorByUid(resolvedUid);
    if (existing) {
      return existing;
    }

    const schema = this.spec?.schemas?.[actorType] as Record<string, string> | undefined;
    if (!schema || typeof schema !== "object") {
      return null;
    }

    const actor: Record<string, any> = {
      uid: resolvedUid,
      type: actorType,
    };

    for (const [fieldName, fieldType] of Object.entries(schema)) {
      if (fieldName === "active") {
        actor[fieldName] = true;
      } else if (fieldName === "uid") {
        // Canonical uid is managed outside schema fields.
        continue;
      } else if (fieldName === "block_mask") {
        actor[fieldName] = null;
      } else if (fieldName === "x" || fieldName === "y" || fieldName === "z") {
        actor[fieldName] = 0;
      } else if (
        fieldName === "w" ||
        fieldName === "h" ||
        fieldName === "parent" ||
        fieldName === "sprite"
      ) {
        // Keep these unset by default so runtime systems can infer values
        // (e.g. sprite-driven dimensions) and optional links remain absent.
        continue;
      } else {
        actor[fieldName] = this.defaultValueForSchemaType(fieldType);
      }
    }

    if (fields && typeof fields === "object") {
      for (const [fieldName, value] of Object.entries(fields)) {
        if (!(fieldName in schema)) {
          continue;
        }
        actor[fieldName] = Array.isArray(value) ? [...value] : value;
      }
    }

    this.actors.push(actor);
    this.refreshActorRefGlobalsForUid(resolvedUid);

    if (this.runtimeHooks.scene?.spawnActor) {
      this.runtimeHooks.scene.spawnActor(actor);
    }

    return actor;
  }

  private destroyActor(actorOrUid: Record<string, any> | string | null | undefined): void {
    const uid =
      typeof actorOrUid === "string"
        ? actorOrUid
        : actorOrUid && typeof actorOrUid.uid === "string"
          ? actorOrUid.uid
          : null;

    if (!uid) {
      return;
    }

    const index = this.actors.findIndex((actor) => actor.uid === uid);
    if (index < 0) {
      return;
    }

    const removed = this.actors.splice(index, 1)[0];
    removed.active = false;
    this.refreshActorRefGlobalsForUid(uid);

    if (this.runtimeHooks.destroyActor) {
      this.runtimeHooks.destroyActor(removed);
    }
  }

  private refreshActorRefGlobalsForUid(uid: string): void {
    for (const [globalName, globalUid] of this.actorRefGlobals.entries()) {
      if (globalUid !== uid) {
        continue;
      }
      this.globals[globalName] = this.getActorByUid(globalUid);
    }
  }

  private captureActorPositions(): Map<string, { x: number; y: number; z: number }> {
    const out = new Map<string, { x: number; y: number; z: number }>();
    for (const actor of this.actors) {
      if (typeof actor.uid !== "string" || !actor.uid) {
        continue;
      }
      out.set(actor.uid, {
        x: this.numberOrZero(actor.x),
        y: this.numberOrZero(actor.y),
        z: this.numberOrZero(actor.z),
      });
    }
    return out;
  }

  private applyParentBindings(
    previousPositions: Map<string, { x: number; y: number; z: number }>,
  ): void {
    const byUid = new Map<string, Record<string, any>>();
    for (const actor of this.actors) {
      if (typeof actor.uid === "string" && actor.uid) {
        byUid.set(actor.uid, actor);
      }
    }

    const visiting = new Set<string>();
    const visited = new Set<string>();

    const applyFor = (actor: Record<string, any>): void => {
      const uid = typeof actor.uid === "string" ? actor.uid : "";
      if (!uid || visited.has(uid)) {
        return;
      }
      if (visiting.has(uid)) {
        return;
      }
      visiting.add(uid);

      const parentUid = typeof actor.parent === "string" ? actor.parent : "";
      if (parentUid) {
        const parent = byUid.get(parentUid);
        if (parent) {
          applyFor(parent);
          const previous = previousPositions.get(parentUid);
          const parentPrevX = previous ? previous.x : this.numberOrZero(parent.x);
          const parentPrevY = previous ? previous.y : this.numberOrZero(parent.y);
          const parentPrevZ = previous ? previous.z : this.numberOrZero(parent.z);
          const dx = this.numberOrZero(parent.x) - parentPrevX;
          const dy = this.numberOrZero(parent.y) - parentPrevY;
          const dz = this.numberOrZero(parent.z) - parentPrevZ;
          if (dx !== 0) {
            actor.x = this.numberOrZero(actor.x) + dx;
          }
          if (dy !== 0) {
            actor.y = this.numberOrZero(actor.y) + dy;
          }
          if (dz !== 0) {
            actor.z = this.numberOrZero(actor.z) + dz;
          }
        }
      }

      visiting.delete(uid);
      visited.add(uid);
    };

    for (const actor of this.actors) {
      applyFor(actor);
    }
  }

  private numberOrZero(value: unknown): number {
    return typeof value === "number" && Number.isFinite(value) ? value : 0;
  }

  private generateActorUid(actorType: string): string {
    const prefix = actorType.toLowerCase();
    let index = 1;
    while (true) {
      const candidate = `${prefix}_${index}`;
      if (!this.getActorByUid(candidate)) {
        return candidate;
      }
      index += 1;
    }
  }

  private defaultValueForSchemaType(typeLabel: unknown): any {
    if (typeof typeLabel !== "string") {
      return null;
    }
    if (typeLabel === "bool") {
      return false;
    }
    if (typeLabel === "int" || typeLabel === "float") {
      return 0;
    }
    if (typeLabel === "str") {
      return "";
    }
    if (typeLabel.startsWith("list[")) {
      return [];
    }
    return null;
  }

  private getActorByUid(uid: string): Record<string, any> | null {
    return this.actors.find((actor) => actor.uid === uid) || null;
  }
}
