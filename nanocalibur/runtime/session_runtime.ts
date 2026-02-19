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
}

export interface SessionTickResult {
  frame: SymbolicFrame;
  state: InterpreterState;
}

export class SessionRuntime {
  private readonly host: HeadlessHost;
  private readonly loopMode: SessionLoopMode;
  private readonly roleOrder: string[];
  private readonly pendingByRole: Map<string, SessionCommand[]>;
  private readonly defaultStepSeconds: number;

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
  }

  getLoopMode(): SessionLoopMode {
    return this.loopMode;
  }

  getRoleOrder(): string[] {
    return [...this.roleOrder];
  }

  getHost(): HeadlessHost {
    return this.host;
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
    if (this.loopMode === "turn_based") {
      this.tickTurnBased(dtSeconds);
    } else if (this.loopMode === "hybrid") {
      this.tickHybrid(dtSeconds);
    } else {
      this.tickRealTime(dtSeconds);
    }

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
      this.applyCommand(command, dtSeconds);
      const afterTurn = this.readCurrentTurn();
      if (afterTurn !== turnAtStart) {
        break;
      }
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
        this.applyCommand(command, dtSeconds);
        const afterTurn = this.readCurrentTurn();
        if (afterTurn !== turnAtStart) {
          return;
        }
      }
      if (!consumedAny) {
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
      this.applyCommand(command, dtSeconds);
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

  private applyCommand(command: SessionCommand, dtSeconds: number): void {
    if (command.kind === "tool") {
      this.host.step({
        dtSeconds,
        toolCalls: [
          {
            name: command.name,
            payload:
              command.payload && typeof command.payload === "object"
                ? command.payload
                : {},
          },
        ],
      });
      return;
    }

    if (command.kind === "button") {
      this.host.step({
        dtSeconds,
        uiButtons: [command.name],
      });
      return;
    }

    if (command.kind === "input") {
      this.host.step({
        dtSeconds,
        keyboard: command.keyboard,
        mouse: command.mouse,
        uiButtons: command.uiButtons,
      });
      return;
    }

    this.host.step({ dtSeconds });
  }
}
