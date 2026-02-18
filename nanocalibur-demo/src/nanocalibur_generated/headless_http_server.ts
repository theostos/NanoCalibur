import { HeadlessHost, HeadlessStepInput } from "./headless_host";

declare const require: any;
const http = require("http");

export interface HeadlessHttpServerOptions {
  host?: string;
  port?: number;
}

export class HeadlessHttpServer {
  private readonly host: HeadlessHost;
  private server: any | null = null;
  private port: number | null = null;

  constructor(host: HeadlessHost) {
    this.host = host;
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
