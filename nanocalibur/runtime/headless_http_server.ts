import { HeadlessHost, HeadlessStepInput } from "./headless_host";
import { SessionManager } from "./session_manager";
import { SessionCommand } from "./session_runtime";

declare const require: any;
const http = require("http");
const crypto = require("crypto");
const nodeBuffer = require("buffer");

export interface HeadlessHttpServerOptions {
  host?: string;
  port?: number;
}

interface SessionViewer {
  isAdmin: boolean;
  roleId: string | null;
}

interface SessionStreamSubscriber {
  res: any;
  viewer: SessionViewer;
}

interface SessionWebSocketSubscriber {
  socket: any;
  viewer: SessionViewer;
  recvBuffer: any;
}

interface RoleWebSocketInputState {
  lastReceivedSeq: number | null;
  lastAckedServerTick: number | null;
  pendingKeysDown: Set<string>;
  lastAppliedKeysDown: Set<string>;
  pendingButtonsDown: Set<string>;
  lastAppliedButtonsDown: Set<string>;
  pendingMousePosition: { x: number; y: number } | null;
  pendingCommands: SessionCommand[];
}

export class HeadlessHttpServer {
  private readonly host: HeadlessHost;
  private readonly sessionManager: SessionManager | null;
  private readonly hostFactory: (() => HeadlessHost) | null;
  private singleHostSessionClaimed = false;
  private server: any | null = null;
  private port: number | null = null;
  private readonly streamSubscribersBySession = new Map<string, Set<SessionStreamSubscriber>>();
  private readonly webSocketSubscribersBySession = new Map<string, Set<SessionWebSocketSubscriber>>();
  private readonly webSocketInputBySession = new Map<string, Map<string, RoleWebSocketInputState>>();
  private readonly serverTickBySession = new Map<string, number>();
  private readonly runtimeTickersBySession = new Map<string, any>();

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
    server.on("upgrade", (req: any, socket: any, head: any) => {
      this.handleUpgrade(req, socket, head);
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
    this.stopAllSessionRuntimeTickers();
    this.closeAllSessionStreamSubscribers();
    this.closeAllSessionWebSocketSubscribers();
    this.webSocketInputBySession.clear();
    this.serverTickBySession.clear();

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

  private handleUpgrade(req: any, socket: any, head: any): void {
    try {
      if (!this.sessionManager) {
        this.rejectWebSocketUpgrade(socket, 503, "Session manager is not available.");
        return;
      }

      const method = typeof req.method === "string" ? req.method.toUpperCase() : "";
      if (method !== "GET") {
        this.rejectWebSocketUpgrade(socket, 405, "WebSocket upgrade requires GET.");
        return;
      }

      const url = this.parseRequestUrl(req.url);
      const wsMatch = /^\/sessions\/([^/]+)\/ws$/.exec(url.pathname);
      if (!wsMatch) {
        this.rejectWebSocketUpgrade(socket, 404, "Not found.");
        return;
      }

      const sessionId = decodeURIComponent(wsMatch[1]);
      const viewer = this.resolveSessionViewer(req, url, sessionId, null);
      if (!viewer) {
        this.rejectWebSocketUpgrade(socket, 401, "Unauthorized.");
        return;
      }

      const upgradeHeader = (this.readHeader(req, "upgrade") || "").toLowerCase();
      const connectionHeader = (this.readHeader(req, "connection") || "").toLowerCase();
      if (upgradeHeader !== "websocket" || !connectionHeader.includes("upgrade")) {
        this.rejectWebSocketUpgrade(socket, 400, "Invalid WebSocket upgrade headers.");
        return;
      }

      const secKey = this.readHeader(req, "sec-websocket-key");
      const secVersion = this.readHeader(req, "sec-websocket-version");
      if (!secKey || secVersion !== "13") {
        this.rejectWebSocketUpgrade(socket, 400, "Invalid WebSocket handshake.");
        return;
      }

      const accept = this.computeWebSocketAccept(secKey);
      const response = [
        "HTTP/1.1 101 Switching Protocols",
        "Upgrade: websocket",
        "Connection: Upgrade",
        `Sec-WebSocket-Accept: ${accept}`,
        "",
        "",
      ].join("\r\n");
      socket.write(response);

      const subscriber: SessionWebSocketSubscriber = {
        socket,
        viewer,
        recvBuffer: this.toNodeBuffer(head),
      };
      this.registerSessionWebSocketSubscriber(sessionId, subscriber);

      if (subscriber.recvBuffer && subscriber.recvBuffer.length > 0) {
        this.handleWebSocketIncomingData(sessionId, subscriber, null);
      }

      this.sendSnapshotToWebSocketSubscriber(sessionId, subscriber);
      this.ensureSessionRuntimeTicker(sessionId);

      socket.on("data", (chunk: unknown) => {
        this.handleWebSocketIncomingData(sessionId, subscriber, chunk);
      });
      socket.on("close", () => {
        this.unregisterSessionWebSocketSubscriber(sessionId, subscriber);
      });
      socket.on("end", () => {
        this.unregisterSessionWebSocketSubscriber(sessionId, subscriber);
      });
      socket.on("error", () => {
        this.unregisterSessionWebSocketSubscriber(sessionId, subscriber);
      });
    } catch (_error) {
      this.rejectWebSocketUpgrade(socket, 500, "WebSocket upgrade failed.");
    }
  }

  private rejectWebSocketUpgrade(socket: any, statusCode: number, message: string): void {
    if (!socket) {
      return;
    }
    const reason = this.reasonPhrase(statusCode);
    const body = JSON.stringify({ error: message });
    const byteLength = this.byteLength(body);
    const response = [
      `HTTP/1.1 ${statusCode} ${reason}`,
      "Connection: close",
      "Content-Type: application/json; charset=utf-8",
      `Content-Length: ${byteLength}`,
      "",
      "",
      body,
    ].join("\r\n");
    try {
      socket.write(response);
    } catch (_ignored) {
      // ignore broken upgrade socket writes
    } finally {
      try {
        socket.destroy();
      } catch (_ignored) {
        // ignore shutdown errors
      }
    }
  }

  private reasonPhrase(statusCode: number): string {
    if (statusCode === 400) {
      return "Bad Request";
    }
    if (statusCode === 401) {
      return "Unauthorized";
    }
    if (statusCode === 404) {
      return "Not Found";
    }
    if (statusCode === 405) {
      return "Method Not Allowed";
    }
    if (statusCode === 503) {
      return "Service Unavailable";
    }
    return "Internal Server Error";
  }

  private computeWebSocketAccept(key: string): string {
    const guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    return crypto
      .createHash("sha1")
      .update(`${key}${guid}`, "utf8")
      .digest("base64");
  }

  private handleWebSocketIncomingData(
    sessionId: string,
    subscriber: SessionWebSocketSubscriber,
    chunk: unknown,
  ): void {
    const incoming = this.toNodeBuffer(chunk);
    if (incoming && incoming.length > 0) {
      if (subscriber.recvBuffer && subscriber.recvBuffer.length > 0) {
        subscriber.recvBuffer = this.concatBuffers([subscriber.recvBuffer, incoming]);
      } else {
        subscriber.recvBuffer = incoming;
      }
    }

    const buffer = subscriber.recvBuffer;
    if (!buffer || buffer.length < 2) {
      return;
    }

    while (subscriber.recvBuffer && subscriber.recvBuffer.length >= 2) {
      const firstByte = subscriber.recvBuffer[0];
      const secondByte = subscriber.recvBuffer[1];
      const opcode = firstByte & 0x0f;
      const isMasked = (secondByte & 0x80) !== 0;
      let payloadLength = secondByte & 0x7f;
      let offset = 2;

      if (payloadLength === 126) {
        if (subscriber.recvBuffer.length < 4) {
          return;
        }
        payloadLength = subscriber.recvBuffer.readUInt16BE(2);
        offset = 4;
      } else if (payloadLength === 127) {
        if (subscriber.recvBuffer.length < 10) {
          return;
        }
        const highBits = subscriber.recvBuffer.readUInt32BE(2);
        const lowBits = subscriber.recvBuffer.readUInt32BE(6);
        if (highBits !== 0) {
          this.sendWebSocketClose(subscriber.socket);
          this.unregisterSessionWebSocketSubscriber(sessionId, subscriber);
          return;
        }
        payloadLength = lowBits;
        offset = 10;
      }

      let maskingKey: any = null;
      if (isMasked) {
        if (subscriber.recvBuffer.length < offset + 4) {
          return;
        }
        maskingKey = subscriber.recvBuffer.subarray(offset, offset + 4);
        offset += 4;
      }

      if (subscriber.recvBuffer.length < offset + payloadLength) {
        return;
      }

      let payload = subscriber.recvBuffer.subarray(offset, offset + payloadLength);
      subscriber.recvBuffer = subscriber.recvBuffer.subarray(offset + payloadLength);

      if (isMasked) {
        payload = this.unmaskWebSocketPayload(payload, maskingKey);
      }

      if (opcode === 0x8) {
        this.sendWebSocketClose(subscriber.socket);
        this.unregisterSessionWebSocketSubscriber(sessionId, subscriber);
        return;
      }
      if (opcode === 0x9) {
        this.sendWebSocketPong(subscriber.socket, payload);
        continue;
      }
      if (opcode !== 0x1) {
        continue;
      }

      try {
        const text = payload.toString("utf8");
        this.handleWebSocketClientText(sessionId, subscriber, text);
      } catch (_ignored) {
        // ignore malformed text frames
      }
    }
  }

  private handleWebSocketClientText(
    sessionId: string,
    subscriber: SessionWebSocketSubscriber,
    text: string,
  ): void {
    if (!text || typeof text !== "string") {
      return;
    }
    if (!this.sessionManager) {
      return;
    }

    let decoded: unknown;
    try {
      decoded = JSON.parse(text);
    } catch (_ignored) {
      return;
    }
    if (!decoded || typeof decoded !== "object") {
      return;
    }

    const payload = decoded as Record<string, any>;
    const messageType =
      typeof payload.type === "string" ? payload.type.trim().toLowerCase() : "";

    if (messageType === "ping") {
      this.writeWebSocketJson(subscriber.socket, {
        event: "pong",
        data: {
          session_id: sessionId,
          server_tick: this.getSessionServerTick(sessionId),
        },
      });
      return;
    }

    const roleId = subscriber.viewer.roleId;
    if (!roleId) {
      return;
    }

    const state = this.getRoleWebSocketInputState(sessionId, roleId, true);
    if (!state) {
      return;
    }

    const seq = this.normalizeSequence(payload.seq);
    if (
      seq !== null &&
      state.lastReceivedSeq !== null &&
      seq <= state.lastReceivedSeq
    ) {
      return;
    }
    if (seq !== null) {
      state.lastReceivedSeq = seq;
    }

    const clientAckTick = this.normalizeSequence(
      payload.last_acked_server_tick ?? payload.lastAckedServerTick,
    );
    if (clientAckTick !== null) {
      state.lastAckedServerTick = clientAckTick;
    }

    if (messageType === "input") {
      const keysDown = this.normalizeStringArray(payload.keys_down ?? payload.keysDown);
      state.pendingKeysDown = new Set<string>(keysDown);
      const rawButtons = payload.buttons ?? payload.ui_buttons ?? payload.uiButtons;
      const buttons = Array.isArray(rawButtons)
        ? this.normalizeStringArray(rawButtons)
        : rawButtons && typeof rawButtons === "object"
          ? this.normalizeStringArray(
              (rawButtons as { on?: unknown }).on
                ?? (rawButtons as { begin?: unknown }).begin
                ?? [],
            )
          : [];
      state.pendingButtonsDown = new Set<string>(buttons);
      const mousePosition = this.normalizeMousePosition(
        payload.mouse_position ?? payload.mousePosition,
      );
      if (mousePosition) {
        state.pendingMousePosition = mousePosition;
      }

      const inlineCommands = this.normalizeSessionCommands(payload.commands);
      if (inlineCommands.length > 0) {
        state.pendingCommands.push(...inlineCommands);
      }
      return;
    }

    if (messageType === "commands") {
      const commands = this.normalizeSessionCommands(payload.commands);
      if (commands.length > 0) {
        state.pendingCommands.push(...commands);
      }
      return;
    }

    if (messageType === "tool") {
      const toolName = typeof payload.name === "string" ? payload.name : "";
      if (!toolName) {
        return;
      }
      state.pendingCommands.push({
        kind: "tool",
        name: toolName,
        payload:
          payload.payload && typeof payload.payload === "object"
            ? (payload.payload as Record<string, any>)
            : payload.arguments && typeof payload.arguments === "object"
              ? (payload.arguments as Record<string, any>)
              : {},
      });
      return;
    }

    if (messageType === "button") {
      const buttonName = typeof payload.name === "string" ? payload.name : "";
      if (!buttonName) {
        return;
      }
      state.pendingCommands.push({
        kind: "input",
        uiButtons: {
          begin: [buttonName],
          end: [buttonName],
        },
      });
    }
  }

  private sendWebSocketSnapshot(
    subscriber: SessionWebSocketSubscriber,
    payload: Record<string, any>,
  ): void {
    this.writeWebSocketJson(subscriber.socket, {
      event: "snapshot",
      data: payload,
    });
  }

  private sendWebSocketClose(socket: any): void {
    const frame = this.encodeWebSocketFrame(0x8, null);
    if (!frame) {
      try {
        socket.end();
      } catch (_ignored) {
        // ignore close errors
      }
      return;
    }
    try {
      socket.write(frame);
      socket.end();
    } catch (_ignored) {
      // ignore close errors
    }
  }

  private sendWebSocketPong(socket: any, payload: any): void {
    const frame = this.encodeWebSocketFrame(0xA, payload);
    if (!frame) {
      return;
    }
    try {
      socket.write(frame);
    } catch (_ignored) {
      // ignore broken pipe writes
    }
  }

  private writeWebSocketJson(socket: any, payload: Record<string, any>): void {
    const frame = this.encodeWebSocketFrame(0x1, JSON.stringify(payload));
    if (!frame) {
      return;
    }
    socket.write(frame);
  }

  private encodeWebSocketFrame(opcode: number, payload: unknown): any | null {
    const BufferCtor = this.getNodeBufferCtor();
    if (!BufferCtor) {
      return null;
    }
    const body =
      payload == null
        ? BufferCtor.alloc(0)
        : typeof payload === "string"
          ? BufferCtor.from(payload, "utf8")
          : this.toNodeBuffer(payload) || BufferCtor.alloc(0);

    const bodyLength = body.length;
    if (bodyLength < 126) {
      const frame = BufferCtor.alloc(2 + bodyLength);
      frame[0] = 0x80 | (opcode & 0x0f);
      frame[1] = bodyLength;
      body.copy(frame, 2);
      return frame;
    }
    if (bodyLength <= 0xffff) {
      const frame = BufferCtor.alloc(4 + bodyLength);
      frame[0] = 0x80 | (opcode & 0x0f);
      frame[1] = 126;
      frame.writeUInt16BE(bodyLength, 2);
      body.copy(frame, 4);
      return frame;
    }

    const frame = BufferCtor.alloc(10 + bodyLength);
    frame[0] = 0x80 | (opcode & 0x0f);
    frame[1] = 127;
    frame.writeUInt32BE(0, 2);
    frame.writeUInt32BE(bodyLength, 6);
    body.copy(frame, 10);
    return frame;
  }

  private unmaskWebSocketPayload(payload: any, mask: any): any {
    const BufferCtor = this.getNodeBufferCtor();
    if (!BufferCtor || !mask || mask.length !== 4) {
      return payload;
    }
    const out = BufferCtor.alloc(payload.length);
    for (let index = 0; index < payload.length; index += 1) {
      out[index] = payload[index] ^ mask[index % 4];
    }
    return out;
  }

  private getNodeBufferCtor(): any | null {
    if (nodeBuffer && nodeBuffer.Buffer) {
      return nodeBuffer.Buffer;
    }
    return null;
  }

  private toNodeBuffer(value: unknown): any | null {
    const BufferCtor = this.getNodeBufferCtor();
    if (!BufferCtor) {
      return null;
    }
    if (!value) {
      return BufferCtor.alloc(0);
    }
    if (BufferCtor.isBuffer(value)) {
      return value;
    }
    if (typeof value === "string") {
      return BufferCtor.from(value, "utf8");
    }
    if (ArrayBuffer.isView(value)) {
      return BufferCtor.from(value.buffer, value.byteOffset, value.byteLength);
    }
    if (value instanceof ArrayBuffer) {
      return BufferCtor.from(value);
    }
    return null;
  }

  private concatBuffers(chunks: any[]): any {
    const BufferCtor = this.getNodeBufferCtor();
    if (!BufferCtor) {
      return null;
    }
    const normalized = chunks.filter((chunk) => chunk && chunk.length > 0);
    if (normalized.length === 0) {
      return BufferCtor.alloc(0);
    }
    if (normalized.length === 1) {
      return normalized[0];
    }
    return BufferCtor.concat(normalized);
  }

  private byteLength(value: string): number {
    const BufferCtor = this.getNodeBufferCtor();
    if (!BufferCtor) {
      return value.length;
    }
    return BufferCtor.byteLength(value, "utf8");
  }

  private getSessionServerTick(sessionId: string): number {
    const tick = this.serverTickBySession.get(sessionId);
    if (typeof tick === "number" && Number.isFinite(tick) && tick >= 0) {
      return Math.floor(tick);
    }
    return 0;
  }

  private bumpSessionServerTick(sessionId: string): number {
    const next = this.getSessionServerTick(sessionId) + 1;
    this.serverTickBySession.set(sessionId, next);
    return next;
  }

  private getRoleWebSocketInputState(
    sessionId: string,
    roleId: string,
    createIfMissing = false,
  ): RoleWebSocketInputState | null {
    let byRole = this.webSocketInputBySession.get(sessionId);
    if (!byRole) {
      if (!createIfMissing) {
        return null;
      }
      byRole = new Map<string, RoleWebSocketInputState>();
      this.webSocketInputBySession.set(sessionId, byRole);
    }
    let state = byRole.get(roleId);
    if (!state && createIfMissing) {
      state = {
        lastReceivedSeq: null,
        lastAckedServerTick: null,
        pendingKeysDown: new Set<string>(),
        lastAppliedKeysDown: new Set<string>(),
        pendingButtonsDown: new Set<string>(),
        lastAppliedButtonsDown: new Set<string>(),
        pendingMousePosition: null,
        pendingCommands: [],
      };
      byRole.set(roleId, state);
    }
    return state || null;
  }

  private getRoleAckSeq(sessionId: string, roleId: string | null): number | null {
    if (!roleId) {
      return null;
    }
    const state = this.getRoleWebSocketInputState(sessionId, roleId, false);
    if (!state || typeof state.lastReceivedSeq !== "number") {
      return null;
    }
    return Math.floor(state.lastReceivedSeq);
  }

  private clearRolePendingInputs(sessionId: string, roleId: string | null): void {
    if (!roleId) {
      return;
    }
    const state = this.getRoleWebSocketInputState(sessionId, roleId, false);
    if (!state) {
      return;
    }
    state.pendingKeysDown = new Set<string>();
    state.pendingButtonsDown = new Set<string>();
    state.lastAppliedButtonsDown = new Set<string>();
    state.pendingMousePosition = null;
    state.pendingCommands = [];
  }

  private normalizeStringArray(value: unknown): string[] {
    if (!Array.isArray(value)) {
      return [];
    }
    const out: string[] = [];
    const seen = new Set<string>();
    for (const entry of value) {
      if (typeof entry !== "string" || !entry) {
        continue;
      }
      if (seen.has(entry)) {
        continue;
      }
      seen.add(entry);
      out.push(entry);
    }
    return out;
  }

  private normalizeMousePosition(value: unknown): { x: number; y: number } | null {
    if (!value || typeof value !== "object") {
      return null;
    }
    const payload = value as { x?: unknown; y?: unknown };
    if (typeof payload.x !== "number" || !Number.isFinite(payload.x)) {
      return null;
    }
    if (typeof payload.y !== "number" || !Number.isFinite(payload.y)) {
      return null;
    }
    return { x: payload.x, y: payload.y };
  }

  private normalizeSequence(value: unknown): number | null {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      return null;
    }
    const seq = Math.floor(value);
    if (seq < 0) {
      return null;
    }
    return seq;
  }

  private applyPendingWebSocketInputs(sessionId: string): void {
    if (!this.sessionManager) {
      return;
    }
    const byRole = this.webSocketInputBySession.get(sessionId);
    if (!byRole || byRole.size === 0) {
      return;
    }

    for (const [roleId, state] of byRole.entries()) {
      while (state.pendingCommands.length > 0) {
        const command = state.pendingCommands.shift();
        if (!command) {
          continue;
        }
        try {
          this.sessionManager.enqueueCommand(sessionId, roleId, command);
        } catch (_ignored) {
          break;
        }
      }

      const on = Array.from(state.pendingKeysDown.values());
      const begin = on.filter((key) => !state.lastAppliedKeysDown.has(key));
      const end = Array.from(state.lastAppliedKeysDown.values()).filter(
        (key) => !state.pendingKeysDown.has(key),
      );
      const buttonsOn = Array.from(state.pendingButtonsDown.values());
      const buttonsBegin = buttonsOn.filter(
        (name) => !state.lastAppliedButtonsDown.has(name),
      );
      const buttonsEnd = Array.from(state.lastAppliedButtonsDown.values()).filter(
        (name) => !state.pendingButtonsDown.has(name),
      );
      const shouldEmitInput =
        begin.length > 0
        || on.length > 0
        || end.length > 0
        || buttonsBegin.length > 0
        || buttonsOn.length > 0
        || buttonsEnd.length > 0;
      if (shouldEmitInput) {
        const keyboardPayload: HeadlessStepInput["keyboard"] = {
          begin,
          on,
          end,
        };
        const uiButtonsPayload: HeadlessStepInput["uiButtons"] = {
          begin: buttonsBegin,
          on: buttonsOn,
          end: buttonsEnd,
        };
        const command: SessionCommand = {
          kind: "input",
          keyboard: keyboardPayload,
          uiButtons: uiButtonsPayload,
          mousePosition: state.pendingMousePosition || undefined,
        };
        try {
          this.sessionManager.enqueueCommand(sessionId, roleId, command);
        } catch (_ignored) {
          // ignore stale role/session command injection.
        }
      }

      state.lastAppliedKeysDown = new Set<string>(state.pendingKeysDown);
      state.lastAppliedButtonsDown = new Set<string>(state.pendingButtonsDown);
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
      this.serverTickBySession.set(created.id, 0);
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
      this.ensureSessionRuntimeTicker(sessionId);
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
      this.stopSessionRuntimeTicker(sessionId);
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
      if (shouldTick) {
        this.bumpSessionServerTick(sessionId);
      }
      this.respondJson(res, 200, {
        frame: this.sessionManager.getSessionFrameForRole(sessionId, roleBinding.roleId),
        state: this.scopeStateForViewer(result.state, {
          isAdmin: false,
          roleId: roleBinding.roleId,
        }),
        server_tick: this.getSessionServerTick(sessionId),
        ack_seq: this.getRoleAckSeq(sessionId, roleBinding.roleId),
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

    const snapshotMatch = /^\/sessions\/([^/]+)\/snapshot$/.exec(url.pathname);
    if (method === "GET" && snapshotMatch) {
      const sessionId = decodeURIComponent(snapshotMatch[1]);
      const viewer = this.resolveSessionViewer(req, url, sessionId, null);
      if (!viewer) {
        this.respondJson(res, 401, { error: "Unauthorized." });
        return true;
      }
      this.respondJson(
        res,
        200,
        this.buildSessionSnapshotPayload(sessionId, viewer),
      );
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
      const subscriber: SessionStreamSubscriber = { res, viewer };
      this.registerSessionStreamSubscriber(sessionId, subscriber);
      this.sendSnapshotToSubscriber(sessionId, subscriber);
      this.ensureSessionRuntimeTicker(sessionId);
      req.on("close", () => {
        this.unregisterSessionStreamSubscriber(sessionId, subscriber);
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
      if (kind === "input") {
        const rawUiButtons = (item as { uiButtons?: unknown }).uiButtons;
        const normalizedUiButtons: HeadlessStepInput["uiButtons"] =
          rawUiButtons && typeof rawUiButtons === "object" && !Array.isArray(rawUiButtons)
            ? {
                begin: this.normalizeStringArray(
                  (rawUiButtons as { begin?: unknown }).begin || [],
                ),
                on: this.normalizeStringArray(
                  (rawUiButtons as { on?: unknown }).on || [],
                ),
                end: this.normalizeStringArray(
                  (rawUiButtons as { end?: unknown }).end || [],
                ),
              }
            : Array.isArray(rawUiButtons)
              ? { begin: this.normalizeStringArray(rawUiButtons) }
              : undefined;
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
          uiButtons: normalizedUiButtons,
          mousePosition: this.normalizeMousePosition(
            (item as { mousePosition?: unknown }).mousePosition
              ?? (item as { mouse_position?: unknown }).mouse_position,
          ) || undefined,
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

  private buildSessionSnapshotPayload(
    sessionId: string,
    viewer: SessionViewer,
    stateOverride?: Record<string, any>,
    serverTickOverride?: number,
  ): Record<string, any> {
    if (!this.sessionManager) {
      throw new Error("Session manager is not available.");
    }
    const state = stateOverride || this.sessionManager.getSessionState(sessionId);
    const serverTick =
      typeof serverTickOverride === "number" && Number.isFinite(serverTickOverride)
        ? Math.max(0, Math.floor(serverTickOverride))
        : this.getSessionServerTick(sessionId);
    const ackSeq = this.getRoleAckSeq(sessionId, viewer.roleId);
    return {
      session_id: sessionId,
      frame: this.sessionManager.getSessionFrameForRole(sessionId, viewer.roleId),
      state: this.scopeStateForViewer(state, viewer),
      server_tick: serverTick,
      ack_seq: ackSeq,
    };
  }

  private sendSnapshotToSubscriber(
    sessionId: string,
    subscriber: SessionStreamSubscriber,
    stateOverride?: Record<string, any>,
    serverTickOverride?: number,
  ): void {
    this.writeSseEvent(
      subscriber.res,
      "snapshot",
      this.buildSessionSnapshotPayload(
        sessionId,
        subscriber.viewer,
        stateOverride,
        serverTickOverride,
      ),
    );
  }

  private sendSnapshotToWebSocketSubscriber(
    sessionId: string,
    subscriber: SessionWebSocketSubscriber,
    stateOverride?: Record<string, any>,
    serverTickOverride?: number,
  ): void {
    this.sendWebSocketSnapshot(
      subscriber,
      this.buildSessionSnapshotPayload(
        sessionId,
        subscriber.viewer,
        stateOverride,
        serverTickOverride,
      ),
    );
  }

  private registerSessionStreamSubscriber(
    sessionId: string,
    subscriber: SessionStreamSubscriber,
  ): void {
    const existing = this.streamSubscribersBySession.get(sessionId);
    if (existing) {
      existing.add(subscriber);
      return;
    }
    this.streamSubscribersBySession.set(sessionId, new Set([subscriber]));
  }

  private unregisterSessionStreamSubscriber(
    sessionId: string,
    subscriber: SessionStreamSubscriber,
  ): void {
    const subscribers = this.streamSubscribersBySession.get(sessionId);
    if (!subscribers) {
      return;
    }
    subscribers.delete(subscriber);
    if (subscribers.size === 0) {
      this.streamSubscribersBySession.delete(sessionId);
    }
  }

  private registerSessionWebSocketSubscriber(
    sessionId: string,
    subscriber: SessionWebSocketSubscriber,
  ): void {
    const existing = this.webSocketSubscribersBySession.get(sessionId);
    if (existing) {
      existing.add(subscriber);
      return;
    }
    this.webSocketSubscribersBySession.set(sessionId, new Set([subscriber]));
  }

  private unregisterSessionWebSocketSubscriber(
    sessionId: string,
    subscriber: SessionWebSocketSubscriber,
  ): void {
    const subscribers = this.webSocketSubscribersBySession.get(sessionId);
    if (!subscribers) {
      return;
    }
    subscribers.delete(subscriber);
    this.clearRolePendingInputs(sessionId, subscriber.viewer.roleId);
    if (subscribers.size === 0) {
      this.webSocketSubscribersBySession.delete(sessionId);
    }
  }

  private ensureSessionRuntimeTicker(sessionId: string): void {
    if (!this.sessionManager || this.runtimeTickersBySession.has(sessionId)) {
      return;
    }

    const status = this.sessionManager.getSessionStatus(sessionId);
    if (status !== "running") {
      return;
    }

    const session = this.sessionManager.getSession(sessionId);
    const stepSeconds =
      session && session.runtime
        ? session.runtime.getDefaultStepSeconds()
        : 1 / 20;
    const intervalMs = Math.max(10, Math.round(stepSeconds * 1000));
    const interval = setInterval(() => {
      this.tickSessionAndBroadcastSnapshot(sessionId, stepSeconds);
    }, intervalMs);
    this.runtimeTickersBySession.set(sessionId, interval);
  }

  private stopSessionRuntimeTicker(sessionId: string): void {
    const interval = this.runtimeTickersBySession.get(sessionId);
    if (!interval) {
      return;
    }
    clearInterval(interval);
    this.runtimeTickersBySession.delete(sessionId);
  }

  private stopAllSessionRuntimeTickers(): void {
    for (const interval of this.runtimeTickersBySession.values()) {
      clearInterval(interval);
    }
    this.runtimeTickersBySession.clear();
  }

  private closeAllSessionStreamSubscribers(): void {
    for (const subscribers of this.streamSubscribersBySession.values()) {
      for (const subscriber of subscribers) {
        try {
          subscriber.res.end();
        } catch (_ignored) {
          // ignore broken pipe on shutdown
        }
      }
    }
    this.streamSubscribersBySession.clear();
  }

  private closeAllSessionWebSocketSubscribers(): void {
    for (const subscribers of this.webSocketSubscribersBySession.values()) {
      for (const subscriber of subscribers) {
        try {
          this.sendWebSocketClose(subscriber.socket);
        } catch (_ignored) {
          // ignore websocket shutdown errors
        }
      }
    }
    this.webSocketSubscribersBySession.clear();
  }

  private tickSessionAndBroadcastSnapshot(
    sessionId: string,
    stepSeconds: number,
  ): void {
    if (!this.sessionManager) {
      this.stopSessionRuntimeTicker(sessionId);
      return;
    }

    let state: Record<string, any>;
    let serverTick = this.getSessionServerTick(sessionId);
    try {
      this.applyPendingWebSocketInputs(sessionId);
      const result = this.sessionManager.tickSession(sessionId, stepSeconds);
      state = result.state as Record<string, any>;
      serverTick = this.bumpSessionServerTick(sessionId);
    } catch (_error) {
      this.stopSessionRuntimeTicker(sessionId);
      const streamSubscribers = this.streamSubscribersBySession.get(sessionId);
      if (streamSubscribers && streamSubscribers.size > 0) {
        for (const subscriber of streamSubscribers) {
          try {
            subscriber.res.end();
          } catch (_ignored) {
            // ignore broken connection writes
          }
        }
        this.streamSubscribersBySession.delete(sessionId);
      }
      const webSocketSubscribers = this.webSocketSubscribersBySession.get(sessionId);
      if (webSocketSubscribers && webSocketSubscribers.size > 0) {
        for (const subscriber of webSocketSubscribers) {
          try {
            this.sendWebSocketClose(subscriber.socket);
          } catch (_ignored) {
            // ignore broken websocket writes
          }
        }
        this.webSocketSubscribersBySession.delete(sessionId);
      }
      return;
    }

    const streamSubscribers = this.streamSubscribersBySession.get(sessionId);
    const webSocketSubscribers = this.webSocketSubscribersBySession.get(sessionId);
    const hasStreamSubscribers = Boolean(streamSubscribers && streamSubscribers.size > 0);
    const hasWebSocketSubscribers = Boolean(
      webSocketSubscribers && webSocketSubscribers.size > 0,
    );
    if (!hasStreamSubscribers && !hasWebSocketSubscribers) {
      return;
    }

    if (streamSubscribers) {
      for (const subscriber of Array.from(streamSubscribers)) {
        try {
          this.sendSnapshotToSubscriber(sessionId, subscriber, state, serverTick);
        } catch (_error) {
          this.unregisterSessionStreamSubscriber(sessionId, subscriber);
          try {
            subscriber.res.end();
          } catch (_ignored) {
            // ignore broken connection writes
          }
        }
      }
    }

    if (webSocketSubscribers) {
      for (const subscriber of Array.from(webSocketSubscribers)) {
        try {
          this.sendSnapshotToWebSocketSubscriber(sessionId, subscriber, state, serverTick);
        } catch (_error) {
          this.unregisterSessionWebSocketSubscriber(sessionId, subscriber);
          try {
            this.sendWebSocketClose(subscriber.socket);
          } catch (_ignored) {
            // ignore broken websocket writes
          }
        }
      }
    }
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
