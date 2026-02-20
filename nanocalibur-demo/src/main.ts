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
import { InterfaceOverlay } from './nanocalibur_generated/canvas/interface_overlay';
import type { ActorState, MapSpec } from './nanocalibur_generated/canvas/types';

type SymbolicLegendEntry = { symbol: string; description: string };
type SymbolicFrame = { rows: string[]; legend: SymbolicLegendEntry[] };

interface SessionJoinPayload {
  session_id: string;
  role_id: string;
  access_token: string;
}

interface SessionSnapshot {
  session_id: string;
  frame: SymbolicFrame;
  state: Record<string, any>;
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
  private interfaceOverlay: InterfaceOverlay | null;
  private interfaceHtml: string;
  private localState: Record<string, any> = {};
  private ready = false;
  private latestState: InterpreterState | null = null;
  private latestSnapshotAtMs = 0;
  private readonly smoothedPositionsByUid = new Map<string, { x: number; y: number }>();
  private lastRenderAtMs = 0;

  constructor(
    canvas: HTMLCanvasElement,
    options: CanvasHostOptions,
    interfaceHtml: string,
  ) {
    this.canvas = canvas;
    this.assets = new AssetStore(options);
    this.animation = new AnimationSystem(options, () => undefined);
    this.renderer = new CanvasRenderer(canvas, options, this.assets, this.animation);
    this.interfaceHtml = interfaceHtml;
    this.interfaceOverlay =
      interfaceHtml.trim().length > 0
        ? new InterfaceOverlay(canvas, interfaceHtml)
        : null;
  }

  async start(): Promise<void> {
    await this.assets.preload();
    this.ready = true;
    this.renderLoop();
  }

  render(snapshot: SessionSnapshot): void {
    this.latestState = (snapshot.state || {}) as InterpreterState;
    this.latestSnapshotAtMs = performance.now();
  }

  setLocalState(nextLocalState: Record<string, any>): void {
    this.localState = deepCloneLocalState(nextLocalState);
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
    this.syncInterfaceOverlay(state);
    if (this.interfaceOverlay) {
      this.interfaceOverlay.updateGlobals(this.buildInterfaceGlobals(state));
    }
  }

  private buildInterpolatedState(): InterpreterState | null {
    if (!this.latestState) {
      return null;
    }
    const nowMs = performance.now();
    const elapsedSeconds = Math.max(
      0,
      Math.min(0.08, (nowMs - this.latestSnapshotAtMs) / 1000),
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
      if (!uid) {
        cloned.x = projected.x;
        cloned.y = projected.y;
        return cloned;
      }

      const previousSmoothed = this.smoothedPositionsByUid.get(uid);
      let nextX = projected.x;
      let nextY = projected.y;
      if (previousSmoothed) {
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

    if (
      nextState.camera &&
      typeof nextState.camera === 'object' &&
      typeof nextState.camera.target_uid === 'string'
    ) {
      const target = actors.find((actor) => actor.uid === nextState.camera?.target_uid);
      if (target && typeof target.x === 'number' && typeof target.y === 'number') {
        const offsetX =
          typeof nextState.camera.offset_x === 'number' ? nextState.camera.offset_x : 0;
        const offsetY =
          typeof nextState.camera.offset_y === 'number' ? nextState.camera.offset_y : 0;
        nextState.camera = {
          ...nextState.camera,
          x: target.x + offsetX,
          y: target.y + offsetY,
        };
      }
    }

    return nextState;
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

  private syncInterfaceOverlay(state: InterpreterState): void {
    const scene = state.scene as Record<string, any> | null;
    const nextHtml =
      scene && typeof scene.interfaceHtml === 'string'
        ? scene.interfaceHtml
        : this.interfaceHtml;
    if (nextHtml === this.interfaceHtml) {
      return;
    }
    this.interfaceHtml = nextHtml;
    if (nextHtml.trim().length === 0) {
      if (this.interfaceOverlay) {
        this.interfaceOverlay.destroy();
        this.interfaceOverlay = null;
      }
      return;
    }
    if (this.interfaceOverlay) {
      this.interfaceOverlay.setHtml(nextHtml);
      return;
    }
    this.interfaceOverlay = new InterfaceOverlay(this.canvas, nextHtml);
  }
}

const DEFAULT_CANVAS_OPTIONS: CanvasHostOptions = {
  width: 960,
  height: 640,
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

function formatSymbolicFrame(frame: SymbolicFrame): string {
  const legend = formatLegend(frame.legend || []);
  if (!legend) {
    return frame.rows.join('\n');
  }
  return `${frame.rows.join('\n')}\n\nLegend\n${legend}`;
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
  let lastSnapshotAtMs = 0;

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
      symbolicPanel.textContent = lines.join('\n');
      lastSymbolicRenderAtMs = nowMs;
      return;
    }
    if (shouldRenderSymbolic) {
      const warningPrefix = sessionWarning ? `WARNING: ${sessionWarning}\n\n` : '';
      symbolicPanel.textContent = `${warningPrefix}${formatSessionSnapshot(latestSnapshot)}`;
      lastSymbolicRenderAtMs = nowMs;
    }
    sessionRenderer.render(latestSnapshot);
  };

  const renderSnapshot = (snapshot: SessionSnapshot): void => {
    latestSnapshot = snapshot;
    lastSnapshotAtMs = performance.now();
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

  let snapshotPollInFlight = false;
  let snapshotPollFailureCount = 0;
  const snapshotPollHandle = window.setInterval(() => {
    if (snapshotPollInFlight) {
      return;
    }
    if (performance.now() - lastSnapshotAtMs < 250) {
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
  }, 120);

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

  const sendReleaseForAllPressedKeys = (): void => {
    const physicalTokens = uniqueStrings(
      Array.from(activePhysicalTokensByKey.values()).flat(),
    );
    if (physicalTokens.length === 0) {
      return;
    }
    activePhysicalTokensByKey.clear();
    const endTokens = keyboardTokensWithLogicalBindings(roleLocal.localState, physicalTokens);
    if (endTokens.length === 0) {
      return;
    }
    enqueueCommand({
      kind: 'input',
      keyboard: { end: endTokens },
    });
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
    enqueueCommand({
      kind: 'input',
      keyboard: keyboardPayload,
    });
  };

  const handleVisibilityChange = (): void => {
    if (document.visibilityState !== 'visible') {
      sendReleaseForAllPressedKeys();
    }
  };

  window.addEventListener('keydown', handleKeyDown);
  window.addEventListener('keyup', handleKeyUp);
  window.addEventListener('blur', sendReleaseForAllPressedKeys);
  document.addEventListener('visibilitychange', handleVisibilityChange);

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
  const inputPulseMs = Math.max(
    20,
    Math.round(1000 / Math.max(1, Math.floor(configuredTickRate))),
  );
  const inputPulseHandle = window.setInterval(() => {
    const onTokens = activeInputTokens();
    if (onTokens.length === 0) {
      return;
    }
    enqueueCommand(
      {
        kind: 'input',
        keyboard: { on: onTokens },
      },
      { dropIfBusy: true },
    );
  }, inputPulseMs);

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
    window.clearInterval(statusPollHandle);
    const text = await streamResponse.text();
    throw new Error(text || `Session stream failed: ${streamResponse.status}`);
  }

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
    window.clearInterval(statusPollHandle);
    window.clearInterval(snapshotPollHandle);
    window.clearInterval(inputPulseHandle);
    sendReleaseForAllPressedKeys();
    window.removeEventListener('keydown', handleKeyDown);
    window.removeEventListener('keyup', handleKeyUp);
    window.removeEventListener('blur', sendReleaseForAllPressedKeys);
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
