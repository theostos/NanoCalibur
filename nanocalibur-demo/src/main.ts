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

class SessionSnapshotRenderer {
  private readonly canvas: HTMLCanvasElement;
  private readonly animation: AnimationSystem;
  private readonly assets: AssetStore;
  private readonly renderer: CanvasRenderer;
  private interfaceOverlay: InterfaceOverlay | null;
  private interfaceHtml: string;
  private ready = false;
  private latestState: InterpreterState | null = null;
  private latestSnapshotAtMs = 0;

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
    if (!this.ready) {
      return;
    }
    this.renderFrame();
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
      Math.min(0.25, (nowMs - this.latestSnapshotAtMs) / 1000),
    );
    const sourceActors = Array.isArray(this.latestState.actors)
      ? (this.latestState.actors as ActorState[])
      : [];
    const sourceActorsByUid = new Map<string, ActorState>();
    for (const actor of sourceActors) {
      if (typeof actor.uid === 'string' && actor.uid.length > 0) {
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
      cloned.x = projected.x;
      cloned.y = projected.y;
      return cloned;
    });
    const nextState = {
      ...this.latestState,
      actors,
    } as InterpreterState;

    if (
      nextState.camera &&
      typeof nextState.camera === 'object' &&
      nextState.camera.mode === 'follow' &&
      typeof nextState.camera.target_uid === 'string'
    ) {
      const target = actors.find((actor) => actor.uid === nextState.camera?.target_uid);
      if (target && typeof target.x === 'number' && typeof target.y === 'number') {
        nextState.camera = {
          ...nextState.camera,
          x: target.x,
          y: target.y,
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
    globals.self =
      selfState && typeof selfState === 'object'
        ? { ...(selfState as Record<string, any>) }
        : {};
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
  if (previousElapsed !== null && nextElapsed !== null && previousElapsed !== nextElapsed) {
    return true;
  }
  const previousTurn =
    typeof previousScene.turn === 'number' ? previousScene.turn : null;
  const nextTurn =
    typeof nextScene.turn === 'number' ? nextScene.turn : null;
  if (previousTurn !== null && nextTurn !== null && previousTurn !== nextTurn) {
    return true;
  }
  if (previousElapsed === null || nextElapsed === null) {
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

function mapBrowserKeyDownToCommand(
  event: KeyboardEvent,
): Record<string, any> | null {
  const tokens = browserKeyboardTokens(event);
  if (tokens.length === 0) {
    return null;
  }
  return { kind: 'input', keyboard: { begin: tokens, on: tokens } };
}

function mapBrowserKeyUpToCommand(
  event: KeyboardEvent,
): Record<string, any> | null {
  const tokens = browserKeyboardTokens(event);
  if (tokens.length === 0) {
    return null;
  }
  return { kind: 'input', keyboard: { end: tokens } };
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
  const rendererOptions = mergeSpecOptions(
    DEFAULT_CANVAS_OPTIONS,
    sessionSpec as Record<string, any>,
  );
  const sessionRenderer = new SessionSnapshotRenderer(
    canvas,
    rendererOptions,
    typeof sessionSpec.interface_html === 'string' ? sessionSpec.interface_html : '',
  );
  void sessionRenderer.start().catch((error) => {
    console.error('Failed to preload session renderer assets.', error);
  });

  let latestSnapshot: SessionSnapshot | null = null;
  let sessionWarning: string | null = null;
  let lastSymbolicRenderAtMs = 0;

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

  window.addEventListener('keydown', (event) => {
    if (event.repeat) {
      return;
    }
    const command = mapBrowserKeyDownToCommand(event);
    if (!command) {
      return;
    }
    if (event.key.startsWith('Arrow') || event.key === ' ') {
      event.preventDefault();
    }
    void sendCommand(command);
  });

  window.addEventListener('keyup', (event) => {
    const command = mapBrowserKeyUpToCommand(event);
    if (!command) {
      return;
    }
    if (event.key.startsWith('Arrow') || event.key === ' ') {
      event.preventDefault();
    }
    void sendCommand(command);
  });

  const streamResponse = await fetch(
    `${config.baseUrl}/sessions/${encodeURIComponent(sessionId)}/stream`,
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
