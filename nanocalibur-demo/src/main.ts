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
  private readonly animation: AnimationSystem;
  private readonly assets: AssetStore;
  private readonly renderer: CanvasRenderer;
  private readonly interfaceOverlay: InterfaceOverlay | null;
  private ready = false;
  private latestState: InterpreterState | null = null;
  private latestSnapshotAtMs = 0;

  constructor(
    canvas: HTMLCanvasElement,
    options: CanvasHostOptions,
    interfaceHtml: string,
  ) {
    this.assets = new AssetStore(options);
    this.animation = new AnimationSystem(options, () => undefined);
    this.renderer = new CanvasRenderer(canvas, options, this.assets, this.animation);
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
    const actors = sourceActors.map((actor) => {
      const cloned = { ...actor };
      const x = typeof actor.x === 'number' ? actor.x : 0;
      const y = typeof actor.y === 'number' ? actor.y : 0;
      const vx = typeof actor.vx === 'number' ? actor.vx : 0;
      const vy = typeof actor.vy === 'number' ? actor.vy : 0;
      cloned.x = x + vx * elapsedSeconds;
      cloned.y = y + vy * elapsedSeconds;
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
    globals.__actors_count = Array.isArray(state.actors) ? state.actors.length : 0;
    globals.__scene_elapsed =
      state.scene && typeof state.scene.elapsed === 'number'
        ? state.scene.elapsed
        : 0;
    return globals;
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

function normalizeMovementKey(rawKey: string): string | null {
  const key = rawKey.toLowerCase();
  if (key === 'arrowup' || key === 'z' || key === 'w') return 'z';
  if (key === 'arrowleft' || key === 'q' || key === 'a') return 'q';
  if (key === 'arrowdown' || key === 's') return 's';
  if (key === 'arrowright' || key === 'd') return 'd';
  return null;
}

function mapBrowserKeyDownToCommand(event: KeyboardEvent): Record<string, any> | null {
  const movement = normalizeMovementKey(event.key);
  if (movement) {
    return { kind: 'input', keyboard: { on: [movement] } };
  }
  const key = event.key.toLowerCase();
  if (key === 'e') return { kind: 'tool', name: 'spawn_bonus' };
  if (key === 'n') return { kind: 'tool', name: 'llm_dummy_next_turn' };
  return null;
}

function mapBrowserKeyUpToCommand(event: KeyboardEvent): Record<string, any> | null {
  const movement = normalizeMovementKey(event.key);
  if (!movement) {
    return null;
  }
  return { kind: 'input', keyboard: { end: [movement] } };
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

  const renderPanel = (): void => {
    if (!latestSnapshot) {
      const lines = [
        `Session: ${sessionId}`,
        sessionWarning ? `WARNING: ${sessionWarning}` : '',
        'Waiting for first snapshot...',
      ].filter((line) => line.length > 0);
      symbolicPanel.textContent = lines.join('\n');
      return;
    }
    const warningPrefix = sessionWarning ? `WARNING: ${sessionWarning}\n\n` : '';
    symbolicPanel.textContent = `${warningPrefix}${formatSessionSnapshot(latestSnapshot)}`;
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
        const currentElapsed = latestSnapshot?.state?.scene?.elapsed;
        const nextElapsed = (response.state as Record<string, any>)?.scene?.elapsed;
        if (typeof currentElapsed !== 'number' || nextElapsed !== currentElapsed) {
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
    event.preventDefault();
    void sendCommand(command);
  });

  window.addEventListener('keyup', (event) => {
    const command = mapBrowserKeyUpToCommand(event);
    if (!command) {
      return;
    }
    event.preventDefault();
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
          renderSnapshot(snapshot);
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
  const renderSymbolic = (): void => {
    const frame = host.getSymbolicFrame();
    symbolicPanel.textContent = formatSymbolicFrame(frame);
    window.requestAnimationFrame(renderSymbolic);
  };

  void host.start().then(() => {
    renderSymbolic();
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
