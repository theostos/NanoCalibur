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

    if (method === "POST" && url.pathname === "/sessions") {
      const payload = await this.readJsonBody(req);
      const sessionId =
        payload && typeof payload.session_id === "string" && payload.session_id
          ? payload.session_id
          : this.generateSessionId();

      const host = this.createHostForSession();
      const created = this.sessionManager.createSession(sessionId, host, {
        seed: typeof payload.seed === "string" ? payload.seed : undefined,
        loopMode:
          typeof payload.loop_mode === "string"
            ? (payload.loop_mode as any)
            : undefined,
        roles: Array.isArray(payload.roles)
          ? payload.roles
              .filter((entry) => entry && typeof entry === "object")
              .map((entry) => ({
                id: String(entry.id || ""),
                type: typeof entry.type === "string" ? entry.type : undefined,
                required:
                  typeof entry.required === "boolean" ? entry.required : undefined,
              }))
          : undefined,
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
      const adminToken = this.resolveAdminToken(req, payload);
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
      const adminToken = this.resolveAdminToken(req, payload);
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
      const adminToken = this.resolveAdminToken(req, payload);
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
      const accessToken = this.resolveRoleToken(req, payload);
      if (!accessToken) {
        this.respondJson(res, 401, { error: "Missing role access token." });
        return true;
      }
      const commands = this.normalizeSessionCommands(payload.commands);
      this.sessionManager.enqueueAuthorizedCommands(sessionId, accessToken, commands);
      const result = this.sessionManager.tickSession(sessionId);
      this.respondJson(res, 200, {
        frame: result.frame,
        state: result.state,
      });
      return true;
    }

    const frameMatch = /^\/sessions\/([^/]+)\/frame$/.exec(url.pathname);
    if (method === "GET" && frameMatch) {
      const sessionId = decodeURIComponent(frameMatch[1]);
      if (!this.hasSessionAccess(req, sessionId)) {
        this.respondJson(res, 401, { error: "Unauthorized." });
        return true;
      }
      this.respondJson(res, 200, {
        session_id: sessionId,
        frame: this.sessionManager.getSessionFrame(sessionId),
      });
      return true;
    }

    const stateMatch = /^\/sessions\/([^/]+)\/state$/.exec(url.pathname);
    if (method === "GET" && stateMatch) {
      const sessionId = decodeURIComponent(stateMatch[1]);
      if (!this.hasSessionAccess(req, sessionId)) {
        this.respondJson(res, 401, { error: "Unauthorized." });
        return true;
      }
      this.respondJson(res, 200, {
        session_id: sessionId,
        state: this.sessionManager.getSessionState(sessionId),
      });
      return true;
    }

    const toolsMatch = /^\/sessions\/([^/]+)\/tools$/.exec(url.pathname);
    if (method === "GET" && toolsMatch) {
      const sessionId = decodeURIComponent(toolsMatch[1]);
      if (!this.hasSessionAccess(req, sessionId)) {
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
      if (!this.hasSessionAccess(req, sessionId)) {
        this.respondJson(res, 401, { error: "Unauthorized." });
        return true;
      }

      res.statusCode = 200;
      res.setHeader("Content-Type", "text/event-stream");
      res.setHeader("Cache-Control", "no-cache");
      res.setHeader("Connection", "keep-alive");
      this.writeSseEvent(res, "snapshot", {
        session_id: sessionId,
        frame: this.sessionManager.getSessionFrame(sessionId),
        state: this.sessionManager.getSessionState(sessionId),
      });

      const interval = setInterval(() => {
        try {
          this.writeSseEvent(res, "snapshot", {
            session_id: sessionId,
            frame: this.sessionManager!.getSessionFrame(sessionId),
            state: this.sessionManager!.getSessionState(sessionId),
          });
        } catch (_error) {
          clearInterval(interval);
          try {
            res.end();
          } catch (_ignored) {
            // ignore broken connection writes
          }
        }
      }, 1000);

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

  private hasSessionAccess(req: any, sessionId: string): boolean {
    if (!this.sessionManager) {
      return false;
    }
    const adminToken = this.resolveAdminToken(req, null);
    if (adminToken && this.sessionManager.validateAdminToken(sessionId, adminToken)) {
      return true;
    }
    const roleToken = this.resolveRoleToken(req, null);
    if (!roleToken) {
      return false;
    }
    return this.sessionManager.validateRoleToken(sessionId, roleToken) !== null;
  }

  private resolveAdminToken(req: any, payload: Record<string, any> | null): string | null {
    const headerToken = this.readHeader(req, "x-admin-token");
    if (headerToken) {
      return headerToken;
    }
    if (payload && typeof payload.admin_token === "string" && payload.admin_token) {
      return payload.admin_token;
    }
    return null;
  }

  private resolveRoleToken(req: any, payload: Record<string, any> | null): string | null {
    const headerToken = this.readHeader(req, "x-role-token");
    if (headerToken) {
      return headerToken;
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
    if (!crypto || typeof crypto.randomBytes !== "function") {
      return `session_${Date.now()}`;
    }
    return `session_${Date.now().toString(36)}_${crypto.randomBytes(4).toString("hex")}`;
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
