import { InterpreterState } from "./interpreter";
import { SymbolicFrame } from "./canvas/types";
import {
  SessionCommand,
  SessionLoopMode,
  SessionPaceConfig,
  SessionRuntime,
  SessionRuntimeOptions,
  SessionTickResult,
} from "./session_runtime";
import { HeadlessHost } from "./headless_host";
import { SessionSeedStore } from "./replay_store_sqlite";

declare const require: any;
const crypto = require("crypto");

export type SessionStatus = "created" | "running" | "stopped";

export interface SessionRoleConfig {
  id: string;
  kind?: string;
  type?: string;
  required?: boolean;
}

export interface SessionRoleView {
  role_id: string;
  role_kind: string;
  role_type: string;
  required: boolean;
  connected: boolean;
  open: boolean;
}

interface SessionRoleRecord {
  id: string;
  kind: string;
  required: boolean;
  connected: boolean;
  inviteToken: string;
  accessToken: string | null;
  joinedAt: number | null;
}

export interface SessionRecord {
  id: string;
  seed: string;
  runtime: SessionRuntime;
  createdAt: number;
  status: SessionStatus;
  adminToken: string;
  roles: Map<string, SessionRoleRecord>;
}

export interface SessionManagerOptions {
  replayStore?: SessionSeedStore;
}

export interface SessionCreateOptions extends SessionRuntimeOptions {
  seed?: string;
  metadata?: Record<string, any>;
  roles?: SessionRoleConfig[];
}

export class SessionManager {
  private readonly sessions = new Map<string, SessionRecord>();
  private readonly reservedSeeds = new Set<string>();
  private readonly replayStore: SessionSeedStore | null;
  private readonly inviteTokenIndex = new Map<string, { sessionId: string; roleId: string }>();
  private readonly accessTokenIndex = new Map<string, { sessionId: string; roleId: string }>();

  constructor(options: SessionManagerOptions = {}) {
    this.replayStore = options.replayStore || null;
  }

  createSession(
    sessionId: string,
    host: HeadlessHost,
    options: SessionCreateOptions = {},
  ): SessionRecord {
    if (!sessionId || typeof sessionId !== "string") {
      throw new Error("Session id must be a non-empty string.");
    }
    if (this.sessions.has(sessionId)) {
      throw new Error(`Session '${sessionId}' already exists.`);
    }

    const seed = this.reserveUniqueSeed(sessionId, options.seed, options.metadata || {});
    const roleRecords = this.buildRoleRecords(options.roles);
    const runtimeRoleOrder =
      Array.isArray(options.roleOrder) && options.roleOrder.length > 0
        ? options.roleOrder
        : Array.from(roleRecords.keys());
    const runtime = new SessionRuntime(host, {
      loopMode: options.loopMode,
      roleOrder: runtimeRoleOrder,
      defaultStepSeconds: options.defaultStepSeconds,
      pace: options.pace,
    });

    const adminToken = this.generateToken();
    for (const role of roleRecords.values()) {
      this.inviteTokenIndex.set(role.inviteToken, {
        sessionId,
        roleId: role.id,
      });
    }

    const record: SessionRecord = {
      id: sessionId,
      seed,
      runtime,
      createdAt: Date.now(),
      status: "created",
      adminToken,
      roles: roleRecords,
    };

    this.sessions.set(sessionId, record);

    if (this.replayStore) {
      this.replayStore.appendEvent(sessionId, "session_created", {
        seed,
        loopMode: runtime.getLoopMode(),
        roleCount: record.roles.size,
      });
    }
    return record;
  }

  getSession(sessionId: string): SessionRecord | null {
    return this.sessions.get(sessionId) || null;
  }

  listSessionIds(): string[] {
    return Array.from(this.sessions.keys());
  }

  removeSession(sessionId: string): boolean {
    const record = this.sessions.get(sessionId);
    if (!record) {
      return false;
    }
    this.sessions.delete(sessionId);
    for (const role of record.roles.values()) {
      this.inviteTokenIndex.delete(role.inviteToken);
      if (role.accessToken) {
        this.accessTokenIndex.delete(role.accessToken);
      }
    }
    return true;
  }

  startSession(sessionId: string, adminToken: string): SessionStatus {
    const session = this.requireAdminSession(sessionId, adminToken);
    for (const role of session.roles.values()) {
      if (role.required && !role.connected) {
        throw new Error(
          `Session '${sessionId}' cannot start: required role '${role.id}' is not connected.`,
        );
      }
    }
    session.status = "running";
    if (this.replayStore) {
      this.replayStore.appendEvent(sessionId, "session_started", {});
    }
    return session.status;
  }

  stopSession(sessionId: string, adminToken: string): SessionStatus {
    const session = this.requireAdminSession(sessionId, adminToken);
    session.status = "stopped";
    if (this.replayStore) {
      this.replayStore.appendEvent(sessionId, "session_stopped", {});
    }
    return session.status;
  }

  getSessionStatus(sessionId: string): SessionStatus {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    return session.status;
  }

  listSessionInvites(
    sessionId: string,
    adminToken: string,
  ): Array<SessionRoleView & { invite_token: string }> {
    const session = this.requireAdminSession(sessionId, adminToken);
    return Array.from(session.roles.values()).map((role) => ({
      role_id: role.id,
      role_kind: role.kind,
      role_type: role.kind,
      required: role.required,
      connected: role.connected,
      open: role.accessToken === null,
      invite_token: role.inviteToken,
    }));
  }

  listOpenRoles(sessionId: string): SessionRoleView[] {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    return this.buildOpenRoleViews(session);
  }

  listAllOpenRoles(): Array<{ session_id: string } & SessionRoleView> {
    const out: Array<{ session_id: string } & SessionRoleView> = [];
    for (const [sessionId, session] of this.sessions.entries()) {
      for (const role of this.buildOpenRoleViews(session)) {
        out.push({
          session_id: sessionId,
          ...role,
        });
      }
    }
    return out;
  }

  listSessionRoles(sessionId: string): SessionRoleView[] {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    return Array.from(session.roles.values()).map((role) => ({
      role_id: role.id,
      role_kind: role.kind,
      role_type: role.kind,
      required: role.required,
      connected: role.connected,
      open: role.accessToken === null,
    }));
  }

  listSessionsSummary(): Array<{
    session_id: string;
    status: SessionStatus;
    loop_mode: SessionLoopMode;
    roles: SessionRoleView[];
  }> {
    const out: Array<{
      session_id: string;
      status: SessionStatus;
      loop_mode: SessionLoopMode;
      roles: SessionRoleView[];
    }> = [];
    for (const session of this.sessions.values()) {
      out.push({
        session_id: session.id,
        status: session.status,
        loop_mode: session.runtime.getLoopMode(),
        roles: this.listSessionRoles(session.id),
      });
    }
    return out;
  }

  joinWithInviteToken(inviteToken: string): {
    sessionId: string;
    roleId: string;
    accessToken: string;
  } {
    const binding = this.inviteTokenIndex.get(inviteToken);
    if (!binding) {
      throw new Error("Invalid invite token.");
    }
    const session = this.sessions.get(binding.sessionId);
    if (!session) {
      throw new Error(`Unknown session '${binding.sessionId}'.`);
    }
    const role = session.roles.get(binding.roleId);
    if (!role) {
      throw new Error(`Unknown role '${binding.roleId}'.`);
    }

    if (role.accessToken) {
      this.accessTokenIndex.delete(role.accessToken);
    }

    const accessToken = this.generateToken();
    role.accessToken = accessToken;
    role.connected = true;
    role.joinedAt = Date.now();
    this.accessTokenIndex.set(accessToken, {
      sessionId: session.id,
      roleId: role.id,
    });

    if (this.replayStore) {
      this.replayStore.appendEvent(session.id, "role_joined", {
        roleId: role.id,
      });
    }

    return {
      sessionId: session.id,
      roleId: role.id,
      accessToken,
    };
  }

  validateAdminToken(sessionId: string, adminToken: string): boolean {
    const session = this.sessions.get(sessionId);
    if (!session) {
      return false;
    }
    return session.adminToken === adminToken;
  }

  validateRoleToken(sessionId: string, accessToken: string): { roleId: string } | null {
    const binding = this.accessTokenIndex.get(accessToken);
    if (!binding || binding.sessionId !== sessionId) {
      return null;
    }
    return { roleId: binding.roleId };
  }

  getAdminToken(sessionId: string): string {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    return session.adminToken;
  }

  enqueueCommand(sessionId: string, roleId: string, command: SessionCommand): void {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    if (!session.roles.has(roleId)) {
      throw new Error(`Unknown role '${roleId}' in session '${sessionId}'.`);
    }
    session.runtime.enqueue(roleId, command);
  }

  enqueueAuthorizedCommands(
    sessionId: string,
    accessToken: string,
    commands: SessionCommand[],
  ): void {
    const role = this.validateRoleToken(sessionId, accessToken);
    if (!role) {
      throw new Error("Invalid role access token.");
    }
    for (const command of commands) {
      this.enqueueCommand(sessionId, role.roleId, command);
    }
  }

  tickSession(sessionId: string, dtSeconds?: number): SessionTickResult {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    if (session.status !== "running") {
      return {
        frame: session.runtime.getHost().getSymbolicFrame(),
        state: session.runtime.getHost().getState(),
      };
    }

    const result = session.runtime.tick(dtSeconds);
    if (this.replayStore) {
      this.replayStore.appendEvent(
        sessionId,
        "tick",
        {
          dtSeconds:
            typeof dtSeconds === "number" && Number.isFinite(dtSeconds)
              ? dtSeconds
              : undefined,
        },
        result.state.scene && typeof result.state.scene.elapsed === "number"
          ? result.state.scene.elapsed
          : undefined,
      );
    }
    return result;
  }

  getSessionState(sessionId: string): InterpreterState {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    return session.runtime.getHost().getState();
  }

  getSessionFrame(sessionId: string): SymbolicFrame {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    return session.runtime.getHost().getSymbolicFrame();
  }

  getSessionFrameForRole(sessionId: string, roleId: string | null): SymbolicFrame {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    const role =
      typeof roleId === "string" && roleId ? session.roles.get(roleId) || null : null;
    return session.runtime.getHost().getSymbolicFrame({
      roleId,
      roleKind: role ? role.kind : null,
    });
  }

  getSessionTools(sessionId: string): Array<{ name: string; tool_docstring: string; action: string; role_id?: string }> {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    return session.runtime.getHost().listTools();
  }

  updateSessionPace(
    sessionId: string,
    pace: SessionPaceConfig,
    adminToken?: string,
  ): { gameTimeScale: number; maxCatchupSteps: number } {
    if (adminToken) {
      this.requireAdminSession(sessionId, adminToken);
    }
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    session.runtime.setPace(pace);
    const resolved = session.runtime.getPace();
    if (this.replayStore) {
      this.replayStore.appendEvent(sessionId, "pace_updated", {
        gameTimeScale: resolved.gameTimeScale,
        maxCatchupSteps: resolved.maxCatchupSteps,
      });
    }
    return resolved;
  }

  private requireAdminSession(sessionId: string, adminToken: string): SessionRecord {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    if (session.adminToken !== adminToken) {
      throw new Error("Invalid admin token.");
    }
    return session;
  }

  private buildOpenRoleViews(session: SessionRecord): SessionRoleView[] {
    return Array.from(session.roles.values())
      .filter((role) => role.accessToken === null)
      .map((role) => ({
        role_id: role.id,
        role_kind: role.kind,
        role_type: role.kind,
        required: role.required,
        connected: role.connected,
        open: role.accessToken === null,
      }));
  }

  private buildRoleRecords(roleConfigs: SessionRoleConfig[] | undefined): Map<string, SessionRoleRecord> {
    const source =
      Array.isArray(roleConfigs) && roleConfigs.length > 0
        ? roleConfigs
        : [
            {
              id: "default",
              kind: "hybrid",
              required: true,
            },
          ];

    const byId = new Map<string, SessionRoleRecord>();
    for (const item of source) {
      if (!item || typeof item.id !== "string" || !item.id) {
        throw new Error("Each role requires a non-empty 'id'.");
      }
      if (byId.has(item.id)) {
        throw new Error(`Duplicate role id '${item.id}'.`);
      }
      const record: SessionRoleRecord = {
        id: item.id,
        kind: this.normalizeRoleKind(item),
        required: item.required !== false,
        connected: false,
        inviteToken: this.generateToken(),
        accessToken: null,
        joinedAt: null,
      };
      byId.set(record.id, record);
    }

    return byId;
  }

  private normalizeRoleKind(item: SessionRoleConfig): string {
    const source =
      typeof item.kind === "string" && item.kind
        ? item.kind
        : typeof item.type === "string" && item.type
          ? item.type
          : "hybrid";
    const normalized = source.trim().toLowerCase();
    if (normalized === "human" || normalized === "ai" || normalized === "hybrid") {
      return normalized;
    }
    throw new Error(
      `Unsupported role kind '${source}'. Expected one of: human, ai, hybrid.`,
    );
  }

  private reserveUniqueSeed(
    sessionId: string,
    requestedSeed: string | undefined,
    metadata: Record<string, any>,
  ): string {
    if (requestedSeed !== undefined) {
      const normalized = this.normalizeSeed(requestedSeed);
      if (this.isSeedReserved(normalized)) {
        throw new Error(`Seed '${normalized}' is already reserved by another session.`);
      }
      this.reserveSeedInStore(sessionId, normalized, metadata);
      this.reservedSeeds.add(normalized);
      return normalized;
    }

    for (let attempt = 0; attempt < 1024; attempt += 1) {
      const generatedSeed = this.generateToken(16);
      if (!generatedSeed) {
        throw new Error("Node crypto.randomBytes(...) is unavailable.");
      }
      if (this.isSeedReserved(generatedSeed)) {
        continue;
      }
      try {
        this.reserveSeedInStore(sessionId, generatedSeed, metadata);
      } catch (_error) {
        continue;
      }
      this.reservedSeeds.add(generatedSeed);
      return generatedSeed;
    }

    throw new Error("Failed to reserve a unique seed after multiple attempts.");
  }

  private normalizeSeed(seed: string): string {
    if (typeof seed !== "string" || seed.trim().length === 0) {
      throw new Error("Session seed must be a non-empty string.");
    }
    return seed.trim();
  }

  private isSeedReserved(seed: string): boolean {
    if (this.reservedSeeds.has(seed)) {
      return true;
    }
    if (this.replayStore && this.replayStore.hasSeed(seed)) {
      return true;
    }
    return false;
  }

  private reserveSeedInStore(
    sessionId: string,
    seed: string,
    metadata: Record<string, any>,
  ): void {
    if (!this.replayStore) {
      return;
    }
    this.replayStore.reserveSeed(sessionId, seed, metadata);
  }

  private generateToken(bytes = 24): string {
    if (!crypto || typeof crypto.randomBytes !== "function") {
      throw new Error("Node crypto.randomBytes(...) is unavailable.");
    }
    return String(crypto.randomBytes(bytes).toString("hex"));
  }
}
