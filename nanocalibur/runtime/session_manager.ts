import { InterpreterState } from "./interpreter";
import { SymbolicFrame } from "./canvas/types";
import {
  SessionCommand,
  SessionRuntime,
  SessionRuntimeOptions,
  SessionTickResult,
} from "./session_runtime";
import { HeadlessHost } from "./headless_host";
import { SessionSeedStore } from "./replay_store_sqlite";

declare const require: any;
const crypto = require("crypto");

export interface SessionRecord {
  id: string;
  seed: string;
  runtime: SessionRuntime;
  createdAt: number;
}

export interface SessionManagerOptions {
  replayStore?: SessionSeedStore;
}

export interface SessionCreateOptions extends SessionRuntimeOptions {
  seed?: string;
  metadata?: Record<string, any>;
}

export class SessionManager {
  private readonly sessions = new Map<string, SessionRecord>();
  private readonly reservedSeeds = new Set<string>();
  private readonly replayStore: SessionSeedStore | null;

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
    const runtime = new SessionRuntime(host, {
      loopMode: options.loopMode,
      roleOrder: options.roleOrder,
      defaultStepSeconds: options.defaultStepSeconds,
    });
    const record: SessionRecord = {
      id: sessionId,
      seed,
      runtime,
      createdAt: Date.now(),
    };
    this.sessions.set(sessionId, record);
    if (this.replayStore) {
      this.replayStore.appendEvent(sessionId, "session_created", {
        seed,
        loopMode: runtime.getLoopMode(),
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
    return this.sessions.delete(sessionId);
  }

  enqueueCommand(sessionId: string, roleId: string, command: SessionCommand): void {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
    }
    session.runtime.enqueue(roleId, command);
  }

  tickSession(sessionId: string, dtSeconds?: number): SessionTickResult {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session '${sessionId}'.`);
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
      const generatedSeed =
        crypto && typeof crypto.randomBytes === "function"
          ? String(crypto.randomBytes(16).toString("hex"))
          : "";
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
}
