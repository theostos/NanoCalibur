import {
  NanoCaliburInterpreter,
} from "./interpreter";
import { AssetStore } from "./canvas/assets";
import { InterfaceOverlay } from "./canvas/interface_overlay";
import { CanvasRenderer } from "./canvas/renderer";
import { SymbolicRenderer } from "./symbolic_renderer";
import {
  CanvasHostOptions,
  DEFAULT_FIXED_STEP_MS,
  DEFAULT_MAX_SUB_STEPS,
  SymbolicFrame,
} from "./canvas/types";
import { asNumber, clamp, diffSets, mapMouseButton } from "./canvas/utils";
import { RuntimeCore } from "./runtime_core";

export type {
  AnimationClipConfig,
  CanvasHostOptions,
  PhysicsBodyConfig,
  SpriteAnimationConfig,
  SymbolicFrame,
} from "./canvas/types";

export class CanvasHost {
  private readonly core: RuntimeCore;
  private readonly options: CanvasHostOptions;
  private readonly canvas: HTMLCanvasElement;

  private readonly assets: AssetStore;
  private readonly renderer: CanvasRenderer;
  private readonly symbolicRenderer: SymbolicRenderer;
  private interfaceOverlay: InterfaceOverlay | null = null;
  private interfaceHtml = "";

  private readonly keysDown = new Set<string>();
  private previousKeysDown = new Set<string>();
  private readonly mouseDown = new Set<string>();
  private previousMouseDown = new Set<string>();

  private readonly fixedStepMs: number;
  private readonly maxSubSteps: number;

  private running = false;
  private inputInstalled = false;
  private rafId: number | null = null;
  private accumulatorMs = 0;
  private lastFrameMs = 0;

  private readonly handleKeyDown = (event: KeyboardEvent): void => {
    this.keysDown.add(event.key);
    this.keysDown.add(event.code);
    if (event.key.length === 1) {
      this.keysDown.add(event.key.toLowerCase());
    }
    if (event.key.startsWith("Arrow") || event.key === " ") {
      event.preventDefault();
    }
  };

  private readonly handleKeyUp = (event: KeyboardEvent): void => {
    this.keysDown.delete(event.key);
    this.keysDown.delete(event.code);
    if (event.key.length === 1) {
      this.keysDown.delete(event.key.toLowerCase());
    }
  };

  private readonly handleMouseDown = (event: MouseEvent): void => {
    this.mouseDown.add(mapMouseButton(event.button));
  };

  private readonly handleMouseUp = (event: MouseEvent): void => {
    this.mouseDown.delete(mapMouseButton(event.button));
  };

  private readonly handleContextMenu = (event: MouseEvent): void => {
    event.preventDefault();
  };

  private readonly handleWindowBlur = (): void => {
    this.clearInputState();
  };

  private readonly handleVisibilityChange = (): void => {
    if (document.hidden) {
      this.clearInputState();
    }
  };

  private readonly frameLoop = (timestampMs: number): void => {
    if (!this.running) {
      return;
    }

    if (this.lastFrameMs <= 0) {
      this.lastFrameMs = timestampMs;
    }

    const elapsedMs = clamp(timestampMs - this.lastFrameMs, 0, 250);
    this.lastFrameMs = timestampMs;
    this.accumulatorMs += elapsedMs;

    let subSteps = 0;
    while (
      this.accumulatorMs >= this.fixedStepMs &&
      subSteps < this.maxSubSteps
    ) {
      this.step(this.fixedStepMs / 1000);
      this.accumulatorMs -= this.fixedStepMs;
      subSteps += 1;
    }

    if (subSteps >= this.maxSubSteps) {
      this.accumulatorMs = 0;
    }

    this.renderer.render(this.core.getState(), this.core.getMap());
    this.rafId = window.requestAnimationFrame(this.frameLoop);
  };

  constructor(
    canvas: HTMLCanvasElement,
    interpreter: NanoCaliburInterpreter,
    options: CanvasHostOptions = {},
  ) {
    this.canvas = canvas;
    this.core = new RuntimeCore(interpreter, options);
    this.options = this.core.getOptions();

    this.fixedStepMs = Math.max(
      1,
      asNumber(this.options.fixedStepMs, DEFAULT_FIXED_STEP_MS),
    );
    this.maxSubSteps = Math.max(
      1,
      Math.floor(asNumber(this.options.maxSubSteps, DEFAULT_MAX_SUB_STEPS)),
    );

    this.assets = new AssetStore(this.options);
    this.renderer = new CanvasRenderer(
      canvas,
      this.options,
      this.assets,
      this.core.getAnimationSystem(),
    );
    this.symbolicRenderer = new SymbolicRenderer(this.options);
    this.syncInterfaceOverlay();
    this.renderer.render(this.core.getState(), this.core.getMap());
  }

  getInterpreter(): NanoCaliburInterpreter {
    return this.core.getInterpreter();
  }

  isRunning(): boolean {
    return this.running;
  }

  getSymbolicFrame(): SymbolicFrame {
    return this.symbolicRenderer.render(this.core.getState(), this.core.getMap());
  }

  async start(): Promise<void> {
    if (this.running) {
      return;
    }

    await this.assets.preload();
    this.installInputListeners();

    this.running = true;
    this.accumulatorMs = 0;
    this.lastFrameMs = 0;
    this.rafId = window.requestAnimationFrame(this.frameLoop);
  }

  stop(): void {
    this.running = false;
    if (this.rafId !== null) {
      window.cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    this.uninstallInputListeners();
  }

  private step(dtSeconds: number): void {
    const keyboard = diffSets(this.keysDown, this.previousKeysDown);
    const mouse = diffSets(this.mouseDown, this.previousMouseDown);
    const uiButtons = this.interfaceOverlay
      ? this.interfaceOverlay.consumeButtonEvents()
      : [];

    this.previousKeysDown = new Set(this.keysDown);
    this.previousMouseDown = new Set(this.mouseDown);

    this.core.step(dtSeconds, { keyboard, mouse, uiButtons });
    this.syncInterfaceOverlay();
    if (this.interfaceOverlay) {
      this.interfaceOverlay.updateGlobals(this.buildInterfaceGlobals());
    }
  }

  private buildInterfaceGlobals(): Record<string, any> {
    const state = this.core.getState();
    const globals =
      state.globals && typeof state.globals === "object"
        ? { ...(state.globals as Record<string, any>) }
        : {};
    globals.role =
      state.self && typeof state.self === "object"
        ? { ...(state.self as Record<string, any>) }
        : {};
    globals.__actors_count = Array.isArray(state.actors) ? state.actors.length : 0;
    globals.__scene_elapsed =
      state.scene && typeof state.scene.elapsed === "number"
        ? state.scene.elapsed
        : 0;
    return globals;
  }

  private installInputListeners(): void {
    if (this.inputInstalled) {
      return;
    }

    window.addEventListener("keydown", this.handleKeyDown, { passive: false });
    window.addEventListener("keyup", this.handleKeyUp);
    window.addEventListener("mousedown", this.handleMouseDown);
    window.addEventListener("mouseup", this.handleMouseUp);
    window.addEventListener("contextmenu", this.handleContextMenu);
    window.addEventListener("blur", this.handleWindowBlur);
    document.addEventListener("visibilitychange", this.handleVisibilityChange);
    this.inputInstalled = true;
  }

  private uninstallInputListeners(): void {
    if (!this.inputInstalled) {
      return;
    }

    window.removeEventListener("keydown", this.handleKeyDown);
    window.removeEventListener("keyup", this.handleKeyUp);
    window.removeEventListener("mousedown", this.handleMouseDown);
    window.removeEventListener("mouseup", this.handleMouseUp);
    window.removeEventListener("contextmenu", this.handleContextMenu);
    window.removeEventListener("blur", this.handleWindowBlur);
    document.removeEventListener("visibilitychange", this.handleVisibilityChange);
    this.inputInstalled = false;
  }

  private clearInputState(): void {
    this.keysDown.clear();
    this.previousKeysDown.clear();
    this.mouseDown.clear();
    this.previousMouseDown.clear();
  }

  private syncInterfaceOverlay(): void {
    const scene = this.core.getState().scene as Record<string, any> | null;
    const nextHtml =
      scene && typeof scene.interfaceHtml === "string"
        ? scene.interfaceHtml
        : "";
    if (nextHtml === this.interfaceHtml) {
      return;
    }

    this.interfaceHtml = nextHtml;
    if (nextHtml.trim().length === 0) {
      if (this.interfaceOverlay) {
        this.interfaceOverlay.destroy();
        this.interfaceOverlay = null;
      }
      return;
    }

    if (this.interfaceOverlay) {
      this.interfaceOverlay.setHtml(nextHtml);
    } else {
      this.interfaceOverlay = new InterfaceOverlay(this.canvas, nextHtml);
    }
    this.interfaceOverlay.updateGlobals(this.buildInterfaceGlobals());
  }
}
