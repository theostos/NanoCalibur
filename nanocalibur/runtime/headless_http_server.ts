import { HeadlessHost, HeadlessStepInput } from "./headless_host";
import { SessionManager } from "./session_manager";
import { SessionCommand } from "./session_runtime";

declare const require: any;
const http = require("http");
const crypto = require("crypto");

export interface HeadlessHttpServerOptions {
  host?: string;
  port?: number;
}

interface SessionViewer {
  isAdmin: boolean;
  roleId: string | null;
}

export class HeadlessHttpServer {
  private readonly host: HeadlessHost;
  private readonly sessionManager: SessionManager | null;
  private readonly hostFactory: (() => HeadlessHost) | null;
  private singleHostSessionClaimed = false;
  private server: any | null = null;
  private port: number | null = null;

  constructor(
    host: HeadlessHost,
    sessionManager: SessionManager | null = null,
    hostFactory: (() => HeadlessHost) | null = null,
  ) {
    this.host = host;
    this.sessionManager = sessionManager;
    this.hostFactory = hostFactory;
  }

  async start(options: HeadlessHttpServerOptions = {}): Promise<number> {
    if (this.server) {
      return this.port || 0;
    }

    const host = options.host || "127.0.0.1";
    const requestedPort =
      typeof options.port === "number" && Number.isFinite(options.port)
        ? Math.floor(options.port)
        : 0;

    const server = http.createServer((req: any, res: any) => {
      void this.handleRequest(req, res);
    });

    await new Promise<void>((resolve, reject) => {
      server.once("error", reject);
      server.listen(requestedPort, host, () => {
        server.removeListener("error", reject);
        resolve();
      });
    });

    const address = server.address();
    this.port =
      address && typeof address === "object" && typeof address.port === "number"
        ? address.port
        : requestedPort;
    this.server = server;
    return this.port || 0;
  }

  async stop(): Promise<void> {
    if (!this.server) {
      return;
    }
    const server = this.server;
    this.server = null;
    this.port = null;
    await new Promise<void>((resolve, reject) => {
      server.close((error: Error | undefined) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }

  getPort(): number | null {
    return this.port;
  }

  private async handleRequest(req: any, res: any): Promise<void> {
    try {
      const url = this.parseRequestUrl(req.url);
      const method = typeof req.method === "string" ? req.method.toUpperCase() : "";
      this.applyCorsHeaders(res);

      if (method === "OPTIONS") {
        res.statusCode = 204;
        res.end();
        return;
      }

      if (this.sessionManager) {
        const handled = await this.handleSessionRequest(req, res, method, url);
        if (handled) {
          return;
        }
      }

      if (method === "GET" && url.pathname === "/health") {
        this.respondJson(res, 200, { ok: true });
        return;
      }

      if (method === "GET" && url.pathname === "/tools") {
        this.respondJson(res, 200, { tools: this.host.listTools() });
        return;
      }

      if (method === "GET" && url.pathname === "/frame") {
        this.respondJson(res, 200, { frame: this.host.getSymbolicFrame() });
        return;
      }

      if (method === "GET" && url.pathname === "/state") {
        this.respondJson(res, 200, { state: this.host.getState() });
        return;
      }

      if (method === "POST" && url.pathname === "/step") {
        const payload = await this.readJsonBody(req);
        const frame = this.host.step((payload || {}) as HeadlessStepInput);
        this.respondJson(res, 200, {
          frame,
          state: this.host.getState(),
        });
        return;
      }

      if (method === "POST" && url.pathname === "/tools/call") {
        const payload = await this.readJsonBody(req);
        const toolName = payload && typeof payload.name === "string" ? payload.name : "";
        if (!toolName) {
          this.respondJson(res, 400, {
            error: "tools/call requires JSON body field 'name'.",
          });
          return;
        }
        const toolArgs =
          payload && payload.arguments && typeof payload.arguments === "object"
            ? payload.arguments
            : {};
        const frame = this.host.callTool(toolName, toolArgs);
        this.respondJson(res, 200, {
          frame,
          state: this.host.getState(),
        });
        return;
      }

      if (method === "POST" && url.pathname.startsWith("/tools/")) {
        const encodedName = url.pathname.slice("/tools/".length);
        const toolName = decodeURIComponent(encodedName);
        if (!toolName || toolName === "call") {
          this.respondJson(res, 404, { error: "Tool not found." });
          return;
        }
        const payload = await this.readJsonBody(req);
        const toolArgs = payload && typeof payload === "object" ? payload : {};
        const frame = this.host.callTool(toolName, toolArgs);
        this.respondJson(res, 200, {
          frame,
          state: this.host.getState(),
        });
        return;
      }

      this.respondJson(res, 404, { error: "Not found." });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.respondJson(res, 500, { error: message });
    }
  }

  private async handleSessionRequest(
    req: any,
    res: any,
    method: string,
    url: URL,
  ): Promise<boolean> {
    if (!this.sessionManager) {
      return false;
    }

    if (method === "GET" && url.pathname === "/open-roles") {
      this.respondJson(res, 200, {
        sessions: this.sessionManager.listAllOpenRoles(),
      });
      return true;
    }

    if (method === "GET" && url.pathname === "/sessions") {
      this.respondJson(res, 200, {
        sessions: this.sessionManager.listSessionsSummary(),
      });
      return true;
    }

    if (method === "POST" && url.pathname === "/sessions") {
      const payload = await this.readJsonBody(req);
      const host = this.createHostForSession();
      const sessionId = this.generateUniqueSessionId();
      const loopMode = this.resolveSessionLoopMode(host);
      const tickRate = this.resolveSessionTickRate(host);
      const rolesFromSpec = this.resolveSessionRoles(host);
      const fallbackRoles = this.parseRoleConfigsFromPayload(payload);
      const created = this.sessionManager.createSession(sessionId, host, {
        seed: typeof payload.seed === "string" ? payload.seed : undefined,
        loopMode,
        defaultStepSeconds: 1 / tickRate,
        roles: rolesFromSpec.length > 0 ? rolesFromSpec : fallbackRoles,
        pace: {
          gameTimeScale:
            typeof payload.game_time_scale === "number"
              ? payload.game_time_scale
              : typeof payload.gameTimeScale === "number"
                ? payload.gameTimeScale
                : undefined,
          maxCatchupSteps:
            typeof payload.max_catchup_steps === "number"
              ? payload.max_catchup_steps
              : typeof payload.maxCatchupSteps === "number"
                ? payload.maxCatchupSteps
                : undefined,
        },
      });

      const invites = this.sessionManager.listSessionInvites(
        created.id,
        created.adminToken,
      );
      this.respondJson(res, 201, {
        session_id: created.id,
        seed: created.seed,
        status: created.status,
        admin_token: created.adminToken,
        loop_mode: created.runtime.getLoopMode(),
        tick_rate: tickRate,
        roles: this.sessionManager.listSessionRoles(created.id),
        invites,
      });
      return true;
    }

    if (method === "POST" && url.pathname === "/join") {
      const payload = await this.readJsonBody(req);
      const inviteToken =
        payload && typeof payload.invite_token === "string" ? payload.invite_token : "";
      if (!inviteToken) {
        this.respondJson(res, 400, { error: "join requires invite_token." });
        return true;
      }
      const joined = this.sessionManager.joinWithInviteToken(inviteToken);
      this.respondJson(res, 200, {
        session_id: joined.sessionId,
        role_id: joined.roleId,
        access_token: joined.accessToken,
      });
      return true;
    }

    const openRolesMatch = /^\/sessions\/([^/]+)\/open-roles$/.exec(url.pathname);
    if (method === "GET" && openRolesMatch) {
      const sessionId = decodeURIComponent(openRolesMatch[1]);
      this.respondJson(res, 200, {
        session_id: sessionId,
        roles: this.sessionManager.listOpenRoles(sessionId),
      });
      return true;
    }

    const startMatch = /^\/sessions\/([^/]+)\/start$/.exec(url.pathname);
    if (method === "POST" && startMatch) {
      const sessionId = decodeURIComponent(startMatch[1]);
      const payload = await this.readJsonBody(req);
      const adminToken = this.resolveAdminToken(req, payload, url);
      if (!adminToken) {
        this.respondJson(res, 401, { error: "Missing admin token." });
        return true;
      }
      const status = this.sessionManager.startSession(sessionId, adminToken);
      this.respondJson(res, 200, { session_id: sessionId, status });
      return true;
    }

    const stopMatch = /^\/sessions\/([^/]+)\/stop$/.exec(url.pathname);
    if (method === "POST" && stopMatch) {
      const sessionId = decodeURIComponent(stopMatch[1]);
      const payload = await this.readJsonBody(req);
      const adminToken = this.resolveAdminToken(req, payload, url);
      if (!adminToken) {
        this.respondJson(res, 401, { error: "Missing admin token." });
        return true;
      }
      const status = this.sessionManager.stopSession(sessionId, adminToken);
      this.respondJson(res, 200, { session_id: sessionId, status });
      return true;
    }

    const paceMatch = /^\/sessions\/([^/]+)\/pace$/.exec(url.pathname);
    if (method === "PATCH" && paceMatch) {
      const sessionId = decodeURIComponent(paceMatch[1]);
      const payload = await this.readJsonBody(req);
      const adminToken = this.resolveAdminToken(req, payload, url);
      if (!adminToken) {
        this.respondJson(res, 401, { error: "Missing admin token." });
        return true;
      }
      const pace = this.sessionManager.updateSessionPace(
        sessionId,
        {
          gameTimeScale:
            typeof payload.game_time_scale === "number"
              ? payload.game_time_scale
              : typeof payload.gameTimeScale === "number"
                ? payload.gameTimeScale
                : undefined,
          maxCatchupSteps:
            typeof payload.max_catchup_steps === "number"
              ? payload.max_catchup_steps
              : typeof payload.maxCatchupSteps === "number"
                ? payload.maxCatchupSteps
                : undefined,
        },
        adminToken,
      );
      this.respondJson(res, 200, {
        session_id: sessionId,
        pace: {
          game_time_scale: pace.gameTimeScale,
          max_catchup_steps: pace.maxCatchupSteps,
        },
      });
      return true;
    }

    const commandsMatch = /^\/sessions\/([^/]+)\/commands$/.exec(url.pathname);
    if (method === "POST" && commandsMatch) {
      const sessionId = decodeURIComponent(commandsMatch[1]);
      const payload = await this.readJsonBody(req);
      const accessToken = this.resolveRoleToken(req, payload, url);
      if (!accessToken) {
        this.respondJson(res, 401, { error: "Missing role access token." });
        return true;
      }
      const roleBinding = this.sessionManager.validateRoleToken(sessionId, accessToken);
      if (!roleBinding) {
        this.respondJson(res, 401, { error: "Invalid role access token." });
        return true;
      }
      const commands = this.normalizeSessionCommands(payload.commands);
      this.sessionManager.enqueueAuthorizedCommands(sessionId, accessToken, commands);
      const shouldTick = payload.tick !== false;
      const result = shouldTick
        ? this.sessionManager.tickSession(sessionId)
        : {
            frame: this.sessionManager.getSessionFrameForRole(
              sessionId,
              roleBinding.roleId,
            ),
            state: this.sessionManager.getSessionState(sessionId),
          };
      this.respondJson(res, 200, {
        frame: this.sessionManager.getSessionFrameForRole(sessionId, roleBinding.roleId),
        state: this.scopeStateForViewer(result.state, {
          isAdmin: false,
          roleId: roleBinding.roleId,
        }),
      });
      return true;
    }

    const frameMatch = /^\/sessions\/([^/]+)\/frame$/.exec(url.pathname);
    if (method === "GET" && frameMatch) {
      const sessionId = decodeURIComponent(frameMatch[1]);
      const viewer = this.resolveSessionViewer(req, url, sessionId, null);
      if (!viewer) {
        this.respondJson(res, 401, { error: "Unauthorized." });
        return true;
      }
      this.respondJson(res, 200, {
        session_id: sessionId,
        frame: this.sessionManager.getSessionFrameForRole(sessionId, viewer.roleId),
      });
      return true;
    }

    const stateMatch = /^\/sessions\/([^/]+)\/state$/.exec(url.pathname);
    if (method === "GET" && stateMatch) {
      const sessionId = decodeURIComponent(stateMatch[1]);
      const viewer = this.resolveSessionViewer(req, url, sessionId, null);
      if (!viewer) {
        this.respondJson(res, 401, { error: "Unauthorized." });
        return true;
      }
      this.respondJson(res, 200, {
        session_id: sessionId,
        state: this.scopeStateForViewer(
          this.sessionManager.getSessionState(sessionId),
          viewer,
        ),
      });
      return true;
    }

    const toolsMatch = /^\/sessions\/([^/]+)\/tools$/.exec(url.pathname);
    if (method === "GET" && toolsMatch) {
      const sessionId = decodeURIComponent(toolsMatch[1]);
      const viewer = this.resolveSessionViewer(req, url, sessionId, null);
      if (!viewer) {
        this.respondJson(res, 401, { error: "Unauthorized." });
        return true;
      }
      this.respondJson(res, 200, {
        session_id: sessionId,
        tools: this.sessionManager.getSessionTools(sessionId),
      });
      return true;
    }

    const streamMatch = /^\/sessions\/([^/]+)\/stream$/.exec(url.pathname);
    if (method === "GET" && streamMatch) {
      const sessionId = decodeURIComponent(streamMatch[1]);
      const viewer = this.resolveSessionViewer(req, url, sessionId, null);
      if (!viewer) {
        this.respondJson(res, 401, { error: "Unauthorized." });
        return true;
      }

      res.statusCode = 200;
      res.setHeader("Content-Type", "text/event-stream");
      res.setHeader("Cache-Control", "no-cache");
      res.setHeader("Connection", "keep-alive");
      this.writeSseEvent(res, "snapshot", {
        session_id: sessionId,
        frame: this.sessionManager.getSessionFrameForRole(sessionId, viewer.roleId),
        state: this.scopeStateForViewer(
          this.sessionManager.getSessionState(sessionId),
          viewer,
        ),
      });

      const session = this.sessionManager.getSession(sessionId);
      const stepSeconds =
        session && session.runtime
          ? session.runtime.getDefaultStepSeconds()
          : 1 / 20;
      const intervalMs = Math.max(10, Math.round(stepSeconds * 1000));
      const interval = setInterval(() => {
        try {
          const result = this.sessionManager!.tickSession(sessionId, stepSeconds);
          this.writeSseEvent(res, "snapshot", {
            session_id: sessionId,
            frame: this.sessionManager!.getSessionFrameForRole(sessionId, viewer.roleId),
            state: this.scopeStateForViewer(result.state, viewer),
          });
        } catch (_error) {
          clearInterval(interval);
          try {
            res.end();
          } catch (_ignored) {
            // ignore broken connection writes
          }
        }
      }, intervalMs);

      req.on("close", () => {
        clearInterval(interval);
      });
      return true;
    }

    return false;
  }

  private normalizeSessionCommands(value: unknown): SessionCommand[] {
    if (!Array.isArray(value)) {
      return [];
    }
    const out: SessionCommand[] = [];
    for (const item of value) {
      if (!item || typeof item !== "object") {
        continue;
      }
      const kind = (item as { kind?: unknown }).kind;
      if (kind === "tool") {
        const name = (item as { name?: unknown }).name;
        if (typeof name === "string" && name) {
          out.push({
            kind: "tool",
            name,
            payload:
              (item as { payload?: unknown }).payload &&
              typeof (item as { payload?: unknown }).payload === "object"
                ? ((item as { payload?: Record<string, any> }).payload as Record<string, any>)
                : {},
          });
        }
        continue;
      }
      if (kind === "button") {
        const name = (item as { name?: unknown }).name;
        if (typeof name === "string" && name) {
          out.push({ kind: "button", name });
        }
        continue;
      }
      if (kind === "input") {
        out.push({
          kind: "input",
          keyboard:
            (item as { keyboard?: unknown }).keyboard &&
            typeof (item as { keyboard?: unknown }).keyboard === "object"
              ? ((item as { keyboard?: HeadlessStepInput["keyboard"] }).keyboard as HeadlessStepInput["keyboard"])
              : undefined,
          mouse:
            (item as { mouse?: unknown }).mouse &&
            typeof (item as { mouse?: unknown }).mouse === "object"
              ? ((item as { mouse?: HeadlessStepInput["mouse"] }).mouse as HeadlessStepInput["mouse"])
              : undefined,
          uiButtons: Array.isArray((item as { uiButtons?: unknown }).uiButtons)
            ? ((item as { uiButtons?: unknown[] }).uiButtons as unknown[])
                .filter((entry): entry is string => typeof entry === "string")
            : undefined,
        });
        continue;
      }
      if (kind === "noop") {
        out.push({ kind: "noop" });
      }
    }
    return out;
  }

  private resolveSessionViewer(
    req: any,
    url: URL,
    sessionId: string,
    payload: Record<string, any> | null,
  ): SessionViewer | null {
    if (!this.sessionManager) {
      return null;
    }
    const adminToken = this.resolveAdminToken(req, payload, url);
    if (adminToken && this.sessionManager.validateAdminToken(sessionId, adminToken)) {
      return { isAdmin: true, roleId: null };
    }
    const roleToken = this.resolveRoleToken(req, payload, url);
    if (!roleToken) {
      return null;
    }
    const role = this.sessionManager.validateRoleToken(sessionId, roleToken);
    if (!role) {
      return null;
    }
    return {
      isAdmin: false,
      roleId: role.roleId,
    };
  }

  private scopeStateForViewer(
    state: Record<string, any>,
    viewer: SessionViewer,
  ): Record<string, any> {
    const cameras =
      state && state.cameras && typeof state.cameras === "object"
        ? (state.cameras as Record<string, any>)
        : {};
    const resolveCameraForRole = (roleId: string | null): Record<string, any> | null => {
      if (!roleId) {
        return null;
      }
      for (const camera of Object.values(cameras)) {
        if (!camera || typeof camera !== "object") {
          continue;
        }
        if ((camera as Record<string, any>).role_id === roleId) {
          return camera as Record<string, any>;
        }
      }
      return null;
    };

    const roles =
      state && state.roles && typeof state.roles === "object"
        ? (state.roles as Record<string, any>)
        : null;
    if (!roles) {
      return state;
    }

    const scopedScene = (() => {
      const scene =
        state && state.scene && typeof state.scene === "object"
          ? ({ ...(state.scene as Record<string, any>) } as Record<string, any>)
          : null;
      if (!scene) {
        return null;
      }
      const roleScoped =
        scene.interfaceByRole && typeof scene.interfaceByRole === "object"
          ? (scene.interfaceByRole as Record<string, any>)
          : {};
      const fallbackHtml =
        typeof scene.interfaceHtml === "string" ? scene.interfaceHtml : "";
      if (viewer.isAdmin) {
        scene.interfaceByRole = {};
        scene.interfaceHtml = fallbackHtml;
        return scene;
      }
      const roleId = viewer.roleId;
      const scopedHtml =
        roleId &&
        typeof roleScoped[roleId] === "string"
          ? (roleScoped[roleId] as string)
          : fallbackHtml;
      scene.interfaceHtml = scopedHtml;
      scene.interfaceByRole =
        roleId &&
        typeof roleScoped[roleId] === "string"
          ? { [roleId]: roleScoped[roleId] }
          : {};
      return scene;
    })();

    if (viewer.isAdmin) {
      return {
        ...state,
        scene: scopedScene,
        camera: null,
        self: null,
      };
    }

    const roleId = viewer.roleId;
    const selfRole =
      roleId &&
      roleId.length > 0 &&
      roles[roleId] &&
      typeof roles[roleId] === "object"
        ? roles[roleId]
        : null;
    return {
      ...state,
      scene: scopedScene,
      roles: selfRole && roleId ? { [roleId]: selfRole } : {},
      camera: resolveCameraForRole(roleId) || null,
      self: selfRole,
    };
  }

  private resolveAdminToken(
    req: any,
    payload: Record<string, any> | null,
    url: URL,
  ): string | null {
    const headerToken = this.readHeader(req, "x-admin-token");
    if (headerToken) {
      return headerToken;
    }
    const queryToken = this.readQueryString(url, "admin_token");
    if (queryToken) {
      return queryToken;
    }
    if (payload && typeof payload.admin_token === "string" && payload.admin_token) {
      return payload.admin_token;
    }
    return null;
  }

  private resolveRoleToken(
    req: any,
    payload: Record<string, any> | null,
    url: URL,
  ): string | null {
    const headerToken = this.readHeader(req, "x-role-token");
    if (headerToken) {
      return headerToken;
    }
    const queryToken = this.readQueryString(url, "access_token");
    if (queryToken) {
      return queryToken;
    }
    const authToken = this.readBearer(req);
    if (authToken) {
      return authToken;
    }
    if (payload && typeof payload.access_token === "string" && payload.access_token) {
      return payload.access_token;
    }
    return null;
  }

  private readQueryString(url: URL, key: string): string | null {
    const value = url.searchParams.get(key);
    if (typeof value === "string" && value) {
      return value;
    }
    return null;
  }

  private readHeader(req: any, headerName: string): string | null {
    if (!req || !req.headers || typeof req.headers !== "object") {
      return null;
    }
    const value = req.headers[headerName] || req.headers[headerName.toLowerCase()];
    if (typeof value === "string" && value) {
      return value;
    }
    if (Array.isArray(value) && value.length > 0 && typeof value[0] === "string") {
      return value[0];
    }
    return null;
  }

  private readBearer(req: any): string | null {
    const header = this.readHeader(req, "authorization");
    if (!header) {
      return null;
    }
    const match = /^Bearer\s+(.+)$/.exec(header);
    if (!match) {
      return null;
    }
    return match[1];
  }

  private writeSseEvent(res: any, eventName: string, payload: Record<string, any>): void {
    res.write(`event: ${eventName}\n`);
    res.write(`data: ${JSON.stringify(payload)}\n\n`);
  }

  private applyCorsHeaders(res: any): void {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader(
      "Access-Control-Allow-Headers",
      "Content-Type, Accept, Authorization, x-role-token, x-admin-token",
    );
    res.setHeader(
      "Access-Control-Allow-Methods",
      "GET, POST, PATCH, OPTIONS",
    );
  }

  private resolveSessionLoopMode(host: HeadlessHost): "real_time" | "turn_based" | "hybrid" {
    const spec = host.getInterpreter().getSpec() as Record<string, any>;
    const fromSpec =
      spec &&
      spec.multiplayer &&
      typeof spec.multiplayer.default_loop === "string"
        ? spec.multiplayer.default_loop
        : null;
    if (fromSpec === "real_time" || fromSpec === "turn_based" || fromSpec === "hybrid") {
      return fromSpec;
    }
    const fromScene = host.getState()?.scene?.loopMode;
    if (fromScene === "real_time" || fromScene === "turn_based" || fromScene === "hybrid") {
      return fromScene;
    }
    return "real_time";
  }

  private resolveSessionTickRate(host: HeadlessHost): number {
    const spec = host.getInterpreter().getSpec() as Record<string, any>;
    const fromSpec =
      spec &&
      spec.multiplayer &&
      typeof spec.multiplayer.tick_rate === "number"
        ? spec.multiplayer.tick_rate
        : null;
    if (typeof fromSpec === "number" && Number.isFinite(fromSpec) && fromSpec > 0) {
      return Math.floor(fromSpec);
    }
    return 20;
  }

  private resolveSessionRoles(
    host: HeadlessHost,
  ): Array<{ id: string; kind?: string; required?: boolean }> {
    const spec = host.getInterpreter().getSpec() as Record<string, any>;
    if (!spec || !Array.isArray(spec.roles)) {
      return [];
    }
    const out: Array<{ id: string; kind?: string; required?: boolean }> = [];
    for (const item of spec.roles) {
      if (!item || typeof item !== "object") {
        continue;
      }
      const id = typeof item.id === "string" ? item.id : "";
      if (!id) {
        continue;
      }
      out.push({
        id,
        kind: typeof item.kind === "string" ? item.kind : undefined,
        required: typeof item.required === "boolean" ? item.required : undefined,
      });
    }
    return out;
  }

  private parseRoleConfigsFromPayload(
    payload: Record<string, any>,
  ): Array<{ id: string; kind?: string; required?: boolean }> | undefined {
    if (!payload || !Array.isArray(payload.roles)) {
      return undefined;
    }
    return payload.roles
      .filter((entry) => entry && typeof entry === "object")
      .map((entry) => ({
        id: String(entry.id || ""),
        kind:
          typeof entry.kind === "string"
            ? entry.kind
            : typeof entry.type === "string"
              ? entry.type
              : undefined,
        required:
          typeof entry.required === "boolean" ? entry.required : undefined,
      }));
  }

  private createHostForSession(): HeadlessHost {
    if (this.hostFactory) {
      return this.hostFactory();
    }
    if (this.singleHostSessionClaimed) {
      throw new Error(
        "Cannot create more than one session without a hostFactory. Provide one HeadlessHost per session.",
      );
    }
    this.singleHostSessionClaimed = true;
    return this.host;
  }

  private generateSessionId(): string {
    if (crypto && typeof crypto.randomUUID === "function") {
      return String(crypto.randomUUID());
    }
    if (!crypto || typeof crypto.randomBytes !== "function") {
      return `session_${Date.now()}`;
    }
    return `${crypto.randomBytes(16).toString("hex")}`;
  }

  private generateUniqueSessionId(): string {
    if (!this.sessionManager) {
      return this.generateSessionId();
    }
    for (let attempt = 0; attempt < 1024; attempt += 1) {
      const candidate = this.generateSessionId();
      if (!this.sessionManager.getSession(candidate)) {
        return candidate;
      }
    }
    throw new Error("Failed to allocate a unique session id.");
  }

  private parseRequestUrl(rawUrl: unknown): URL {
    const safeUrl = typeof rawUrl === "string" ? rawUrl : "/";
    return new URL(safeUrl, "http://localhost");
  }

  private async readJsonBody(req: any): Promise<Record<string, any>> {
    const chunks: string[] = [];
    if (typeof req.setEncoding === "function") {
      req.setEncoding("utf8");
    }
    await new Promise<void>((resolve, reject) => {
      req.on("data", (chunk: unknown) => {
        chunks.push(String(chunk));
      });
      req.on("end", () => resolve());
      req.on("error", (error: Error) => reject(error));
    });

    if (chunks.length === 0) {
      return {};
    }

    const raw = chunks.join("").trim();
    if (!raw) {
      return {};
    }

    const decoded = JSON.parse(raw);
    if (!decoded || typeof decoded !== "object") {
      return {};
    }
    return decoded as Record<string, any>;
  }

  private respondJson(res: any, statusCode: number, payload: Record<string, any>): void {
    const body = JSON.stringify(payload);
    res.statusCode = statusCode;
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.end(body);
  }
}
