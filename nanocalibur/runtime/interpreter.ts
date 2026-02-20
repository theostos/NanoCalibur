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
  role_id?: string;
}

export interface NanoCaliburFrameInput {
  keyboard?: FramePhaseInput;
  mouse?: FramePhaseInput;
  uiButtons?: string[];
  collisions?: CollisionFrameInput[];
  contacts?: CollisionFrameInput[];
  toolCalls?: Array<string | ToolFrameInput>;
  parentPreviousPositions?: Array<{
    uid: string;
    x?: number;
    y?: number;
    z?: number;
  }>;
  roleId?: string;
  role_id?: string;
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
  elapsed: number;
  turn: number;
  loopMode: "real_time" | "turn_based" | "hybrid";
  turnChangedThisStep: boolean;
  interfaceHtml: string;
  interfaceByRole: Record<string, string>;
}

export interface InterpreterState {
  globals: Record<string, any>;
  actors: Record<string, any>[];
  roles: Record<string, any>;
  cameras: Record<string, any>;
  camera: Record<string, any> | null;
  map: Record<string, any> | null;
  scene: InterpreterSceneState;
  self?: Record<string, any> | null;
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
type PredicateFn = (payload: Record<string, any>) => boolean;

const COLLISION_LEFT_BINDING_UID = "__nanocalibur_collision_left__";
const COLLISION_RIGHT_BINDING_UID = "__nanocalibur_collision_right__";
const LOGICAL_TARGET_BINDING_UID = "__nanocalibur_logical_target__";

export class NanoCaliburInterpreter {
  private readonly spec: Record<string, any>;
  private readonly actionFns: Record<string, ActionFn>;
  private readonly predicateFns: Record<string, PredicateFn>;
  private readonly actors: Record<string, any>[];
  private readonly globals: Record<string, any>;
  private readonly rules: Record<string, any>[];
  private readonly map: Record<string, any> | null;
  private readonly camerasByName: Record<string, any>;
  private readonly cameraOrder: string[];
  private readonly predicateMeta: Record<
    string,
    { actor_type: string | null; params: Array<Record<string, any>> | null }
  >;
  private readonly maskedTiles: Set<string>;
  private readonly actorRefGlobals = new Map<string, string>();
  private readonly runningActions: ActionGenerator[] = [];
  private readonly sceneState: InterpreterSceneState;
  private readonly rolesById: Record<string, any>;
  private readonly keyboardAliasLookup: Map<string, Set<string>>;
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
    const cameraInit = this.initCameras(this.spec.cameras || []);
    this.camerasByName = cameraInit.byName;
    this.cameraOrder = cameraInit.order;
    this.predicateMeta = this.buildPredicateMeta(this.spec.predicates || []);
    this.maskedTiles = this.buildMaskedTileSet(this.map);
    this.sceneState = this.initSceneState(this.spec.scene || null);
    this.rolesById = this.initRoles(this.spec.roles || []);
    this.keyboardAliasLookup = this.buildKeyboardAliasLookup(this.spec.scene || null);
    this.syncCameraFollowTargets();
  }

  tick(frame: NanoCaliburFrameInput = {}): void {
    this.syncCameraFollowTargets();
    const fallbackPreviousPositions = this.captureActorPositions();
    const previousPositions = this.resolveParentPreviousPositions(
      frame.parentPreviousPositions,
      fallbackPreviousPositions,
    );
    this.sceneState.turnChangedThisStep = false;
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
    this.syncCameraFollowTargets();
    this.sceneState.elapsed += 1;
  }

  getState(): InterpreterState {
    return {
      globals: this.globals,
      actors: this.actors,
      roles: this.rolesById,
      cameras: this.getCameraStates(),
      camera: this.getCameraState(),
      map: this.map,
      scene: {
        gravityEnabled: this.sceneState.gravityEnabled,
        elapsed: this.sceneState.elapsed,
        turn: this.sceneState.turn,
        loopMode: this.sceneState.loopMode,
        turnChangedThisStep: this.sceneState.turnChangedThisStep,
        interfaceHtml: this.sceneState.interfaceHtml,
        interfaceByRole: { ...this.sceneState.interfaceByRole },
      },
    };
  }

  getSpec(): Record<string, any> {
    return this.spec;
  }

  getSceneState(): InterpreterSceneState {
    return {
      gravityEnabled: this.sceneState.gravityEnabled,
      elapsed: this.sceneState.elapsed,
      turn: this.sceneState.turn,
      loopMode: this.sceneState.loopMode,
      turnChangedThisStep: this.sceneState.turnChangedThisStep,
      interfaceHtml: this.sceneState.interfaceHtml,
      interfaceByRole: { ...this.sceneState.interfaceByRole },
    };
  }

  getTools(): Array<{ name: string; tool_docstring: string; action: string; role_id?: string }> {
    const fromSpec = Array.isArray(this.spec.tools) ? this.spec.tools : [];
    const out: Array<{ name: string; tool_docstring: string; action: string; role_id?: string }> = [];
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
        role_id: typeof item.role_id === "string" ? item.role_id : undefined,
      });
    }
    return out;
  }

  setRuntimeHooks(runtimeHooks: RuntimeHooks): void {
    this.runtimeHooks = runtimeHooks || {};
  }

  getCameraState(): Record<string, any> | null {
    const defaultName = this.cameraOrder.length > 0 ? this.cameraOrder[0] : null;
    if (!defaultName) {
      return null;
    }
    return this.getResolvedCameraState(this.camerasByName[defaultName]);
  }

  getCameraStateForRole(roleId: string | null): Record<string, any> | null {
    if (typeof roleId !== "string" || !roleId) {
      return null;
    }
    const camera = this.getCameraForRole(roleId);
    if (!camera) {
      return null;
    }
    return this.getResolvedCameraState(camera);
  }

  getCameraByName(name: string): Record<string, any> | null {
    if (typeof name !== "string" || !name) {
      return null;
    }
    const camera = this.camerasByName[name];
    if (!camera || typeof camera !== "object") {
      return null;
    }
    return camera;
  }

  getCameraStates(): Record<string, any> {
    const out: Record<string, any> = {};
    for (const name of this.cameraOrder) {
      const camera = this.camerasByName[name];
      if (!camera || typeof camera !== "object") {
        continue;
      }
      out[name] = this.getResolvedCameraState(camera);
    }
    return out;
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
      cameras: this.camerasByName,
      roles: this.rolesById,
      tick: 1,
      elapsed: this.sceneState.elapsed,
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
      getCameraByName: (name: string) => this.getCameraByName(name),
      getRoleById: (id: string) => this.getRoleById(id),
      playAnimation: this.runtimeHooks.playAnimation,
      destroyActor: (actor: Record<string, any>) => this.destroyActor(actor),
      scene: {
        gravityEnabled: this.sceneState.gravityEnabled,
        elapsed: this.sceneState.elapsed,
        setGravityEnabled: (enabled: boolean) => this.setGravityEnabled(enabled),
        nextTurn: () => this.nextTurn(),
        setInterfaceHtml: (html: string, role?: unknown) => this.setInterfaceHtml(html, role),
        followCamera: (camera: Record<string, any>, targetUid: string) =>
          this.followCamera(camera, targetUid),
        detachCamera: (camera: Record<string, any>) => this.detachCamera(camera),
        translateCamera: (camera: Record<string, any>, dx: number, dy: number) =>
          this.translateCamera(camera, dx, dy),
        spawnActor: (
          actorType: string,
          uid: string,
          fields?: Record<string, any>,
        ) => this.spawnActor(actorType, uid, fields || {}),
      },
      tool: toolCall,
    };
  }

  private buildPredicateContext(
    logicalTarget: Record<string, any>,
  ): Record<string, any> {
    return {
      globals: this.globals,
      actors: this.actors,
      cameras: this.camerasByName,
      roles: this.rolesById,
      tick: 1,
      elapsed: this.sceneState.elapsed,
      getActorByUid: (uid: string) => {
        if (uid === LOGICAL_TARGET_BINDING_UID) {
          return logicalTarget;
        }
        return this.getActorByUid(uid);
      },
      getCameraByName: (name: string) => this.getCameraByName(name),
      getRoleById: (id: string) => this.getRoleById(id),
      scene: {
        gravityEnabled: this.sceneState.gravityEnabled,
        elapsed: this.sceneState.elapsed,
        setGravityEnabled: (enabled: boolean) => this.setGravityEnabled(enabled),
        followCamera: (camera: Record<string, any>, targetUid: string) =>
          this.followCamera(camera, targetUid),
        detachCamera: (camera: Record<string, any>) => this.detachCamera(camera),
        translateCamera: (camera: Record<string, any>, dx: number, dy: number) =>
          this.translateCamera(camera, dx, dy),
        setInterfaceHtml: (html: string, role?: unknown) => this.setInterfaceHtml(html, role),
        spawnActor: (
          actorType: string,
          uid: string,
          fields?: Record<string, any>,
        ) => this.spawnActor(actorType, uid, fields || {}),
      },
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
        globals[globalVar.name] = this.cloneStructuredValue(globalVar.value);
      }
    }
    return globals;
  }

  private initActors(actorSpecs: Record<string, any>[]): Record<string, any>[] {
    return actorSpecs.map((actor) => {
      const out = {
        ...(this.cloneStructuredValue(actor.fields || {}) as Record<string, any>),
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

  private initRoles(roleSpecs: Record<string, any>[]): Record<string, any> {
    const out: Record<string, any> = {};
    if (!Array.isArray(roleSpecs)) {
      return out;
    }
    for (const role of roleSpecs) {
      if (!role || typeof role !== "object") {
        continue;
      }
      const id = typeof role.id === "string" ? role.id : "";
      if (!id) {
        continue;
      }
      const roleFields =
        role.fields && typeof role.fields === "object"
          ? (this.cloneStructuredValue(role.fields) as Record<string, any>)
          : {};
      out[id] = {
        id,
        type: typeof role.type === "string" ? role.type : "Role",
        kind: typeof role.kind === "string" ? role.kind : "hybrid",
        required: typeof role.required === "boolean" ? role.required : true,
        ...roleFields,
      };
    }
    return out;
  }

  private initCameras(
    cameraSpecs: Record<string, any>[],
  ): { byName: Record<string, any>; order: string[] } {
    const byName: Record<string, any> = {};
    const order: string[] = [];
    if (!Array.isArray(cameraSpecs)) {
      return { byName, order };
    }
    for (const raw of cameraSpecs) {
      if (!raw || typeof raw !== "object") {
        continue;
      }
      const name = typeof raw.name === "string" ? raw.name : "";
      const roleId = typeof raw.role_id === "string" ? raw.role_id : "";
      if (!name || !roleId || byName[name]) {
        continue;
      }
      const width =
        typeof raw.width === "number" && Number.isFinite(raw.width) && raw.width > 0
          ? Math.floor(raw.width)
          : null;
      const height =
        typeof raw.height === "number" && Number.isFinite(raw.height) && raw.height > 0
          ? Math.floor(raw.height)
          : null;
      byName[name] = {
        name,
        role_id: roleId,
        x: this.asFiniteNumber(raw.x, 0),
        y: this.asFiniteNumber(raw.y, 0),
        width,
        height,
        target_uid:
          typeof raw.target_uid === "string" && raw.target_uid ? raw.target_uid : null,
        offset_x: this.asFiniteNumber(raw.offset_x, 0),
        offset_y: this.asFiniteNumber(raw.offset_y, 0),
      };
      order.push(name);
    }
    return { byName, order };
  }

  private getCameraForRole(roleId: string): Record<string, any> | null {
    if (typeof roleId !== "string" || !roleId) {
      return null;
    }
    for (const name of this.cameraOrder) {
      const camera = this.camerasByName[name];
      if (!camera || typeof camera !== "object") {
        continue;
      }
      if (camera.role_id === roleId) {
        return camera;
      }
    }
    return null;
  }

  private getResolvedCameraState(camera: Record<string, any>): Record<string, any> {
    const resolvedX = this.asFiniteNumber(camera.x, 0);
    const resolvedY = this.asFiniteNumber(camera.y, 0);
    return {
      name: camera.name,
      role_id: camera.role_id,
      x: resolvedX,
      y: resolvedY,
      width:
        typeof camera.width === "number" && Number.isFinite(camera.width) && camera.width > 0
          ? Math.floor(camera.width)
          : null,
      height:
        typeof camera.height === "number" && Number.isFinite(camera.height) && camera.height > 0
          ? Math.floor(camera.height)
          : null,
      target_uid:
        typeof camera.target_uid === "string" && camera.target_uid ? camera.target_uid : null,
      offset_x: this.asFiniteNumber(camera.offset_x, 0),
      offset_y: this.asFiniteNumber(camera.offset_y, 0),
    };
  }

  private syncCameraFollowTargets(): void {
    for (const name of this.cameraOrder) {
      const camera = this.camerasByName[name];
      if (!camera || typeof camera !== "object") {
        continue;
      }
      if (typeof camera.target_uid !== "string" || !camera.target_uid) {
        continue;
      }
      const target = this.getActorByUid(camera.target_uid);
      if (!target) {
        continue;
      }
      camera.x = this.asFiniteNumber(target.x, this.asFiniteNumber(camera.x, 0))
        + this.asFiniteNumber(camera.offset_x, 0);
      camera.y = this.asFiniteNumber(target.y, this.asFiniteNumber(camera.y, 0))
        + this.asFiniteNumber(camera.offset_y, 0);
    }
  }

  private followCamera(camera: Record<string, any>, targetUid: string): void {
    if (!camera || typeof camera !== "object") {
      return;
    }
    if (typeof targetUid !== "string" || !targetUid) {
      return;
    }
    camera.target_uid = targetUid;
    camera.offset_x = 0;
    camera.offset_y = 0;
    this.syncCameraFollowTargets();
  }

  private detachCamera(camera: Record<string, any>): void {
    if (!camera || typeof camera !== "object") {
      return;
    }
    this.syncCameraFollowTargets();
    camera.target_uid = null;
    camera.offset_x = 0;
    camera.offset_y = 0;
  }

  private translateCamera(camera: Record<string, any>, dx: number, dy: number): void {
    if (!camera || typeof camera !== "object") {
      return;
    }
    const safeDx = this.asFiniteNumber(dx, 0);
    const safeDy = this.asFiniteNumber(dy, 0);
    if (typeof camera.target_uid === "string" && camera.target_uid) {
      camera.offset_x = this.asFiniteNumber(camera.offset_x, 0) + safeDx;
      camera.offset_y = this.asFiniteNumber(camera.offset_y, 0) + safeDy;
      this.syncCameraFollowTargets();
      return;
    }
    camera.x = this.asFiniteNumber(camera.x, 0) + safeDx;
    camera.y = this.asFiniteNumber(camera.y, 0) + safeDy;
  }

  private getRoleById(id: string): Record<string, any> | null {
    if (typeof id !== "string" || !id) {
      return null;
    }
    const role = this.rolesById[id];
    if (!role || typeof role !== "object") {
      return null;
    }
    return role;
  }

  private initSceneState(sceneSpec: Record<string, any> | null): InterpreterSceneState {
    const loopMode = this.resolveLoopMode(
      this.spec?.multiplayer && typeof this.spec.multiplayer === "object"
        ? this.spec.multiplayer.default_loop
        : null,
    );
    const interfaceByRole: Record<string, string> = {};
    const roleInterfacesRaw =
      this.spec && this.spec.interfaces_by_role && typeof this.spec.interfaces_by_role === "object"
        ? (this.spec.interfaces_by_role as Record<string, unknown>)
        : {};
    for (const [roleId, html] of Object.entries(roleInterfacesRaw)) {
      if (typeof roleId !== "string" || !roleId) {
        continue;
      }
      if (typeof html !== "string") {
        continue;
      }
      interfaceByRole[roleId] = html;
    }
    return {
      gravityEnabled: Boolean(sceneSpec && sceneSpec.gravity_enabled),
      elapsed: 0,
      turn: 0,
      loopMode,
      turnChangedThisStep: false,
      interfaceHtml:
        typeof this.spec?.interface_html === "string" ? this.spec.interface_html : "",
      interfaceByRole,
    };
  }

  private resolveLoopMode(value: unknown): "real_time" | "turn_based" | "hybrid" {
    if (value === "turn_based" || value === "hybrid" || value === "real_time") {
      return value;
    }
    return "real_time";
  }

  private nextTurn(): void {
    this.sceneState.turn += 1;
    this.sceneState.turnChangedThisStep = true;
  }

  private setInterfaceHtml(html: string, role?: unknown): void {
    const nextHtml = typeof html === "string" ? html : String(html ?? "");
    const roleId = this.resolveRoleIdArg(role);
    if (roleId) {
      this.sceneState.interfaceByRole[roleId] = nextHtml;
      return;
    }
    this.sceneState.interfaceHtml = nextHtml;
  }

  private resolveRoleIdArg(role: unknown): string | null {
    if (typeof role === "string") {
      return role || null;
    }
    if (role && typeof role === "object" && typeof (role as { id?: unknown }).id === "string") {
      const id = (role as { id: string }).id;
      return id || null;
    }
    return null;
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
    predicateDefs: Array<
      string | { name?: string; actor_type?: string | null; params?: unknown }
    >,
  ): Record<string, { actor_type: string | null; params: Array<Record<string, any>> | null }> {
    const out: Record<
      string,
      { actor_type: string | null; params: Array<Record<string, any>> | null }
    > = {};
    for (const item of predicateDefs) {
      if (typeof item === "string") {
        out[item] = { actor_type: null, params: null };
      } else if (item && typeof item.name === "string") {
        const params = Array.isArray(item.params)
          ? item.params.filter(
              (entry): entry is Record<string, any> =>
                Boolean(entry) && typeof entry === "object",
            )
          : null;
        out[item.name] = { actor_type: item.actor_type || null, params };
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
      if (!this.matchesRoleScope(condition, frame)) {
        return { matched: false };
      }
      const phase = condition.phase || "on";
      return { matched: this.matchKeyboardPhase(frame, phase, condition.key) };
    }

    if (condition.kind === "mouse" || condition.kind === "mouse_clicked") {
      if (!this.matchesRoleScope(condition, frame)) {
        return { matched: false };
      }
      const phase = condition.phase || "on";
      return {
        matched: this.matchMousePhase(frame, phase, condition.button || "left"),
      };
    }

    if (
      condition.kind === "collision" ||
      condition.kind === "overlap" ||
      condition.kind === "contact"
    ) {
      const mode =
        typeof condition.mode === "string"
          ? condition.mode
          : condition.kind === "contact"
            ? "contact"
            : "overlap";
      const collisions =
        mode === "contact"
          ? Array.isArray(frame.contacts)
            ? frame.contacts
            : []
          : Array.isArray(frame.collisions)
            ? frame.collisions
            : [];
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
      const predicateMeta = this.predicateMeta[condition.predicate] || {
        actor_type: null,
        params: null,
      };
      const predicateType = predicateMeta.actor_type;
      const selected = this.selectActors(condition.target).filter((actor) => {
        if (!predicateType) {
          return true;
        }
        return actor.type === predicateType;
      });
      if (predicateMeta.params && predicateMeta.params.length > 0) {
        return {
          matched: selected.some((actor) =>
            Boolean(fn(this.buildPredicateContext(actor))),
          ),
        };
      }
      return { matched: selected.some((actor) => Boolean(fn(actor))) };
    }

    if (condition.kind === "tool") {
      const toolName = typeof condition.name === "string" ? condition.name : "";
      if (!toolName) {
        return { matched: false };
      }
      const toolCalls = this.normalizeToolCalls(frame.toolCalls);
      for (const toolCall of toolCalls) {
        if (toolCall.name === toolName && this.matchesRoleScope(condition, frame, toolCall)) {
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
    const begin = this.expandKeyboardValues(this.normalizeStringArray(
      keyboard.begin || frame.keysJustPressed || frame.keysBegin || [],
    ));
    const on = this.expandKeyboardValues(this.normalizeStringArray(
      keyboard.on || frame.keysPressed || frame.keysDown || [],
    ));
    const end = this.expandKeyboardValues(this.normalizeStringArray(
      keyboard.end || frame.keysJustReleased || frame.keysEnd || [],
    ));
    if (Array.isArray(key)) {
      for (const item of key) {
        if (this.phaseSetContains(phase, begin, on, end, item)) {
          return true;
        }
      }
      return false;
    }
    return this.phaseSetContains(phase, begin, on, end, key);
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

  private phaseSetContains(
    phase: string,
    begin: Set<string>,
    on: Set<string>,
    end: Set<string>,
    value: string,
  ): boolean {
    const candidates = this.expandKeyboardToken(value);
    if (phase === "begin") {
      return this.setContainsAny(begin, candidates);
    }
    if (phase === "end") {
      return this.setContainsAny(end, candidates);
    }
    return this.setContainsAny(on, candidates);
  }

  private setContainsAny(haystack: Set<string>, candidates: string[]): boolean {
    for (const candidate of candidates) {
      if (haystack.has(candidate)) {
        return true;
      }
    }
    return false;
  }

  private expandKeyboardValues(values: string[]): Set<string> {
    const out = new Set<string>();
    for (const value of values) {
      const expanded = this.expandKeyboardToken(value);
      for (const token of expanded) {
        out.add(token);
      }
    }
    return out;
  }

  private expandKeyboardToken(token: string): string[] {
    if (typeof token !== "string" || token.length === 0) {
      return [];
    }

    const out = new Set<string>();
    const queue: string[] = [token];
    while (queue.length > 0) {
      const current = queue.pop();
      if (!current || out.has(current)) {
        continue;
      }
      out.add(current);

      const lower = current.toLowerCase();
      if (!out.has(lower)) {
        queue.push(lower);
      }

      if (/^[a-zA-Z]$/.test(current)) {
        const upper = current.toUpperCase();
        const lowerLetter = current.toLowerCase();
        const code = `Key${upper}`;
        if (!out.has(upper)) {
          queue.push(upper);
        }
        if (!out.has(lowerLetter)) {
          queue.push(lowerLetter);
        }
        if (!out.has(code)) {
          queue.push(code);
        }
      } else {
        const codeMatch = /^Key([a-zA-Z])$/.exec(current);
        if (codeMatch) {
          const letter = codeMatch[1];
          const upper = letter.toUpperCase();
          const lowerLetter = upper.toLowerCase();
          if (!out.has(upper)) {
            queue.push(upper);
          }
          if (!out.has(lowerLetter)) {
            queue.push(lowerLetter);
          }
        }
      }

      const aliases = this.keyboardAliasLookup.get(lower);
      if (aliases) {
        for (const alias of aliases) {
          if (!out.has(alias)) {
            queue.push(alias);
          }
        }
      }
    }

    return [...out];
  }

  private buildKeyboardAliasLookup(
    sceneSpec: Record<string, any> | null,
  ): Map<string, Set<string>> {
    const groups: string[][] = [
      ["ArrowUp", "arrowup", "up"],
      ["ArrowDown", "arrowdown", "down"],
      ["ArrowLeft", "arrowleft", "left"],
      ["ArrowRight", "arrowright", "right"],
      [" ", "Space", "space", "Spacebar"],
    ];

    const sceneAliases =
      sceneSpec && sceneSpec.keyboard_aliases && typeof sceneSpec.keyboard_aliases === "object"
        ? (sceneSpec.keyboard_aliases as Record<string, unknown>)
        : {};
    for (const [source, aliasValue] of Object.entries(sceneAliases)) {
      if (typeof source !== "string" || source.length === 0) {
        continue;
      }
      const aliases: string[] = [];
      if (typeof aliasValue === "string") {
        aliases.push(aliasValue);
      } else if (Array.isArray(aliasValue)) {
        for (const item of aliasValue) {
          if (typeof item === "string" && item.length > 0) {
            aliases.push(item);
          }
        }
      }
      if (aliases.length === 0) {
        continue;
      }
      groups.push([source, ...aliases]);
    }

    const lookup = new Map<string, Set<string>>();
    for (const group of groups) {
      const tokens = Array.from(new Set(group.filter((token) => token.length > 0)));
      if (tokens.length < 2) {
        continue;
      }
      for (const token of tokens) {
        const key = token.toLowerCase();
        let entry = lookup.get(key);
        if (!entry) {
          entry = new Set<string>();
          lookup.set(key, entry);
        }
        for (const candidate of tokens) {
          entry.add(candidate);
        }
      }
    }
    return lookup;
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
          role_id:
            typeof (item as ToolFrameInput).role_id === "string"
              ? (item as ToolFrameInput).role_id
              : undefined,
        });
      }
    }
    return out;
  }

  private matchesRoleScope(
    condition: Record<string, any>,
    frame: NanoCaliburFrameInput,
    toolCall: ToolFrameInput | null = null,
  ): boolean {
    const scopedRoleId =
      condition && typeof condition.role_id === "string" && condition.role_id
        ? condition.role_id
        : null;
    if (!scopedRoleId) {
      return true;
    }
    const frameRoleId = this.readFrameRoleId(frame, toolCall);
    return frameRoleId === scopedRoleId;
  }

  private readFrameRoleId(
    frame: NanoCaliburFrameInput,
    toolCall: ToolFrameInput | null = null,
  ): string | null {
    if (!frame || typeof frame !== "object") {
      if (toolCall && typeof toolCall.role_id === "string" && toolCall.role_id) {
        return toolCall.role_id;
      }
      return null;
    }
    if (typeof frame.role_id === "string" && frame.role_id) {
      return frame.role_id;
    }
    if (typeof frame.roleId === "string" && frame.roleId) {
      return frame.roleId;
    }
    if (toolCall && typeof toolCall.role_id === "string" && toolCall.role_id) {
      return toolCall.role_id;
    }
    return null;
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
        actor[fieldName] = this.cloneStructuredValue(value);
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

  private resolveParentPreviousPositions(
    encoded:
      | Array<{
          uid: string;
          x?: number;
          y?: number;
          z?: number;
        }>
      | undefined,
    fallback: Map<string, { x: number; y: number; z: number }>,
  ): Map<string, { x: number; y: number; z: number }> {
    if (!Array.isArray(encoded) || encoded.length === 0) {
      return fallback;
    }
    const out = new Map<string, { x: number; y: number; z: number }>();
    for (const item of encoded) {
      if (!item || typeof item.uid !== "string" || !item.uid) {
        continue;
      }
      out.set(item.uid, {
        x: this.numberOrZero(item.x),
        y: this.numberOrZero(item.y),
        z: this.numberOrZero(item.z),
      });
    }
    if (out.size === 0) {
      return fallback;
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

  private asFiniteNumber(value: unknown, fallback: number): number {
    return typeof value === "number" && Number.isFinite(value) ? value : fallback;
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
    if (typeLabel.startsWith("dict[")) {
      return {};
    }
    return null;
  }

  private cloneStructuredValue(value: any): any {
    if (Array.isArray(value)) {
      return value.map((item) => this.cloneStructuredValue(item));
    }
    if (value && typeof value === "object") {
      const out: Record<string, any> = {};
      for (const [key, item] of Object.entries(value)) {
        out[key] = this.cloneStructuredValue(item);
      }
      return out;
    }
    return value;
  }

  private getActorByUid(uid: string): Record<string, any> | null {
    return this.actors.find((actor) => actor.uid === uid) || null;
  }
}
