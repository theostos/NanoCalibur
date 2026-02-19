import { InterpreterState } from "./interpreter";
import { SymbolicFrame } from "./canvas/types";
import {
  SessionCommand,
  SessionRuntime,
  SessionRuntimeOptions,
  SessionTickResult,
} from "./session_runtime";
import { HeadlessHost } from "./headless_host";

export interface SessionRecord {
  id: string;
  runtime: SessionRuntime;
  createdAt: number;
}

export class SessionManager {
  private readonly sessions = new Map<string, SessionRecord>();

  createSession(
    sessionId: string,
    host: HeadlessHost,
    options: SessionRuntimeOptions = {},
  ): SessionRecord {
    if (!sessionId || typeof sessionId !== "string") {
      throw new Error("Session id must be a non-empty string.");
    }
    if (this.sessions.has(sessionId)) {
      throw new Error(`Session '${sessionId}' already exists.`);
    }

    const record: SessionRecord = {
      id: sessionId,
      runtime: new SessionRuntime(host, options),
      createdAt: Date.now(),
    };
    this.sessions.set(sessionId, record);
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
    return session.runtime.tick(dtSeconds);
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
}
