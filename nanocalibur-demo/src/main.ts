import {
  attachNanoCalibur,
  createNanoCaliburInterpreter,
  type CanvasHostOptions,
} from './nanocalibur_generated';
import { mergeSpecOptions } from './nanocalibur_generated/runtime_core';
import type { InterpreterState } from './nanocalibur_generated/interpreter';
import { AssetStore } from './nanocalibur_generated/canvas/assets';
import { AnimationSystem } from './nanocalibur_generated/canvas/animation';
import { CanvasRenderer } from './nanocalibur_generated/canvas/renderer';
import {
  InterfaceOverlay,
  type InterfaceButtonEvent,
  type InterfaceOverlayRect,
} from './nanocalibur_generated/canvas/interface_overlay';
import type {
  ActorState,
  MapSpec,
  SceneInterfaceBinding,
} from './nanocalibur_generated/canvas/types';

type SymbolicLegendEntry = { symbol: string; description: string };
type SymbolicViewFrame = {
  rows: string[];
  legend: SymbolicLegendEntry[];
};
type SymbolicFrame = SymbolicViewFrame & {
  views?: Record<string, SymbolicViewFrame>;
};

interface SessionJoinPayload {
  session_id: string;
  role_id: string;
  access_token: string;
}

interface SessionSnapshot {
  session_id: string;
  frame: SymbolicFrame;
  state: Record<string, any>;
  server_tick?: number;
  ack_seq?: number | null;
}

interface SessionBrowserConfig {
  enabled: boolean;
  baseUrl: string;
  inviteToken: string;
}

interface SessionSummary {
  session_id?: string;
  status?: string;
}

interface SessionRoleSpec {
  id?: string;
  type?: string;
}

interface RoleLocalBundle {
  localState: Record<string, any>;
  roleType: string | null;
}

function deepCloneValue<T>(value: T): T {
  if (typeof structuredClone === 'function') {
    return structuredClone(value);
  }
  try {
    return JSON.parse(JSON.stringify(value)) as T;
  } catch {
    return value;
  }
}

function isPlainRecord(value: unknown): value is Record<string, any> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return false;
  }
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

function deepCloneLocalState(value: Record<string, any>): Record<string, any> {
  if (!isPlainRecord(value)) {
    return {};
  }
  const cloned = deepCloneValue(value);
  if (!isPlainRecord(cloned)) {
    return { ...value };
  }
  return cloned;
}

function mergeLocalStateDefaults(
  defaults: Record<string, any>,
  overrides: Record<string, any>,
): Record<string, any> {
  const out = deepCloneLocalState(defaults);
  for (const [key, override] of Object.entries(overrides)) {
    const current = out[key];
    if (isPlainRecord(current) && isPlainRecord(override)) {
      out[key] = mergeLocalStateDefaults(current, override);
      continue;
    }
    out[key] = deepCloneValue(override);
  }
  return out;
}

function sessionRoleLocalStorageKey(sessionId: string, roleId: string): string {
  return `nanocalibur.local.${sessionId}.${roleId}`;
}

function readRoleLocalStateFromStorage(
  sessionId: string,
  roleId: string,
): Record<string, any> {
  let storage: Storage | null = null;
  try {
    storage = window.localStorage;
  } catch {
    return {};
  }
  if (!storage) {
    return {};
  }
  const storageKey = sessionRoleLocalStorageKey(sessionId, roleId);
  try {
    const raw = storage.getItem(storageKey);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return isPlainRecord(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function writeRoleLocalStateToStorage(
  sessionId: string,
  roleId: string,
  localState: Record<string, any>,
): void {
  let storage: Storage | null = null;
  try {
    storage = window.localStorage;
  } catch {
    return;
  }
  if (!storage) {
    return;
  }
  const storageKey = sessionRoleLocalStorageKey(sessionId, roleId);
  try {
    storage.setItem(storageKey, JSON.stringify(localState));
  } catch {
    // Ignore quota/security errors and keep in-memory state.
  }
}

function resolveSessionRoleType(
  spec: Record<string, any>,
  roleId: string,
): string | null {
  const roles = Array.isArray(spec.roles) ? (spec.roles as SessionRoleSpec[]) : [];
  const matched = roles.find((role) => role && role.id === roleId);
  if (!matched || typeof matched.type !== 'string' || !matched.type) {
    return null;
  }
  return matched.type;
}

function resolveRoleLocalDefaults(
  spec: Record<string, any>,
  roleType: string | null,
): Record<string, any> {
  if (!roleType) {
    return {};
  }
  const defaultsByRoleType =
    spec.role_local_defaults && typeof spec.role_local_defaults === 'object'
      ? (spec.role_local_defaults as Record<string, unknown>)
      : {};
  const defaults = defaultsByRoleType[roleType];
  return isPlainRecord(defaults) ? deepCloneLocalState(defaults) : {};
}

function buildRoleLocalBundle(
  spec: Record<string, any>,
  sessionId: string,
  roleId: string,
): RoleLocalBundle {
  const roleType = resolveSessionRoleType(spec, roleId);
  const defaults = resolveRoleLocalDefaults(spec, roleType);
  const stored = readRoleLocalStateFromStorage(sessionId, roleId);
  const localState = mergeLocalStateDefaults(defaults, stored);
  writeRoleLocalStateToStorage(sessionId, roleId, localState);
  return {
    localState,
    roleType,
  };
}

function keyboardTokenAliases(token: string): string[] {
  if (typeof token !== 'string' || token.length === 0) {
    return [];
  }
  const out = new Set<string>();
  const lower = token.toLowerCase();
  out.add(token);
  out.add(lower);

  if (token.length === 1 && /^[a-zA-Z]$/.test(token)) {
    out.add(token.toUpperCase());
    out.add(token.toLowerCase());
    out.add(`Key${token.toUpperCase()}`);
  } else {
    const codeMatch = /^Key([a-zA-Z])$/.exec(token);
    if (codeMatch) {
      const letter = codeMatch[1];
      out.add(letter.toLowerCase());
      out.add(letter.toUpperCase());
      out.add(`Key${letter.toUpperCase()}`);
    }
  }

  if (lower === 'arrowup' || lower === 'up') {
    out.add('ArrowUp');
    out.add('arrowup');
    out.add('up');
  } else if (lower === 'arrowdown' || lower === 'down') {
    out.add('ArrowDown');
    out.add('arrowdown');
    out.add('down');
  } else if (lower === 'arrowleft' || lower === 'left') {
    out.add('ArrowLeft');
    out.add('arrowleft');
    out.add('left');
  } else if (lower === 'arrowright' || lower === 'right') {
    out.add('ArrowRight');
    out.add('arrowright');
    out.add('right');
  } else if (lower === 'space' || lower === 'spacebar' || token === ' ') {
    out.add(' ');
    out.add('Space');
    out.add('space');
    out.add('Spacebar');
  }
  return [...out];
}

function resolveLogicalKeyboardTokens(
  localState: Record<string, any>,
  physicalTokens: string[],
): string[] {
  const keybindsRaw = localState.keybinds;
  if (!keybindsRaw || typeof keybindsRaw !== 'object') {
    return [];
  }
  const keybinds = keybindsRaw as Record<string, unknown>;

  const expandedPhysical = new Set<string>();
  for (const token of physicalTokens) {
    for (const alias of keyboardTokenAliases(token)) {
      expandedPhysical.add(alias.toLowerCase());
    }
  }

  const logical: string[] = [];
  for (const [logicalToken, boundToken] of Object.entries(keybinds)) {
    if (typeof logicalToken !== 'string' || logicalToken.length === 0) {
      continue;
    }
    if (typeof boundToken !== 'string' || boundToken.length === 0) {
      continue;
    }
    const aliases = keyboardTokenAliases(boundToken).map((item) => item.toLowerCase());
    if (aliases.some((alias) => expandedPhysical.has(alias))) {
      logical.push(logicalToken);
    }
  }
  return uniqueStrings(logical);
}

class SessionSnapshotRenderer {
  private readonly canvas: HTMLCanvasElement;
  private readonly animation: AnimationSystem;
  private readonly assets: AssetStore;
  private readonly renderer: CanvasRenderer;
  private readonly fallbackInterfaceHtml: string;
  private readonly interfaceOverlays = new Map<
    string,
    {
      overlay: InterfaceOverlay;
      html: string;
      rectKey: string;
    }
  >();
  private localState: Record<string, any> = {};
  private ready = false;
  private latestState: InterpreterState | null = null;
  private latestProjectionState: InterpreterState | null = null;
  private latestSnapshotAtMs = 0;
  private readonly smoothedPositionsByUid = new Map<string, { x: number; y: number }>();
  private readonly smoothedCameraPositionsById = new Map<string, { x: number; y: number }>();
  private lastRenderAtMs = 0;
  private latestStateRevision = 0;
  private localStateRevision = 0;
  private lastOverlayStateRevision = -1;
  private lastOverlayLocalRevision = -1;

  constructor(
    canvas: HTMLCanvasElement,
    options: CanvasHostOptions,
    interfaceHtml: string,
  ) {
    this.canvas = canvas;
    this.assets = new AssetStore(options);
    this.animation = new AnimationSystem(options, () => undefined);
    this.renderer = new CanvasRenderer(canvas, options, this.assets, this.animation);
    this.fallbackInterfaceHtml = interfaceHtml;
  }

  async start(): Promise<void> {
    await this.assets.preload();
    this.ready = true;
    this.renderLoop();
  }

  render(snapshot: SessionSnapshot): void {
    this.latestState = (snapshot.state || {}) as InterpreterState;
    this.latestSnapshotAtMs = performance.now();
    this.latestStateRevision += 1;
  }

  setLocalState(nextLocalState: Record<string, any>): void {
    this.localState = deepCloneLocalState(nextLocalState);
    this.localStateRevision += 1;
  }

  consumeInterfaceButtonPhases(): {
    begin: InterfaceButtonEvent[];
    on: InterfaceButtonEvent[];
    end: InterfaceButtonEvent[];
  } {
    const begin: InterfaceButtonEvent[] = [];
    const on: InterfaceButtonEvent[] = [];
    const end: InterfaceButtonEvent[] = [];
    for (const entry of this.interfaceOverlays.values()) {
      const phases = entry.overlay.consumeButtonPhases();
      begin.push(...phases.begin);
      on.push(...phases.on);
      end.push(...phases.end);
    }
    return { begin, on, end };
  }

  projectScreenToWorld(screenX: number, screenY: number): {
    localX: number;
    localY: number;
    worldX: number;
    worldY: number;
    viewId: string;
  } | null {
    const state = this.latestProjectionState || this.latestState;
    if (!state) {
      return null;
    }
    return this.renderer.projectScreenToWorld(
      state,
      (state.map || null) as MapSpec | null,
      screenX,
      screenY,
    );
  }

  private renderLoop = (): void => {
    if (!this.ready) {
      return;
    }
    this.renderFrame();
    window.requestAnimationFrame(this.renderLoop);
  };

  private renderFrame(): void {
    const state = this.buildInterpolatedState();
    if (!state) {
      return;
    }
    const actors = Array.isArray(state.actors)
      ? (state.actors as ActorState[])
      : [];
    this.animation.update(actors);
    this.renderer.render(
      state,
      (state.map || null) as MapSpec | null,
    );
    this.latestProjectionState = state;
    if (
      this.latestStateRevision !== this.lastOverlayStateRevision
      || this.localStateRevision !== this.lastOverlayLocalRevision
    ) {
      this.syncInterfaceOverlays(this.latestState || state);
      this.lastOverlayStateRevision = this.latestStateRevision;
      this.lastOverlayLocalRevision = this.localStateRevision;
    }
  }

  private buildInterpolatedState(): InterpreterState | null {
    if (!this.latestState) {
      return null;
    }
    const nowMs = performance.now();
    const elapsedSeconds = Math.max(
      0,
      Math.min(0.12, (nowMs - this.latestSnapshotAtMs) / 1000),
    );
    const renderDeltaMs =
      this.lastRenderAtMs > 0
        ? Math.max(1, Math.min(100, nowMs - this.lastRenderAtMs))
        : 16.67;
    this.lastRenderAtMs = nowMs;
    const smoothAlpha = Math.min(0.4, Math.max(0.2, renderDeltaMs / 80));

    const sourceActors = Array.isArray(this.latestState.actors)
      ? (this.latestState.actors as ActorState[])
      : [];
    const aliveUids = new Set<string>();
    const sourceActorsByUid = new Map<string, ActorState>();
    for (const actor of sourceActors) {
      if (typeof actor.uid === 'string' && actor.uid.length > 0) {
        aliveUids.add(actor.uid);
        sourceActorsByUid.set(actor.uid, actor);
      }
    }
    const projectedByUid = new Map<string, { x: number; y: number }>();
    const visiting = new Set<string>();
    const projectActor = (actor: ActorState): { x: number; y: number } => {
      const uid = typeof actor.uid === 'string' ? actor.uid : '';
      if (uid.length > 0) {
        const cached = projectedByUid.get(uid);
        if (cached) {
          return cached;
        }
        if (visiting.has(uid)) {
          return {
            x: typeof actor.x === 'number' ? actor.x : 0,
            y: typeof actor.y === 'number' ? actor.y : 0,
          };
        }
        visiting.add(uid);
      }

      const x = typeof actor.x === 'number' ? actor.x : 0;
      const y = typeof actor.y === 'number' ? actor.y : 0;
      const vx = typeof actor.vx === 'number' ? actor.vx : 0;
      const vy = typeof actor.vy === 'number' ? actor.vy : 0;
      let projectedX = x + vx * elapsedSeconds;
      let projectedY = y + vy * elapsedSeconds;

      const parentUid = typeof actor.parent === 'string' ? actor.parent : '';
      const hasOwnVelocity = Math.abs(vx) > 1e-6 || Math.abs(vy) > 1e-6;
      if (parentUid.length > 0 && !hasOwnVelocity) {
        const parent = sourceActorsByUid.get(parentUid);
        if (parent) {
          const parentProjected = projectActor(parent);
          const parentX = typeof parent.x === 'number' ? parent.x : 0;
          const parentY = typeof parent.y === 'number' ? parent.y : 0;
          projectedX += parentProjected.x - parentX;
          projectedY += parentProjected.y - parentY;
        }
      }

      const projected = { x: projectedX, y: projectedY };
      if (uid.length > 0) {
        projectedByUid.set(uid, projected);
        visiting.delete(uid);
      }
      return projected;
    };
    const actors = sourceActors.map((actor) => {
      const cloned = { ...actor };
      const projected = projectActor(actor);
      const uid = typeof actor.uid === 'string' ? actor.uid : '';
      const shouldSmooth = this.actorPositionSmoothingEnabled(actor);
      if (!uid) {
        cloned.x = projected.x;
        cloned.y = projected.y;
        return cloned;
      }

      const previousSmoothed = this.smoothedPositionsByUid.get(uid);
      let nextX = projected.x;
      let nextY = projected.y;
      if (previousSmoothed && shouldSmooth) {
        const dx = projected.x - previousSmoothed.x;
        const dy = projected.y - previousSmoothed.y;
        const distanceSq = dx * dx + dy * dy;
        if (distanceSq <= 128 * 128) {
          nextX = previousSmoothed.x + dx * smoothAlpha;
          nextY = previousSmoothed.y + dy * smoothAlpha;
        }
      }
      this.smoothedPositionsByUid.set(uid, { x: nextX, y: nextY });
      cloned.x = nextX;
      cloned.y = nextY;
      return cloned;
    });
    for (const cachedUid of Array.from(this.smoothedPositionsByUid.keys())) {
      if (!aliveUids.has(cachedUid)) {
        this.smoothedPositionsByUid.delete(cachedUid);
      }
    }
    const nextState = {
      ...this.latestState,
      actors,
    } as InterpreterState;

    const activeCameraKeys = new Set<string>();
    const cameraDeltaByKey = new Map<string, { x: number; y: number }>();
    const sourceCameras =
      this.latestState && this.latestState.cameras && typeof this.latestState.cameras === 'object'
        ? (this.latestState.cameras as Record<string, any>)
        : null;
    if (sourceCameras) {
      const nextCameras: Record<string, any> = {};
      for (const [cameraName, cameraValue] of Object.entries(sourceCameras)) {
        if (!cameraValue || typeof cameraValue !== 'object') {
          continue;
        }
        const cameraState = cameraValue as Record<string, any>;
        const key = `camera:${cameraName}`;
        activeCameraKeys.add(key);
        const smoothed = this.resolveSmoothedCameraPosition(
          key,
          cameraState,
          actors,
          smoothAlpha,
        );
        if (
          smoothed
          && typeof cameraState.x === 'number'
          && Number.isFinite(cameraState.x)
          && typeof cameraState.y === 'number'
          && Number.isFinite(cameraState.y)
        ) {
          cameraDeltaByKey.set(key, {
            x: smoothed.x - cameraState.x,
            y: smoothed.y - cameraState.y,
          });
        }
        nextCameras[cameraName] = smoothed
          ? {
              ...cameraState,
              x: smoothed.x,
              y: smoothed.y,
            }
          : { ...cameraState };
      }
      nextState.cameras = nextCameras;
    }

    if (nextState.camera && typeof nextState.camera === 'object') {
      const fallbackCamera = nextState.camera as Record<string, any>;
      const namedCameraId =
        typeof fallbackCamera.name === 'string' && fallbackCamera.name.length > 0
          ? fallbackCamera.name
          : '';
      let smoothedFallback: { x: number; y: number } | null = null;

      if (
        namedCameraId
        && nextState.cameras
        && typeof nextState.cameras === 'object'
        && !Array.isArray(nextState.cameras)
      ) {
        const namedCamera = (nextState.cameras as Record<string, any>)[namedCameraId];
        if (namedCamera && typeof namedCamera === 'object') {
          const cameraX = typeof namedCamera.x === 'number' ? namedCamera.x : null;
          const cameraY = typeof namedCamera.y === 'number' ? namedCamera.y : null;
          if (cameraX !== null && cameraY !== null) {
            smoothedFallback = { x: cameraX, y: cameraY };
          }
        }
      }

      if (!smoothedFallback) {
        const key = 'camera:__primary__';
        activeCameraKeys.add(key);
        smoothedFallback = this.resolveSmoothedCameraPosition(
          key,
          fallbackCamera,
          actors,
          smoothAlpha,
        );
        if (
          smoothedFallback
          && typeof fallbackCamera.x === 'number'
          && Number.isFinite(fallbackCamera.x)
          && typeof fallbackCamera.y === 'number'
          && Number.isFinite(fallbackCamera.y)
        ) {
          cameraDeltaByKey.set(key, {
            x: smoothedFallback.x - fallbackCamera.x,
            y: smoothedFallback.y - fallbackCamera.y,
          });
        }
      }
      if (smoothedFallback) {
        nextState.camera = {
          ...fallbackCamera,
          x: smoothedFallback.x,
          y: smoothedFallback.y,
        };
      }
    }

    this.applyCameraLockDeltaToActors(actors, cameraDeltaByKey);
    this.clearStaleSmoothedCameraKeys(activeCameraKeys);
    return nextState;
  }

  private actorPositionSmoothingEnabled(actor: ActorState): boolean {
    const actorRecord = actor as Record<string, unknown>;
    if (actorRecord.position_smoothing === false || actorRecord.positionSmoothing === false) {
      return false;
    }
    if (actorRecord.interpolate_position === false || actorRecord.interpolatePosition === false) {
      return false;
    }
    return true;
  }

  private actorCameraLockEnabled(actor: ActorState): boolean {
    const actorRecord = actor as Record<string, unknown>;
    if (actorRecord.camera_locked === true || actorRecord.cameraLocked === true) {
      return true;
    }
    return false;
  }

  private resolveSmoothedCameraPosition(
    cameraKey: string,
    cameraState: Record<string, any>,
    actors: ActorState[],
    smoothAlpha: number,
  ): { x: number; y: number } | null {
    let targetX = typeof cameraState.x === 'number' ? cameraState.x : null;
    let targetY = typeof cameraState.y === 'number' ? cameraState.y : null;
    const targetUid =
      typeof cameraState.target_uid === 'string' && cameraState.target_uid.length > 0
        ? cameraState.target_uid
        : null;
    if (targetUid) {
      const target = actors.find((actor) => actor.uid === targetUid);
      if (target && typeof target.x === 'number' && typeof target.y === 'number') {
        const offsetX = typeof cameraState.offset_x === 'number' ? cameraState.offset_x : 0;
        const offsetY = typeof cameraState.offset_y === 'number' ? cameraState.offset_y : 0;
        targetX = target.x + offsetX;
        targetY = target.y + offsetY;
      }
    }
    if (targetX === null || targetY === null) {
      return null;
    }
    if (!Number.isFinite(targetX) || !Number.isFinite(targetY)) {
      return null;
    }

    const smoothingDisabled =
      cameraState.interpolate_camera === false
      || cameraState.interpolateCamera === false
      || cameraState.interpolate === false
      || cameraState.position_smoothing === false
      || cameraState.positionSmoothing === false;
    const shouldSmooth = !smoothingDisabled;
    if (!shouldSmooth) {
      this.smoothedCameraPositionsById.set(cameraKey, { x: targetX, y: targetY });
      return { x: targetX, y: targetY };
    }

    const previous = this.smoothedCameraPositionsById.get(cameraKey);
    const cameraAlpha = Math.min(0.85, Math.max(0.45, smoothAlpha * 2.0));
    let nextX = targetX;
    let nextY = targetY;
    if (previous) {
      const dx = targetX - previous.x;
      const dy = targetY - previous.y;
      const distanceSq = dx * dx + dy * dy;
      if (distanceSq <= 512 * 512) {
        nextX = previous.x + (dx * cameraAlpha);
        nextY = previous.y + (dy * cameraAlpha);
      }
    }
    this.smoothedCameraPositionsById.set(cameraKey, { x: nextX, y: nextY });
    return { x: nextX, y: nextY };
  }

  private clearStaleSmoothedCameraKeys(activeKeys: Set<string>): void {
    for (const key of Array.from(this.smoothedCameraPositionsById.keys())) {
      if (!activeKeys.has(key)) {
        this.smoothedCameraPositionsById.delete(key);
      }
    }
  }

  private resolveViewCameraKeyById(state: InterpreterState | null): Map<string, string> {
    const out = new Map<string, string>();
    if (!state || !state.scene || typeof state.scene !== 'object') {
      return out;
    }
    const sceneRecord = state.scene as unknown as Record<string, unknown>;
    const rawViews = Array.isArray(sceneRecord.views)
      ? (sceneRecord.views as Array<Record<string, unknown>>)
      : [];
    for (const entry of rawViews) {
      if (!entry || typeof entry !== 'object') {
        continue;
      }
      const viewId = typeof entry.id === 'string' ? entry.id : '';
      if (!viewId) {
        continue;
      }
      const cameraName = typeof entry.camera_name === 'string' ? entry.camera_name : '';
      if (cameraName) {
        out.set(viewId, `camera:${cameraName}`);
      } else {
        out.set(viewId, 'camera:__primary__');
      }
    }
    return out;
  }

  private applyCameraLockDeltaToActors(
    actors: ActorState[],
    cameraDeltaByKey: Map<string, { x: number; y: number }>,
  ): void {
    if (actors.length <= 0 || cameraDeltaByKey.size <= 0) {
      return;
    }
    const viewCameraKeyById = this.resolveViewCameraKeyById(this.latestState);
    for (const actor of actors) {
      if (!this.actorCameraLockEnabled(actor)) {
        continue;
      }
      if (typeof actor.x !== 'number' || typeof actor.y !== 'number') {
        continue;
      }
      const actorRecord = actor as Record<string, unknown>;
      const actorViewId = typeof actorRecord.view_id === 'string'
        ? actorRecord.view_id
        : typeof actorRecord.viewId === 'string'
          ? actorRecord.viewId
          : '';
      const cameraKey = actorViewId
        ? (viewCameraKeyById.get(actorViewId) || 'camera:__primary__')
        : 'camera:__primary__';
      const delta = cameraDeltaByKey.get(cameraKey) || cameraDeltaByKey.get('camera:__primary__');
      if (!delta) {
        continue;
      }
      actor.x = actor.x + delta.x;
      actor.y = actor.y + delta.y;
    }
  }

  private buildInterfaceGlobals(state: InterpreterState): Record<string, any> {
    const globals =
      state.globals && typeof state.globals === 'object'
        ? { ...(state.globals as Record<string, any>) }
        : {};
    const stateRecord = state as Record<string, any>;
    const selfState = stateRecord.self;
    globals.role =
      selfState && typeof selfState === 'object'
        ? { ...(selfState as Record<string, any>) }
        : {};
    globals.local = deepCloneLocalState(this.localState);
    globals.__actors_count = Array.isArray(state.actors) ? state.actors.length : 0;
    globals.__scene_elapsed =
      state.scene && typeof state.scene.elapsed === 'number'
        ? state.scene.elapsed
        : 0;
    return globals;
  }

  private resolveActiveInterfaceBindings(state: InterpreterState): Array<{
    key: string;
    html: string;
    viewId: string | null;
    rect: InterfaceOverlayRect | null;
  }> {
    const scene = state.scene as Record<string, any> | null;
    const fallbackHtml =
      scene && typeof scene.interfaceHtml === 'string'
        ? scene.interfaceHtml
        : this.fallbackInterfaceHtml;
    const rawBindings = Array.isArray(scene?.interfaces)
      ? (scene?.interfaces as SceneInterfaceBinding[])
      : [];
    const bindings = rawBindings.length > 0
      ? rawBindings
      : fallbackHtml.trim().length > 0
        ? [{ html: fallbackHtml, role_id: null, view_id: null }]
        : [];

    const stateRecord = state as Record<string, any>;
    const selfState = stateRecord.self as Record<string, unknown> | null;
    const selfRoleId =
      selfState && typeof selfState.id === 'string'
        ? (selfState.id as string)
        : null;

    const viewRects = new Map<string, InterfaceOverlayRect>();
    for (const view of this.renderer.getRenderViews(state, (state.map || null) as MapSpec | null)) {
      viewRects.set(view.id, {
        x: view.x,
        y: view.y,
        width: view.width,
        height: view.height,
      });
    }

    const desired = new Map<string, {
      key: string;
      html: string;
      viewId: string | null;
      rect: InterfaceOverlayRect | null;
    }>();
    for (const binding of bindings) {
      const html = typeof binding.html === 'string' ? binding.html : '';
      if (html.trim().length === 0) {
        continue;
      }
      const roleId =
        typeof binding.role_id === 'string' && binding.role_id ? binding.role_id : null;
      const viewId =
        typeof binding.view_id === 'string' && binding.view_id ? binding.view_id : null;
      if (roleId && selfRoleId && roleId !== selfRoleId) {
        continue;
      }
      const rect = viewId ? (viewRects.get(viewId) || null) : null;
      if (viewId && !rect) {
        continue;
      }
      const key = `${roleId || ''}::${viewId || ''}`;
      desired.set(key, {
        key,
        html,
        viewId,
        rect,
      });
    }
    return Array.from(desired.values());
  }

  private syncInterfaceOverlays(state: InterpreterState): void {
    const desired = this.resolveActiveInterfaceBindings(state);
    const desiredKeys = new Set(desired.map((item) => item.key));

    for (const [key, existing] of this.interfaceOverlays.entries()) {
      if (!desiredKeys.has(key)) {
        existing.overlay.destroy();
        this.interfaceOverlays.delete(key);
      }
    }

    for (const target of desired) {
      const existing = this.interfaceOverlays.get(target.key);
      const rectKey = target.rect
        ? `${target.rect.x},${target.rect.y},${target.rect.width},${target.rect.height}`
        : 'full';
      if (!existing) {
        const overlay = new InterfaceOverlay(
          this.canvas,
          target.html,
          target.viewId,
          target.rect,
        );
        this.interfaceOverlays.set(target.key, {
          overlay,
          html: target.html,
          rectKey,
        });
        continue;
      }
      if (existing.html !== target.html) {
        existing.overlay.setHtml(target.html);
        existing.html = target.html;
      }
      if (existing.rectKey !== rectKey) {
        existing.overlay.setRect(target.rect);
        existing.rectKey = rectKey;
      }
    }

    const globals = this.buildInterfaceGlobals(state);
    for (const entry of this.interfaceOverlays.values()) {
      entry.overlay.updateGlobals(globals);
    }
  }
}

const DEFAULT_CANVAS_OPTIONS: CanvasHostOptions = {
  width: 960,
  height: 640,
  renderScale: 0.8,
  backgroundColor: '#121826',
  tileColor: '#303a52',
  pixelated: true,
  showHud: true,
};

function requireCanvas(canvasId: string): HTMLCanvasElement {
  const element = document.getElementById(canvasId);
  if (!(element instanceof HTMLCanvasElement)) {
    throw new Error(`Canvas element '#${canvasId}' was not found.`);
  }
  return element;
}

function requireSymbolicPanel(panelId: string): HTMLElement {
  const element = document.getElementById(panelId);
  if (!(element instanceof HTMLElement)) {
    throw new Error(`Symbolic panel '#${panelId}' was not found.`);
  }
  return element;
}

function parseSessionBrowserConfig(): SessionBrowserConfig {
  const params = new URLSearchParams(window.location.search);
  const mode = (params.get('mode') || '').toLowerCase();
  const inviteToken =
    params.get('inviteToken') ||
    params.get('invite_token') ||
    '';
  const rawBaseUrl =
    params.get('baseUrl') ||
    params.get('base_url') ||
    'http://127.0.0.1:7070';
  return {
    enabled: mode === 'session' || inviteToken.length > 0,
    inviteToken,
    baseUrl: rawBaseUrl.replace(/\/$/, ''),
  };
}

function formatLegend(legend: SymbolicLegendEntry[]): string {
  return legend.map((item) => `${item.symbol}: ${item.description}`).join('\n');
}

function formatSingleSymbolicFrame(
  frame: SymbolicViewFrame,
  options: { includeLegend?: boolean } = {},
): string {
  const includeLegend = options.includeLegend !== false;
  if (!includeLegend) {
    return frame.rows.join('\n');
  }
  const legend = formatLegend(frame.legend || []);
  if (!legend) {
    return frame.rows.join('\n');
  }
  return `${frame.rows.join('\n')}\n\nLegend\n${legend}`;
}

function sortSymbolicViewIds(viewIds: string[]): string[] {
  return [...viewIds].sort((a, b) => {
    const aPriority = a.includes('main') ? 0 : 1;
    const bPriority = b.includes('main') ? 0 : 1;
    if (aPriority !== bPriority) {
      return aPriority - bPriority;
    }
    return a.localeCompare(b);
  });
}

function formatSymbolicFrame(frame: SymbolicFrame): string {
  const viewFrames =
    frame.views && typeof frame.views === 'object'
      ? (frame.views as Record<string, SymbolicViewFrame>)
      : null;
  const viewIds = viewFrames ? Object.keys(viewFrames) : [];
  if (viewIds.length <= 0) {
    return formatSingleSymbolicFrame(frame);
  }

  const primaryRows = frame.rows.join('\n');
  const safeViewFrames = viewFrames || {};
  const sections: string[] = [];
  for (const viewId of sortSymbolicViewIds(viewIds)) {
    const subFrame = safeViewFrames[viewId];
    if (!subFrame || !Array.isArray(subFrame.rows) || !Array.isArray(subFrame.legend)) {
      continue;
    }
    const isPrimary = subFrame.rows.join('\n') === primaryRows;
    const title = isPrimary ? `View ${viewId} (primary)` : `View ${viewId}`;
    sections.push(`${title}\n${formatSingleSymbolicFrame(subFrame)}`);
  }
  if (sections.length <= 0) {
    return formatSingleSymbolicFrame(frame);
  }
  return sections.join('\n\n');
}

function formatSessionSnapshot(snapshot: SessionSnapshot): string {
  const scene = snapshot.state?.scene || {};
  const globals = snapshot.state?.globals || {};
  const header = [
    `Session: ${snapshot.session_id}`,
    `Elapsed: ${scene.elapsed}`,
    `Turn: ${scene.turn}`,
    `Globals: ${JSON.stringify(globals)}`,
    '',
  ].join('\n');
  return `${header}${formatSymbolicFrame(snapshot.frame)}`;
}

function hasSnapshotSceneProgress(
  previous: SessionSnapshot | null,
  next: SessionSnapshot,
): boolean {
  if (!previous) {
    return true;
  }
  const previousScene = previous.state?.scene || {};
  const nextScene = next.state?.scene || {};
  const previousElapsed =
    typeof previousScene.elapsed === 'number' ? previousScene.elapsed : null;
  const nextElapsed =
    typeof nextScene.elapsed === 'number' ? nextScene.elapsed : null;
  if (previousElapsed !== null && nextElapsed !== null) {
    if (nextElapsed > previousElapsed) {
      return true;
    }
    if (nextElapsed < previousElapsed) {
      return false;
    }
  }
  const previousTurn =
    typeof previousScene.turn === 'number' ? previousScene.turn : null;
  const nextTurn =
    typeof nextScene.turn === 'number' ? nextScene.turn : null;
  if (previousTurn !== null && nextTurn !== null) {
    if (nextTurn > previousTurn) {
      return true;
    }
    if (nextTurn < previousTurn) {
      return false;
    }
  }
  if (previousElapsed === null || nextElapsed === null || previousTurn === null || nextTurn === null) {
    return true;
  }
  return false;
}

async function requestJson(
  baseUrl: string,
  path: string,
  method: string,
  payload?: Record<string, any>,
  extraHeaders: Record<string, string> = {},
): Promise<Record<string, any>> {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...extraHeaders,
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });

  const body = await response.text();
  const decoded = body ? JSON.parse(body) : {};
  if (!response.ok) {
    const message = typeof decoded?.error === 'string'
      ? decoded.error
      : `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  if (!decoded || typeof decoded !== 'object') {
    return {};
  }
  return decoded as Record<string, any>;
}

async function fetchSessionStatus(
  baseUrl: string,
  sessionId: string,
): Promise<string | null> {
  const payload = await requestJson(baseUrl, '/sessions', 'GET');
  const sessions = Array.isArray(payload.sessions)
    ? (payload.sessions as SessionSummary[])
    : [];
  const target = sessions.find((entry) => entry?.session_id === sessionId);
  if (!target || typeof target.status !== 'string' || !target.status) {
    return null;
  }
  return target.status;
}

function buildSessionWebSocketUrl(
  baseUrl: string,
  sessionId: string,
  accessToken: string,
): string {
  const normalized = baseUrl.replace(/\/$/, '');
  const httpUrl = new URL(
    `${normalized}/sessions/${encodeURIComponent(sessionId)}/ws`,
  );
  httpUrl.searchParams.set('access_token', accessToken);
  httpUrl.protocol = httpUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  return httpUrl.toString();
}

function readSessionSnapshotFromWebSocketData(raw: unknown): SessionSnapshot | null {
  if (typeof raw !== 'string' || raw.length === 0) {
    return null;
  }
  let decoded: unknown;
  try {
    decoded = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!decoded || typeof decoded !== 'object') {
    return null;
  }
  const record = decoded as Record<string, any>;
  const eventName = typeof record.event === 'string' ? record.event : '';
  if (eventName && eventName !== 'snapshot') {
    return null;
  }
  const payload =
    eventName === 'snapshot' && record.data && typeof record.data === 'object'
      ? (record.data as Record<string, any>)
      : record;
  if (!payload || typeof payload !== 'object') {
    return null;
  }
  if (typeof payload.session_id !== 'string' || !payload.frame || !payload.state) {
    return null;
  }
  return payload as SessionSnapshot;
}

function uniqueStrings(values: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    if (typeof value !== 'string' || value.length === 0 || seen.has(value)) {
      continue;
    }
    seen.add(value);
    out.push(value);
  }
  return out;
}

function buttonEventNames(events: InterfaceButtonEvent[]): string[] {
  return uniqueStrings(
    events
      .map((event) => event.name)
      .filter((name): name is string => typeof name === 'string' && name.length > 0),
  );
}

function mapMouseButton(buttonCode: number): string {
  if (buttonCode === 0) return 'left';
  if (buttonCode === 1) return 'middle';
  if (buttonCode === 2) return 'right';
  return `button_${buttonCode}`;
}

function browserKeyboardTokens(event: KeyboardEvent): string[] {
  const key = typeof event.key === 'string' ? event.key : '';
  const code = typeof event.code === 'string' ? event.code : '';
  const tokens: string[] = [];
  if (key.length > 0) {
    tokens.push(key);
    if (key.length === 1) {
      tokens.push(key.toLowerCase());
      tokens.push(key.toUpperCase());
      if (/^[a-zA-Z]$/.test(key)) {
        tokens.push(`Key${key.toUpperCase()}`);
      }
    }
  }
  if (code.length > 0) {
    tokens.push(code);
  }
  return uniqueStrings(tokens);
}

function keyboardTokensWithLogicalBindings(
  localState: Record<string, any>,
  physicalTokens: string[],
): string[] {
  if (physicalTokens.length === 0) {
    return [];
  }
  const logicalTokens = resolveLogicalKeyboardTokens(localState, physicalTokens);
  return uniqueStrings([...physicalTokens, ...logicalTokens]);
}

async function startSessionBrowserClient(
  canvas: HTMLCanvasElement,
  symbolicPanel: HTMLElement,
  config: SessionBrowserConfig,
): Promise<void> {
  if (!config.inviteToken) {
    throw new Error(
      'Session mode requires inviteToken query param. Example: ?mode=session&baseUrl=http://127.0.0.1:7070&inviteToken=...',
    );
  }

  canvas.width = DEFAULT_CANVAS_OPTIONS.width || 960;
  canvas.height = DEFAULT_CANVAS_OPTIONS.height || 640;
  canvas.style.width = `${canvas.width}px`;
  canvas.style.height = `${canvas.height}px`;

  const joined = await requestJson(config.baseUrl, '/join', 'POST', {
    invite_token: config.inviteToken,
  }) as SessionJoinPayload;

  const sessionId = joined.session_id;
  const accessToken = joined.access_token;
  const sessionSpec = createNanoCaliburInterpreter().getSpec();
  const roleLocal = buildRoleLocalBundle(sessionSpec, sessionId, joined.role_id);
  const rendererOptions = mergeSpecOptions(
    DEFAULT_CANVAS_OPTIONS,
    sessionSpec as Record<string, any>,
  );
  const sessionRenderer = new SessionSnapshotRenderer(
    canvas,
    rendererOptions,
    (() => {
      if (typeof sessionSpec.interface_html === 'string') {
        return sessionSpec.interface_html;
      }
      const byRole = sessionSpec.interfaces_by_role;
      if (
        byRole &&
        typeof byRole === 'object' &&
        typeof (byRole as Record<string, unknown>)[joined.role_id] === 'string'
      ) {
        return (byRole as Record<string, string>)[joined.role_id];
      }
      return '';
    })(),
  );
  sessionRenderer.setLocalState(roleLocal.localState);
  void sessionRenderer.start().catch((error) => {
    console.error('Failed to preload session renderer assets.', error);
  });

  let latestSnapshot: SessionSnapshot | null = null;
  let sessionWarning: string | null = null;
  let lastSymbolicRenderAtMs = 0;
  let lastSymbolicText = '';
  const multiplayerSpec =
    sessionSpec &&
    typeof sessionSpec === 'object' &&
    sessionSpec.multiplayer &&
    typeof sessionSpec.multiplayer === 'object'
      ? (sessionSpec.multiplayer as Record<string, any>)
      : null;
  const configuredTickRate = multiplayerSpec && typeof multiplayerSpec.tick_rate === 'number'
    ? multiplayerSpec.tick_rate
    : 30;
  const normalizedTickRate = Math.max(1, Math.floor(configuredTickRate));

  const renderPanel = (): void => {
    const nowMs = performance.now();
    const shouldRenderSymbolic =
      nowMs - lastSymbolicRenderAtMs >= 100 || !latestSnapshot;
    if (!latestSnapshot) {
      const lines = [
        `Session: ${sessionId}`,
        sessionWarning ? `WARNING: ${sessionWarning}` : '',
        'Waiting for first snapshot...',
      ].filter((line) => line.length > 0);
      const nextText = lines.join('\n');
      if (nextText !== lastSymbolicText) {
        symbolicPanel.textContent = nextText;
        lastSymbolicText = nextText;
      }
      lastSymbolicRenderAtMs = nowMs;
      return;
    }
    if (shouldRenderSymbolic) {
      const warningPrefix = sessionWarning ? `WARNING: ${sessionWarning}\n\n` : '';
      const nextText = `${warningPrefix}${formatSessionSnapshot(latestSnapshot)}`;
      if (nextText !== lastSymbolicText) {
        symbolicPanel.textContent = nextText;
        lastSymbolicText = nextText;
      }
      lastSymbolicRenderAtMs = nowMs;
    }
    sessionRenderer.render(latestSnapshot);
  };

  const renderSnapshot = (snapshot: SessionSnapshot): void => {
    const snapshotServerTick =
      typeof snapshot.server_tick === 'number' && Number.isFinite(snapshot.server_tick)
        ? Math.max(0, Math.floor(snapshot.server_tick))
        : null;
    if (snapshotServerTick !== null) {
      lastAckedServerTick = Math.max(lastAckedServerTick, snapshotServerTick);
    }
    latestSnapshot = snapshot;
    renderPanel();
  };

  const refreshSessionWarning = async (): Promise<void> => {
    try {
      const status = await fetchSessionStatus(config.baseUrl, sessionId);
      if (status && status !== 'running') {
        sessionWarning = (
          `Session status is '${status}'. `
          + `Ask admin to start it: POST /sessions/${sessionId}/start`
        );
      } else {
        sessionWarning = null;
      }
      renderPanel();
    } catch (error) {
      console.warn('Failed to read session status for warning banner.', error);
    }
  };

  renderPanel();
  await refreshSessionWarning();
  const statusPollHandle = window.setInterval(() => {
    void refreshSessionWarning();
  }, 1500);

  let liveTransportActive = false;
  let snapshotPollInFlight = false;
  let snapshotPollFailureCount = 0;
  const snapshotPollMs = Math.max(20, Math.round(1000 / normalizedTickRate));
  const snapshotPollHandle = window.setInterval(() => {
    if (liveTransportActive) {
      return;
    }
    if (snapshotPollInFlight) {
      return;
    }
    snapshotPollInFlight = true;
    void requestJson(
      config.baseUrl,
      `/sessions/${encodeURIComponent(sessionId)}/snapshot?access_token=${encodeURIComponent(accessToken)}`,
      'GET',
      undefined,
      { 'x-role-token': accessToken },
    ).then((payload) => {
      snapshotPollFailureCount = 0;
      if (!payload || typeof payload !== 'object') {
        return;
      }
      const candidate: SessionSnapshot = {
        session_id: typeof payload.session_id === 'string' ? payload.session_id : sessionId,
        frame: (payload.frame || { rows: [], legend: [] }) as SymbolicFrame,
        state: (payload.state || {}) as Record<string, any>,
      };
      if (hasSnapshotSceneProgress(latestSnapshot, candidate)) {
        renderSnapshot(candidate);
      }
    }).catch((error) => {
      // SSE is still the primary path; polling is only a compatibility fallback.
      snapshotPollFailureCount += 1;
      if (snapshotPollFailureCount === 1 || snapshotPollFailureCount % 10 === 0) {
        console.warn('Session snapshot polling fallback failed.', error);
      }
    }).finally(() => {
      snapshotPollInFlight = false;
    });
  }, snapshotPollMs);

  let activeWebSocket: WebSocket | null = null;
  let wsInputSeq = 0;
  let lastAckedServerTick = 0;
  const isWebSocketInputActive = (): boolean => {
    const ws = activeWebSocket as unknown as {
      readyState?: number;
      send?: (value: string) => void;
    } | null;
    return Boolean(ws && ws.readyState === 1 && typeof ws.send === 'function');
  };
  const sendWebSocketInputFrame = (
    keysDown: string[],
    options: {
      buttons?: string[];
      mouseButtons?: string[];
      mousePosition?: { x: number; y: number };
      mouseWorldPosition?: { x: number; y: number };
      mouseViewId?: string;
    } = {},
  ): void => {
    const ws = activeWebSocket as unknown as {
      readyState?: number;
      send?: (value: string) => void;
    } | null;
    if (!ws || ws.readyState !== 1 || typeof ws.send !== 'function') {
      return;
    }
    wsInputSeq += 1;
    const payload = {
      type: 'input',
      seq: wsInputSeq,
      last_acked_server_tick: lastAckedServerTick,
      keys_down: keysDown,
      buttons: options.buttons || [],
      mouse_buttons: options.mouseButtons || [],
      mouse_position: options.mousePosition,
      mouse_world_position: options.mouseWorldPosition,
      mouse_view_id: options.mouseViewId,
    };
    try {
      ws.send(JSON.stringify(payload));
    } catch (error) {
      console.warn('Failed to send websocket input frame.', error);
    }
  };

  const sendCommand = async (command: Record<string, any>): Promise<void> => {
    try {
      const response = await requestJson(
        config.baseUrl,
        `/sessions/${encodeURIComponent(sessionId)}/commands`,
        'POST',
        {
          access_token: accessToken,
          commands: [command],
          tick: false,
        },
      );
      if (response && typeof response === 'object' && response.state && response.frame) {
        const candidate: SessionSnapshot = {
          session_id: sessionId,
          frame: response.frame as SymbolicFrame,
          state: response.state as Record<string, any>,
        };
        if (hasSnapshotSceneProgress(latestSnapshot, candidate)) {
          renderSnapshot({
            session_id: sessionId,
            frame: response.frame as SymbolicFrame,
            state: response.state as Record<string, any>,
          });
        }
      }
    } catch (error) {
      console.error('Failed to send command', error);
    }
  };

  const pendingCommands: Record<string, any>[] = [];
  let commandInFlight = false;
  const flushCommandQueue = async (): Promise<void> => {
    if (commandInFlight) {
      return;
    }
    commandInFlight = true;
    try {
      while (pendingCommands.length > 0) {
        const command = pendingCommands.shift();
        if (!command) {
          continue;
        }
        // eslint-disable-next-line no-await-in-loop
        await sendCommand(command);
      }
    } finally {
      commandInFlight = false;
    }
  };

  const enqueueCommand = (
    command: Record<string, any>,
    options: { dropIfBusy?: boolean } = {},
  ): void => {
    if (options.dropIfBusy && (commandInFlight || pendingCommands.length > 0)) {
      return;
    }
    pendingCommands.push(command);
    void flushCommandQueue();
  };

  const activePhysicalTokensByKey = new Map<string, string[]>();
  const activeInputTokens = (): string[] => {
    const physicalTokens = uniqueStrings(
      Array.from(activePhysicalTokensByKey.values()).flat(),
    );
    return keyboardTokensWithLogicalBindings(roleLocal.localState, physicalTokens);
  };

  const keyIdentity = (event: KeyboardEvent): string => {
    if (typeof event.code === 'string' && event.code.length > 0) {
      return event.code;
    }
    if (typeof event.key === 'string' && event.key.length > 0) {
      return event.key;
    }
    return '';
  };

  const mouseDown = new Set<string>();
  const mouseBeginEvents: string[] = [];
  const mouseEndEvents: string[] = [];
  let mousePosition = { x: 0, y: 0 };
  let mouseWorldPosition = { x: 0, y: 0 };
  let mouseViewId = '';

  const updateMousePosition = (event: MouseEvent): void => {
    const rect = canvas.getBoundingClientRect();
    const screenX = event.clientX - rect.left;
    const screenY = event.clientY - rect.top;
    const projection = sessionRenderer.projectScreenToWorld(screenX, screenY);
    if (projection) {
      mousePosition = {
        x: projection.localX,
        y: projection.localY,
      };
      mouseWorldPosition = {
        x: projection.worldX,
        y: projection.worldY,
      };
      mouseViewId = projection.viewId;
      return;
    }
    mousePosition = {
      x: screenX,
      y: screenY,
    };
    mouseWorldPosition = {
      x: screenX,
      y: screenY,
    };
    mouseViewId = '';
  };

  const consumeMousePhases = (): { begin: string[]; on: string[]; end: string[] } => {
    const begin = uniqueStrings(mouseBeginEvents);
    const end = uniqueStrings(mouseEndEvents);
    mouseBeginEvents.length = 0;
    mouseEndEvents.length = 0;
    const on = uniqueStrings(Array.from(mouseDown.values()));
    return { begin, on, end };
  };

  const sendReleaseForAllPressedInputs = (): void => {
    const physicalTokens = uniqueStrings(
      Array.from(activePhysicalTokensByKey.values()).flat(),
    );
    if (physicalTokens.length > 0) {
      activePhysicalTokensByKey.clear();
    }
    const mouseButtonsDown = Array.from(mouseDown.values());
    for (const button of mouseButtonsDown) {
      mouseEndEvents.push(button);
    }
    mouseDown.clear();

    const endTokens = physicalTokens.length > 0
      ? keyboardTokensWithLogicalBindings(roleLocal.localState, physicalTokens)
      : [];
    if (isWebSocketInputActive()) {
      sendWebSocketInputFrame([], {
        buttons: [],
        mouseButtons: [],
        mousePosition,
        mouseWorldPosition,
        mouseViewId,
      });
      return;
    }
    if (endTokens.length === 0 && mouseButtonsDown.length === 0) {
      return;
    }
    const command: Record<string, any> = {
      kind: 'input',
    };
    if (endTokens.length > 0) {
      command.keyboard = { end: endTokens };
    }
    if (mouseButtonsDown.length > 0) {
      command.mouse = { end: uniqueStrings(mouseButtonsDown) };
      command.mousePosition = mousePosition;
      command.mouseWorldPosition = mouseWorldPosition;
      command.mouseViewId = mouseViewId;
    }
    enqueueCommand(command);
  };

  const handleKeyDown = (event: KeyboardEvent): void => {
    if (event.repeat) {
      return;
    }
    const keyId = keyIdentity(event);
    if (!keyId) {
      return;
    }
    const physicalTokens = browserKeyboardTokens(event);
    if (physicalTokens.length === 0) {
      return;
    }
    activePhysicalTokensByKey.set(keyId, physicalTokens);
    const beginTokens = keyboardTokensWithLogicalBindings(roleLocal.localState, physicalTokens);
    const onTokens = activeInputTokens();
    const keyboardPayload: Record<string, string[]> = {};
    if (beginTokens.length > 0) {
      keyboardPayload.begin = beginTokens;
    }
    if (onTokens.length > 0) {
      keyboardPayload.on = onTokens;
    }
    if (Object.keys(keyboardPayload).length === 0) {
      return;
    }
    if (event.key.startsWith('Arrow') || event.key === ' ') {
      event.preventDefault();
    }
    if (isWebSocketInputActive()) {
      return;
    }
    enqueueCommand({
      kind: 'input',
      keyboard: keyboardPayload,
    });
  };

  const handleKeyUp = (event: KeyboardEvent): void => {
    const keyId = keyIdentity(event);
    const releasedPhysicalTokens = keyId
      ? (activePhysicalTokensByKey.get(keyId) || browserKeyboardTokens(event))
      : browserKeyboardTokens(event);
    if (keyId) {
      activePhysicalTokensByKey.delete(keyId);
    }
    const endTokens = keyboardTokensWithLogicalBindings(roleLocal.localState, releasedPhysicalTokens);
    const onTokens = activeInputTokens();
    const keyboardPayload: Record<string, string[]> = {};
    if (endTokens.length > 0) {
      keyboardPayload.end = endTokens;
    }
    if (onTokens.length > 0) {
      keyboardPayload.on = onTokens;
    }
    if (Object.keys(keyboardPayload).length === 0) {
      return;
    }
    if (event.key.startsWith('Arrow') || event.key === ' ') {
      event.preventDefault();
    }
    if (isWebSocketInputActive()) {
      return;
    }
    enqueueCommand({
      kind: 'input',
      keyboard: keyboardPayload,
    });
  };

  const handleMouseDown = (event: MouseEvent): void => {
    updateMousePosition(event);
    const button = mapMouseButton(event.button);
    if (!mouseDown.has(button)) {
      mouseDown.add(button);
      mouseBeginEvents.push(button);
    }
    if (event.button === 2) {
      event.preventDefault();
    }
    if (isWebSocketInputActive()) {
      return;
    }
    enqueueCommand({
      kind: 'input',
      mouse: {
        begin: [button],
        on: uniqueStrings(Array.from(mouseDown.values())),
      },
      mousePosition,
      mouseWorldPosition,
      mouseViewId,
    });
  };

  const handleMouseUp = (event: MouseEvent): void => {
    updateMousePosition(event);
    const button = mapMouseButton(event.button);
    if (mouseDown.has(button)) {
      mouseDown.delete(button);
      mouseEndEvents.push(button);
    }
    if (event.button === 2) {
      event.preventDefault();
    }
    if (isWebSocketInputActive()) {
      return;
    }
    enqueueCommand({
      kind: 'input',
      mouse: {
        on: uniqueStrings(Array.from(mouseDown.values())),
        end: [button],
      },
      mousePosition,
      mouseWorldPosition,
      mouseViewId,
    });
  };

  const handleMouseMove = (event: MouseEvent): void => {
    updateMousePosition(event);
    if (isWebSocketInputActive()) {
      return;
    }
    if (mouseDown.size <= 0) {
      return;
    }
    enqueueCommand(
      {
        kind: 'input',
        mouse: {
          on: uniqueStrings(Array.from(mouseDown.values())),
        },
        mousePosition,
        mouseWorldPosition,
        mouseViewId,
      },
      { dropIfBusy: true },
    );
  };

  const handleContextMenu = (event: MouseEvent): void => {
    event.preventDefault();
  };

  const handleVisibilityChange = (): void => {
    if (document.visibilityState !== 'visible') {
      sendReleaseForAllPressedInputs();
    }
  };

  window.addEventListener('keydown', handleKeyDown);
  window.addEventListener('keyup', handleKeyUp);
  window.addEventListener('mousedown', handleMouseDown, { passive: false });
  window.addEventListener('mouseup', handleMouseUp, { passive: false });
  window.addEventListener('mousemove', handleMouseMove);
  window.addEventListener('contextmenu', handleContextMenu);
  window.addEventListener('blur', sendReleaseForAllPressedInputs);
  document.addEventListener('visibilitychange', handleVisibilityChange);

  const inputPulseMs = Math.max(
    20,
    Math.round(1000 / normalizedTickRate),
  );
  const inputPulseHandle = window.setInterval(() => {
    const onTokens = activeInputTokens();
    const mousePhases = consumeMousePhases();
    const uiButtonPhases = sessionRenderer.consumeInterfaceButtonPhases();
    if (isWebSocketInputActive()) {
      // Fixed-rate protocol: send down-sets; include begin-edges so short taps/clicks are not lost.
      sendWebSocketInputFrame(onTokens, {
        buttons: buttonEventNames([...uiButtonPhases.on, ...uiButtonPhases.begin]),
        mouseButtons: uniqueStrings([...mousePhases.on, ...mousePhases.begin]),
        mousePosition,
        mouseWorldPosition,
        mouseViewId,
      });
      return;
    }
    const hasMousePhases =
      mousePhases.begin.length > 0
      || mousePhases.on.length > 0
      || mousePhases.end.length > 0;
    const hasUiButtonPhases =
      uiButtonPhases.begin.length > 0
      || uiButtonPhases.on.length > 0
      || uiButtonPhases.end.length > 0;
    if (!hasMousePhases && !hasUiButtonPhases && onTokens.length === 0) {
      return;
    }
    const command: Record<string, any> = { kind: 'input' };
    if (onTokens.length > 0) {
      command.keyboard = { on: onTokens };
    }
    if (hasMousePhases) {
      command.mouse = mousePhases;
      command.mousePosition = mousePosition;
      command.mouseWorldPosition = mouseWorldPosition;
      command.mouseViewId = mouseViewId;
    }
    if (hasUiButtonPhases) {
      command.uiButtons = {
        begin: buttonEventNames(uiButtonPhases.begin),
        on: buttonEventNames(uiButtonPhases.on),
        end: buttonEventNames(uiButtonPhases.end),
      };
    }
    const hasEdge =
      mousePhases.begin.length > 0
      || mousePhases.end.length > 0
      || uiButtonPhases.begin.length > 0
      || uiButtonPhases.end.length > 0;
    enqueueCommand(
      command,
      { dropIfBusy: !hasEdge },
    );
  }, inputPulseMs);

  try {
    const consumeWebSocketStream = async (): Promise<void> => {
      if (typeof WebSocket !== 'function') {
        throw new Error('WebSocket API is not available.');
      }
      const wsUrl = buildSessionWebSocketUrl(config.baseUrl, sessionId, accessToken);
      await new Promise<void>((resolve, reject) => {
        const ws = new WebSocket(wsUrl);
        activeWebSocket = ws;
        let opened = false;
        let settled = false;

        const fail = (error: Error): void => {
          if (settled) {
            return;
          }
          settled = true;
          liveTransportActive = false;
          activeWebSocket = null;
          reject(error);
        };

        ws.onopen = () => {
          opened = true;
          liveTransportActive = true;
          sendWebSocketInputFrame(activeInputTokens(), {
            buttons: [],
            mouseButtons: uniqueStrings(Array.from(mouseDown.values())),
            mousePosition,
            mouseWorldPosition,
            mouseViewId,
          });
        };

        ws.onmessage = (event) => {
          if (typeof event.data !== 'string') {
            return;
          }
          const snapshot = readSessionSnapshotFromWebSocketData(event.data);
          if (!snapshot) {
            return;
          }
          if (hasSnapshotSceneProgress(latestSnapshot, snapshot)) {
            renderSnapshot(snapshot);
          }
        };

        ws.onerror = () => {
          if (!opened) {
            fail(new Error('WebSocket handshake failed.'));
            return;
          }
          console.warn('WebSocket session stream emitted an error.');
        };

        ws.onclose = (event) => {
          if (settled) {
            return;
          }
          settled = true;
          liveTransportActive = false;
          activeWebSocket = null;
          const suffix = typeof event.code === 'number' ? ` (code=${event.code})` : '';
          if (!opened) {
            reject(new Error(`WebSocket handshake failed${suffix}.`));
            return;
          }
          reject(new Error(`WebSocket stream closed${suffix}.`));
        };
      });
    };

    const consumeSseStream = async (): Promise<void> => {
      const streamResponse = await fetch(
        `${config.baseUrl}/sessions/${encodeURIComponent(sessionId)}/stream?access_token=${encodeURIComponent(accessToken)}`,
        {
          method: 'GET',
          headers: {
            Accept: 'text/event-stream',
            'x-role-token': accessToken,
          },
        },
      );
      if (!streamResponse.ok || !streamResponse.body) {
        const text = await streamResponse.text();
        throw new Error(text || `Session stream failed: ${streamResponse.status}`);
      }

      liveTransportActive = true;
      const decoder = new TextDecoder('utf-8');
      let sseBuffer = '';
      const reader = streamResponse.body.getReader();
      try {
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) {
            break;
          }
          sseBuffer += decoder.decode(chunk.value, { stream: true });
          sseBuffer = sseBuffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
          while (true) {
            const split = sseBuffer.indexOf('\n\n');
            if (split < 0) {
              break;
            }
            const rawEvent = sseBuffer.slice(0, split);
            sseBuffer = sseBuffer.slice(split + 2);

            const lines = rawEvent.split('\n');
            let eventName = '';
            let dataPayload = '';
            for (const line of lines) {
              if (line.startsWith('event:')) {
                eventName = line.slice('event:'.length).trim();
              } else if (line.startsWith('data:')) {
                if (dataPayload.length > 0) {
                  dataPayload += '\n';
                }
                dataPayload += line.slice('data:'.length).trim();
              }
            }
            if (eventName !== 'snapshot' || !dataPayload) {
              continue;
            }
            try {
              const snapshot = JSON.parse(dataPayload) as SessionSnapshot;
              if (hasSnapshotSceneProgress(latestSnapshot, snapshot)) {
                renderSnapshot(snapshot);
              }
            } catch (error) {
              console.error('Invalid session snapshot payload', error);
            }
          }
        }
      } finally {
        liveTransportActive = false;
      }
    };

    try {
      await consumeWebSocketStream();
    } catch (webSocketError) {
      console.warn('WebSocket stream unavailable; falling back to SSE.', webSocketError);
      await consumeSseStream();
    }
  } finally {
    liveTransportActive = false;
    const wsForCleanup = activeWebSocket as unknown as {
      readyState?: number;
      close?: () => void;
    } | null;
    if (
      wsForCleanup
      && typeof wsForCleanup.close === 'function'
      && (wsForCleanup.readyState === 0 || wsForCleanup.readyState === 1)
    ) {
      wsForCleanup.close();
    }
    window.clearInterval(statusPollHandle);
    window.clearInterval(snapshotPollHandle);
    window.clearInterval(inputPulseHandle);
    sendReleaseForAllPressedInputs();
    window.removeEventListener('keydown', handleKeyDown);
    window.removeEventListener('keyup', handleKeyUp);
    window.removeEventListener('mousedown', handleMouseDown);
    window.removeEventListener('mouseup', handleMouseUp);
    window.removeEventListener('mousemove', handleMouseMove);
    window.removeEventListener('contextmenu', handleContextMenu);
    window.removeEventListener('blur', sendReleaseForAllPressedInputs);
    document.removeEventListener('visibilitychange', handleVisibilityChange);
  }
}

function startLocalCanvasHost(
  canvas: HTMLCanvasElement,
  symbolicPanel: HTMLElement,
): void {
  const host = attachNanoCalibur(canvas, DEFAULT_CANVAS_OPTIONS);
  let lastSymbolicRenderAtMs = 0;
  const renderSymbolic = (nowMs: number): void => {
    if (nowMs - lastSymbolicRenderAtMs >= 100) {
      const frame = host.getSymbolicFrame();
      symbolicPanel.textContent = formatSymbolicFrame(frame);
      lastSymbolicRenderAtMs = nowMs;
    }
    window.requestAnimationFrame(renderSymbolic);
  };

  void host.start().then(() => {
    window.requestAnimationFrame(renderSymbolic);
  }).catch((error: unknown) => {
    console.error('Failed to start NanoCalibur CanvasHost.', error);
  });
}

const canvas = requireCanvas('game');
const symbolicPanel = requireSymbolicPanel('symbolic');
const sessionConfig = parseSessionBrowserConfig();

if (sessionConfig.enabled) {
  void startSessionBrowserClient(canvas, symbolicPanel, sessionConfig).catch((error) => {
    console.error('Failed to start browser session client.', error);
    symbolicPanel.textContent = `Session client error: ${String(error)}`;
  });
} else {
  startLocalCanvasHost(canvas, symbolicPanel);
}
