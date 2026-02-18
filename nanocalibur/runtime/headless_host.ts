import { InterpreterState, NanoCaliburInterpreter } from "./interpreter";
import { CanvasHostOptions, SymbolicFrame } from "./canvas/types";
import { RuntimeCore, RuntimeStepInput } from "./runtime_core";
import { SymbolicRenderer } from "./symbolic_renderer";

export interface HeadlessStepInput extends RuntimeStepInput {
  dtSeconds?: number;
}

export class HeadlessHost {
  private readonly core: RuntimeCore;
  private readonly symbolicRenderer: SymbolicRenderer;
  private readonly defaultStepSeconds: number;

  constructor(
    interpreter: NanoCaliburInterpreter,
    options: CanvasHostOptions = {},
  ) {
    this.core = new RuntimeCore(interpreter, options);
    this.symbolicRenderer = new SymbolicRenderer(this.core.getOptions());
    this.defaultStepSeconds = 1 / 60;
  }

  getInterpreter(): NanoCaliburInterpreter {
    return this.core.getInterpreter();
  }

  getState(): InterpreterState {
    return this.core.getState();
  }

  getSymbolicFrame(): SymbolicFrame {
    return this.symbolicRenderer.render(this.core.getState(), this.core.getMap());
  }

  listTools(): Array<{ name: string; tool_docstring: string; action: string }> {
    return this.core.getInterpreter().getTools();
  }

  step(input: HeadlessStepInput = {}): SymbolicFrame {
    const dtSeconds =
      typeof input.dtSeconds === "number" && Number.isFinite(input.dtSeconds)
        ? input.dtSeconds
        : this.defaultStepSeconds;

    this.core.step(dtSeconds, {
      keyboard: input.keyboard,
      mouse: input.mouse,
      uiButtons: input.uiButtons,
      toolCalls: input.toolCalls,
    });

    return this.getSymbolicFrame();
  }

  callTool(name: string, payload: Record<string, any> = {}): SymbolicFrame {
    return this.step({
      toolCalls: [
        {
          name,
          payload,
        },
      ],
    });
  }
}

export interface MCPRequest {
  id?: string | number | null;
  method: string;
  params?: Record<string, any>;
}

export interface MCPResponse {
  id?: string | number | null;
  result?: Record<string, any>;
  error?: {
    code: number;
    message: string;
  };
}

/**
 * Minimal MCP-style request handler over a HeadlessHost.
 *
 * Supported methods:
 * - tools/list
 * - tools/call (params: { name: string, arguments?: object })
 * - nanocalibur/render
 * - nanocalibur/state
 */
export class NanoCaliburMCPServer {
  private readonly host: HeadlessHost;

  constructor(host: HeadlessHost) {
    this.host = host;
  }

  handle(request: MCPRequest): MCPResponse {
    if (!request || typeof request.method !== "string") {
      return {
        id: request?.id,
        error: {
          code: -32600,
          message: "Invalid request.",
        },
      };
    }

    if (request.method === "tools/list") {
      return {
        id: request.id,
        result: {
          tools: this.host.listTools().map((tool) => ({
            name: tool.name,
            description: tool.tool_docstring,
          })),
        },
      };
    }

    if (request.method === "tools/call") {
      const name = typeof request.params?.name === "string" ? request.params.name : "";
      if (!name) {
        return {
          id: request.id,
          error: {
            code: -32602,
            message: "tools/call requires params.name.",
          },
        };
      }
      const args =
        request.params?.arguments && typeof request.params.arguments === "object"
          ? (request.params.arguments as Record<string, any>)
          : {};
      const frame = this.host.callTool(name, args);
      return {
        id: request.id,
        result: {
          frame,
          state: this.host.getState(),
        },
      };
    }

    if (request.method === "nanocalibur/render") {
      return {
        id: request.id,
        result: {
          frame: this.host.getSymbolicFrame(),
        },
      };
    }

    if (request.method === "nanocalibur/state") {
      return {
        id: request.id,
        result: {
          state: this.host.getState(),
        },
      };
    }

    return {
      id: request.id,
      error: {
        code: -32601,
        message: `Method not found: ${request.method}`,
      },
    };
  }
}
