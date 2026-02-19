import { HeadlessHost, HeadlessStepInput } from "./headless_host";
import { InterpreterState } from "./interpreter";
import { SymbolicFrame } from "./canvas/types";

export type SessionLoopMode = "real_time" | "turn_based" | "hybrid";

export type SessionCommand =
  | {
      kind: "tool";
      name: string;
      payload?: Record<string, any>;
    }
  | {
      kind: "input";
      keyboard?: HeadlessStepInput["keyboard"];
      mouse?: HeadlessStepInput["mouse"];
      uiButtons?: string[];
    }
  | {
      kind: "button";
      name: string;
    }
  | {
      kind: "noop";
    };

export interface SessionRuntimeOptions {
  loopMode?: SessionLoopMode;
  roleOrder?: string[];
  defaultStepSeconds?: number;
  pace?: SessionPaceConfig;
}

export interface SessionTickResult {
  frame: SymbolicFrame;
  state: InterpreterState;
}

export interface SessionPaceConfig {
  gameTimeScale?: number;
  maxCatchupSteps?: number;
}

export class SessionRuntime {
  private readonly host: HeadlessHost;
  private readonly loopMode: SessionLoopMode;
  private readonly roleOrder: string[];
  private readonly pendingByRole: Map<string, SessionCommand[]>;
  private readonly defaultStepSeconds: number;
  private gameTimeScale: number;
  private maxCatchupSteps: number;
  private lastSteppedAtMs: number;

  constructor(host: HeadlessHost, options: SessionRuntimeOptions = {}) {
    this.host = host;
    this.loopMode = options.loopMode || "real_time";
    const order = Array.isArray(options.roleOrder)
      ? options.roleOrder.filter((entry) => typeof entry === "string" && entry.length > 0)
      : [];
    this.roleOrder = order.length > 0 ? [...order] : ["default"];
    this.pendingByRole = new Map<string, SessionCommand[]>();
    for (const roleId of this.roleOrder) {
      this.pendingByRole.set(roleId, []);
    }
    this.defaultStepSeconds =
      typeof options.defaultStepSeconds === "number" && Number.isFinite(options.defaultStepSeconds)
        ? options.defaultStepSeconds
        : 1 / 60;
    this.gameTimeScale = 1.0;
    this.maxCatchupSteps = 1;
    this.lastSteppedAtMs = 0;
    this.setPace(options.pace || {});
  }

  getLoopMode(): SessionLoopMode {
    return this.loopMode;
  }

  getDefaultStepSeconds(): number {
    return this.defaultStepSeconds;
  }

  getRoleOrder(): string[] {
    return [...this.roleOrder];
  }

  getHost(): HeadlessHost {
    return this.host;
  }

  getPace(): { gameTimeScale: number; maxCatchupSteps: number } {
    return {
      gameTimeScale: this.gameTimeScale,
      maxCatchupSteps: this.maxCatchupSteps,
    };
  }

  setPace(pace: SessionPaceConfig): void {
    if (pace && typeof pace.gameTimeScale === "number") {
      if (!Number.isFinite(pace.gameTimeScale) || pace.gameTimeScale <= 0 || pace.gameTimeScale > 1) {
        throw new Error("pace.gameTimeScale must be > 0 and <= 1.");
      }
      this.gameTimeScale = pace.gameTimeScale;
    }
    if (pace && typeof pace.maxCatchupSteps === "number") {
      if (!Number.isFinite(pace.maxCatchupSteps) || pace.maxCatchupSteps <= 0) {
        throw new Error("pace.maxCatchupSteps must be > 0.");
      }
      this.maxCatchupSteps = Math.max(1, Math.floor(pace.maxCatchupSteps));
    }
  }

  enqueue(roleId: string, command: SessionCommand): void {
    if (!this.pendingByRole.has(roleId)) {
      throw new Error(`Unknown role '${roleId}'.`);
    }
    const queue = this.pendingByRole.get(roleId);
    if (!queue) {
      throw new Error(`Missing command queue for role '${roleId}'.`);
    }
    queue.push(command);
  }

  tick(dtSeconds: number = this.defaultStepSeconds): SessionTickResult {
    const nowMs = Date.now();
    const targetStepSeconds =
      typeof dtSeconds === "number" && Number.isFinite(dtSeconds) && dtSeconds > 0
        ? dtSeconds
        : this.defaultStepSeconds;

    if (this.loopMode === "turn_based") {
      this.tickTurnBased(targetStepSeconds);
      return {
        frame: this.host.getSymbolicFrame(),
        state: this.host.getState(),
      };
    }
    if (this.loopMode === "hybrid") {
      this.tickHybrid(targetStepSeconds);
      return {
        frame: this.host.getSymbolicFrame(),
        state: this.host.getState(),
      };
    }

    const intervalMs = (targetStepSeconds * 1000) / this.gameTimeScale;

    if (this.lastSteppedAtMs === 0) {
      this.lastSteppedAtMs = nowMs - intervalMs;
    }

    const elapsedWallMs = nowMs - this.lastSteppedAtMs;
    if (elapsedWallMs < intervalMs) {
      return {
        frame: this.host.getSymbolicFrame(),
        state: this.host.getState(),
      };
    }

    const wantedSteps = Math.max(1, Math.floor(elapsedWallMs / intervalMs));
    const steps = Math.min(this.maxCatchupSteps, wantedSteps);
    for (let index = 0; index < steps; index += 1) {
      this.tickRealTime(targetStepSeconds);
    }
    this.lastSteppedAtMs = nowMs;

    return {
      frame: this.host.getSymbolicFrame(),
      state: this.host.getState(),
    };
  }

  private tickTurnBased(dtSeconds: number): void {
    const state = this.host.getState();
    const currentTurn =
      state.scene && typeof state.scene.turn === "number" ? state.scene.turn : 0;
    const roleId = this.roleOrder[currentTurn % this.roleOrder.length];
    const queue = this.pendingByRole.get(roleId);
    if (!queue || queue.length === 0) {
      return;
    }

    const turnAtStart = currentTurn;
    while (queue.length > 0) {
      const command = queue.shift();
      if (!command) {
        break;
      }
      this.applyCommand(roleId, command, dtSeconds);
      const afterTurn = this.readCurrentTurn();
      if (afterTurn !== turnAtStart) {
        break;
      }
    }

    if (queue.length === 0) {
      this.host.step({ dtSeconds });
    }
  }

  private tickHybrid(dtSeconds: number): void {
    const turnAtStart = this.readCurrentTurn();
    while (true) {
      let consumedAny = false;
      for (const roleId of this.roleOrder) {
        const queue = this.pendingByRole.get(roleId);
        if (!queue || queue.length === 0) {
          continue;
        }
        const command = queue.shift();
        if (!command) {
          continue;
        }
        consumedAny = true;
        this.applyCommand(roleId, command, dtSeconds);
        const afterTurn = this.readCurrentTurn();
        if (afterTurn !== turnAtStart) {
          return;
        }
      }
      if (!consumedAny) {
        this.host.step({ dtSeconds });
        return;
      }
    }
  }

  private tickRealTime(dtSeconds: number): void {
    let consumedAny = false;
    for (const roleId of this.roleOrder) {
      const queue = this.pendingByRole.get(roleId);
      if (!queue || queue.length === 0) {
        continue;
      }
      const command = queue.pop();
      queue.length = 0;
      if (!command) {
        continue;
      }
      consumedAny = true;
      this.applyCommand(roleId, command, dtSeconds);
    }

    if (!consumedAny) {
      this.host.step({ dtSeconds });
    }
  }

  private readCurrentTurn(): number {
    const state = this.host.getState();
    if (state.scene && typeof state.scene.turn === "number") {
      return state.scene.turn;
    }
    return 0;
  }

  private applyCommand(roleId: string, command: SessionCommand, dtSeconds: number): void {
    if (command.kind === "tool") {
      this.host.step({
        dtSeconds,
        roleId,
        toolCalls: [
          {
            name: command.name,
            payload:
              command.payload && typeof command.payload === "object"
                ? command.payload
                : {},
            role_id: roleId,
          },
        ],
      });
      return;
    }

    if (command.kind === "button") {
      this.host.step({
        dtSeconds,
        roleId,
        uiButtons: [command.name],
      });
      return;
    }

    if (command.kind === "input") {
      this.host.step({
        dtSeconds,
        roleId,
        keyboard: command.keyboard,
        mouse: command.mouse,
        uiButtons: command.uiButtons,
      });
      return;
    }

    this.host.step({ dtSeconds });
  }
}
