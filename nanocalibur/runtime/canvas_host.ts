import {
  NanoCaliburInterpreter,
} from "./interpreter";
import { AssetStore } from "./canvas/assets";
import {
  InterfaceButtonEvent,
  InterfaceOverlay,
  InterfaceOverlayRect,
} from "./canvas/interface_overlay";
import { CanvasRenderer } from "./canvas/renderer";
import { SymbolicRenderer } from "./symbolic_renderer";
import {
  CanvasHostOptions,
  DEFAULT_FIXED_STEP_MS,
  DEFAULT_MAX_SUB_STEPS,
  SceneInterfaceBinding,
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
  private readonly interfaceOverlays = new Map<
    string,
    {
      overlay: InterfaceOverlay;
      html: string;
      rectKey: string;
    }
  >();

  private readonly keysDown = new Set<string>();
  private previousKeysDown = new Set<string>();
  private readonly mouseDown = new Set<string>();
  private previousMouseDown = new Set<string>();
  private mousePosition = { x: 0, y: 0 };
  private mouseWorldPosition = { x: 0, y: 0 };
  private mouseViewId = "";

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
    this.updateMousePosition(event);
    this.mouseDown.add(mapMouseButton(event.button));
  };

  private readonly handleMouseUp = (event: MouseEvent): void => {
    this.updateMousePosition(event);
    this.mouseDown.delete(mapMouseButton(event.button));
  };

  private readonly handleMouseMove = (event: MouseEvent): void => {
    this.updateMousePosition(event);
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
    this.renderer.render(this.core.getState(), this.core.getMap());
    this.syncInterfaceOverlays();
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
    const uiButtons = this.consumeOverlayButtonPhases();

    this.previousKeysDown = new Set(this.keysDown);
    this.previousMouseDown = new Set(this.mouseDown);

    this.core.step(dtSeconds, {
      keyboard,
      mouse,
      uiButtons,
      mousePosition: this.mousePosition,
      mouseWorldPosition: this.mouseWorldPosition,
      mouseViewId: this.mouseViewId,
    });
    this.syncInterfaceOverlays();
    const globals = this.buildInterfaceGlobals();
    for (const overlayEntry of this.interfaceOverlays.values()) {
      overlayEntry.overlay.updateGlobals(globals);
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
    window.addEventListener("mousemove", this.handleMouseMove);
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
    window.removeEventListener("mousemove", this.handleMouseMove);
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
    this.mouseViewId = "";
  }

  private updateMousePosition(event: MouseEvent): void {
    const rect = this.canvas.getBoundingClientRect();
    const screenX = event.clientX - rect.left;
    const screenY = event.clientY - rect.top;
    const projection = this.renderer.projectScreenToWorld(
      this.core.getState(),
      this.core.getMap(),
      screenX,
      screenY,
    );
    if (projection) {
      this.mousePosition = {
        x: projection.localX,
        y: projection.localY,
      };
      this.mouseWorldPosition = {
        x: projection.worldX,
        y: projection.worldY,
      };
      this.mouseViewId = projection.viewId;
      return;
    }
    this.mousePosition = {
      x: screenX,
      y: screenY,
    };
    this.mouseWorldPosition = {
      x: screenX,
      y: screenY,
    };
    this.mouseViewId = "";
  }

  private consumeOverlayButtonPhases(): {
    begin: InterfaceButtonEvent[];
    on: InterfaceButtonEvent[];
    end: InterfaceButtonEvent[];
  } {
    const begin: InterfaceButtonEvent[] = [];
    const on: InterfaceButtonEvent[] = [];
    const end: InterfaceButtonEvent[] = [];
    for (const entry of this.interfaceOverlays.values()) {
      const phases = entry.overlay.consumeButtonPhases();
      begin.push(...phases.begin);
      on.push(...phases.on);
      end.push(...phases.end);
    }
    return { begin, on, end };
  }

  private resolveActiveInterfaceBindings(): Array<{
    key: string;
    html: string;
    viewId: string | null;
    rect: InterfaceOverlayRect | null;
  }> {
    const state = this.core.getState();
    const scene = state.scene as Record<string, any> | null;
    const fallbackHtml =
      scene && typeof scene.interfaceHtml === "string" ? scene.interfaceHtml : "";
    const rawBindings = Array.isArray(scene?.interfaces)
      ? (scene?.interfaces as SceneInterfaceBinding[])
      : [];
    const bindings = rawBindings.length > 0
      ? rawBindings
      : fallbackHtml.trim().length > 0
        ? [{ html: fallbackHtml, role_id: null, view_id: null }]
        : [];

    const selfRoleId =
      state.self && typeof state.self === "object" && typeof (state.self as { id?: unknown }).id === "string"
        ? (state.self as { id: string }).id
        : null;

    const viewRects = new Map<string, InterfaceOverlayRect>();
    for (const view of this.renderer.getRenderViews(state, this.core.getMap())) {
      viewRects.set(view.id, {
        x: view.x,
        y: view.y,
        width: view.width,
        height: view.height,
      });
    }

    const desired = new Map<string, {
      key: string;
      html: string;
      viewId: string | null;
      rect: InterfaceOverlayRect | null;
    }>();
    for (const binding of bindings) {
      const html = typeof binding.html === "string" ? binding.html : "";
      if (html.trim().length === 0) {
        continue;
      }
      const roleId =
        typeof binding.role_id === "string" && binding.role_id ? binding.role_id : null;
      const viewId =
        typeof binding.view_id === "string" && binding.view_id ? binding.view_id : null;
      if (roleId && selfRoleId && roleId !== selfRoleId) {
        continue;
      }
      const rect = viewId ? (viewRects.get(viewId) || null) : null;
      if (viewId && !rect) {
        continue;
      }
      const key = `${roleId || ""}::${viewId || ""}`;
      desired.set(key, {
        key,
        html,
        viewId,
        rect,
      });
    }
    return Array.from(desired.values());
  }

  private syncInterfaceOverlays(): void {
    const desired = this.resolveActiveInterfaceBindings();
    const desiredKeys = new Set(desired.map((item) => item.key));

    for (const [key, existing] of this.interfaceOverlays.entries()) {
      if (!desiredKeys.has(key)) {
        existing.overlay.destroy();
        this.interfaceOverlays.delete(key);
      }
    }

    for (const target of desired) {
      const existing = this.interfaceOverlays.get(target.key);
      const rectKey = target.rect
        ? `${target.rect.x},${target.rect.y},${target.rect.width},${target.rect.height}`
        : "full";
      if (!existing) {
        const overlay = new InterfaceOverlay(
          this.canvas,
          target.html,
          target.viewId,
          target.rect,
        );
        this.interfaceOverlays.set(target.key, {
          overlay,
          html: target.html,
          rectKey,
        });
        continue;
      }
      if (existing.html !== target.html) {
        existing.overlay.setHtml(target.html);
        existing.html = target.html;
      }
      if (existing.rectKey !== rectKey) {
        existing.overlay.setRect(target.rect);
        existing.rectKey = rectKey;
      }
    }

    const globals = this.buildInterfaceGlobals();
    for (const entry of this.interfaceOverlays.values()) {
      entry.overlay.updateGlobals(globals);
    }
  }
}
