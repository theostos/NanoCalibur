import { InterpreterState } from "../interpreter";
import { AssetStore } from "./assets";
import { AnimationSystem } from "./animation";
import {
  ActorState,
  CameraState,
  CanvasHostOptions,
  DEFAULT_TICKS_PER_FRAME,
  DEFAULT_HEIGHT,
  DEFAULT_TYPE_COLORS,
  DEFAULT_WIDTH,
  MapSpec,
  SpriteAnimationConfig,
  SpriteFrameInfo,
  ViewState,
} from "./types";
import { actorCenterX, actorCenterY, actorHeight, actorWidth, asNumber, clamp } from "./utils";

interface ViewRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface ResolvedViewCamera {
  x: number;
  y: number;
  worldWidth: number;
  worldHeight: number;
}

interface ResolvedRenderView {
  id: string;
  rect: ViewRect;
  camera: ResolvedViewCamera;
  z: number;
  interactive: boolean;
  symbolic: boolean;
}

interface WorldBounds {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface ScreenProjection {
  viewId: string;
  localX: number;
  localY: number;
  worldX: number;
  worldY: number;
}

export class CanvasRenderer {
  private readonly canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private readonly outputCtx: CanvasRenderingContext2D;
  private readonly offscreenCanvas: HTMLCanvasElement | null;
  private readonly offscreenCtx: CanvasRenderingContext2D | null;
  private readonly renderScale: number;
  private readonly options: CanvasHostOptions;
  private readonly assets: AssetStore;
  private readonly animation: AnimationSystem;
  private frameCounter = 0;

  constructor(
    canvas: HTMLCanvasElement,
    options: CanvasHostOptions,
    assets: AssetStore,
    animation: AnimationSystem,
  ) {
    this.canvas = canvas;
    this.options = options;
    this.assets = assets;
    this.animation = animation;

    const ctx = this.canvas.getContext("2d");
    if (!ctx) {
      throw new Error("Canvas 2D context is not available.");
    }
    this.ctx = ctx;
    this.outputCtx = ctx;

    this.canvas.width = Math.floor(asNumber(options.width, DEFAULT_WIDTH));
    this.canvas.height = Math.floor(asNumber(options.height, DEFAULT_HEIGHT));
    if (this.canvas.tabIndex < 0) {
      this.canvas.tabIndex = 0;
    }

    let normalizedRenderScale = asNumber(options.renderScale, 1);
    if (!Number.isFinite(normalizedRenderScale)) {
      normalizedRenderScale = 1;
    }
    if (normalizedRenderScale < 0.25) {
      normalizedRenderScale = 0.25;
    }
    if (normalizedRenderScale > 1) {
      normalizedRenderScale = 1;
    }
    this.renderScale = normalizedRenderScale;

    let offscreenCanvas: HTMLCanvasElement | null = null;
    let offscreenCtx: CanvasRenderingContext2D | null = null;
    if (this.renderScale < 0.999) {
      offscreenCanvas = document.createElement("canvas");
      offscreenCanvas.width = Math.max(1, Math.floor(this.canvas.width * this.renderScale));
      offscreenCanvas.height = Math.max(1, Math.floor(this.canvas.height * this.renderScale));
      const maybeCtx = offscreenCanvas.getContext("2d");
      if (maybeCtx) {
        offscreenCtx = maybeCtx;
      } else {
        offscreenCanvas = null;
      }
    }
    this.offscreenCanvas = offscreenCanvas;
    this.offscreenCtx = offscreenCtx;

    const pixelated = options.pixelated !== false;
    if (pixelated) {
      this.ctx.imageSmoothingEnabled = false;
      this.outputCtx.imageSmoothingEnabled = false;
      if (this.offscreenCtx) {
        this.offscreenCtx.imageSmoothingEnabled = false;
      }
      this.canvas.style.imageRendering = "pixelated";
    }
  }

  render(state: InterpreterState, mapSpec: MapSpec | null): void {
    this.frameCounter += 1;
    if (this.offscreenCanvas && this.offscreenCtx) {
      const targetScaleX = this.offscreenCanvas.width / this.canvas.width;
      const targetScaleY = this.offscreenCanvas.height / this.canvas.height;
      this.ctx = this.offscreenCtx;
      this.ctx.setTransform(1, 0, 0, 1, 0, 0);
      this.ctx.clearRect(0, 0, this.offscreenCanvas.width, this.offscreenCanvas.height);
      this.ctx.save();
      this.ctx.scale(targetScaleX, targetScaleY);
      this.renderScene(state, mapSpec);
      this.ctx.restore();

      this.outputCtx.setTransform(1, 0, 0, 1, 0, 0);
      this.outputCtx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      if (this.options.pixelated !== false) {
        this.outputCtx.imageSmoothingEnabled = false;
      }
      this.outputCtx.drawImage(
        this.offscreenCanvas,
        0,
        0,
        this.canvas.width,
        this.canvas.height,
      );
      this.ctx = this.outputCtx;
      return;
    }
    this.ctx = this.outputCtx;
    this.renderScene(state, mapSpec);
  }

  private renderScene(state: InterpreterState, mapSpec: MapSpec | null): void {
    const actors = state.actors as ActorState[];
    const sortedActors = [...actors].sort(
      (a, b) => asNumber(a.z, 0) - asNumber(b.z, 0),
    );
    const views = this.resolveRenderViews(state, mapSpec);

    this.ctx.fillStyle = this.options.backgroundColor || "#10151f";
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    for (const view of views) {
      // Overlay-only views are used for interface placement and should not trigger world draws.
      if (!view.interactive && !view.symbolic) {
        continue;
      }
      const viewBounds = this.resolveViewWorldBounds(view);
      this.ctx.save();
      this.ctx.beginPath();
      this.ctx.rect(view.rect.x, view.rect.y, view.rect.width, view.rect.height);
      this.ctx.clip();

      this.ctx.fillStyle = this.options.backgroundColor || "#10151f";
      this.ctx.fillRect(view.rect.x, view.rect.y, view.rect.width, view.rect.height);

      this.drawTiles(mapSpec, view, viewBounds);

      for (const actor of sortedActors) {
        if (!this.actorVisibleInView(actor, view.id)) {
          continue;
        }
        if (!this.actorIntersectsViewBounds(actor, viewBounds)) {
          continue;
        }
        this.drawActor(actor, view);
      }

      if (this.options.showDebugColliders) {
        this.drawDebugColliders(actors, view, viewBounds);
      }
      this.ctx.restore();
    }
  }

  getRenderViews(state: InterpreterState, mapSpec: MapSpec | null): Array<{
    id: string;
    x: number;
    y: number;
    width: number;
    height: number;
    world_width: number;
    world_height: number;
    camera_x: number;
    camera_y: number;
    z: number;
    interactive: boolean;
    symbolic: boolean;
  }> {
    return this.resolveRenderViews(state, mapSpec).map((view) => ({
      id: view.id,
      x: view.rect.x,
      y: view.rect.y,
      width: view.rect.width,
      height: view.rect.height,
      world_width: view.camera.worldWidth,
      world_height: view.camera.worldHeight,
      camera_x: view.camera.x,
      camera_y: view.camera.y,
      z: view.z,
      interactive: view.interactive,
      symbolic: view.symbolic,
    }));
  }

  projectScreenToWorld(
    state: InterpreterState,
    mapSpec: MapSpec | null,
    screenX: number,
    screenY: number,
  ): ScreenProjection | null {
    const views = this.resolveRenderViews(state, mapSpec)
      .filter((view) => view.interactive)
      .sort((a, b) => (b.z - a.z));
    for (const view of views) {
      if (
        screenX < view.rect.x
        || screenY < view.rect.y
        || screenX > view.rect.x + view.rect.width
        || screenY > view.rect.y + view.rect.height
      ) {
        continue;
      }
      const localX = screenX - view.rect.x;
      const localY = screenY - view.rect.y;
      const worldX = this.screenToWorldX(screenX, view);
      const worldY = this.screenToWorldY(screenY, view);
      return {
        viewId: view.id,
        localX,
        localY,
        worldX,
        worldY,
      };
    }
    return null;
  }

  private resolveRenderViews(
    state: InterpreterState,
    mapSpec: MapSpec | null,
  ): ResolvedRenderView[] {
    const scene =
      state && state.scene && typeof state.scene === "object"
        ? (state.scene as Record<string, any>)
        : null;
    const sceneViewsRaw = Array.isArray(scene?.views) ? (scene?.views as ViewState[]) : [];
    const byName =
      state && state.cameras && typeof state.cameras === "object"
        ? (state.cameras as Record<string, any>)
        : {};
    const fallbackCamera = this.resolveDefaultCameraState(state);
    const resolved: ResolvedRenderView[] = [];
    for (const rawView of sceneViewsRaw) {
      if (!rawView || typeof rawView.id !== "string" || !rawView.id) {
        continue;
      }
      const rect = this.resolveViewRect(rawView);
      const cameraState = this.resolveCameraForView(rawView, byName, fallbackCamera);
      if (!cameraState) {
        continue;
      }
      const camera = this.resolveCamera(cameraState, mapSpec, rect);
      resolved.push({
        id: rawView.id,
        rect,
        camera,
        z: Math.floor(asNumber(rawView.z, 0)),
        interactive: rawView.interactive !== false,
        symbolic: rawView.symbolic !== false,
      });
    }
    if (resolved.length === 0) {
      const camera = this.resolveCamera(fallbackCamera, mapSpec, {
        x: 0,
        y: 0,
        width: this.canvas.width,
        height: this.canvas.height,
      });
      return [
        {
          id: "__default__",
          rect: {
            x: 0,
            y: 0,
            width: this.canvas.width,
            height: this.canvas.height,
          },
          camera,
          z: 0,
          interactive: true,
          symbolic: true,
        },
      ];
    }
    resolved.sort((a, b) => (a.z - b.z));
    return resolved;
  }

  private resolveDefaultCameraState(state: InterpreterState): CameraState | null {
    const direct = state.camera as CameraState | null;
    if (direct && typeof direct === "object") {
      return direct;
    }
    const byName =
      state && state.cameras && typeof state.cameras === "object"
        ? (state.cameras as Record<string, any>)
        : null;
    if (!byName) {
      return null;
    }
    for (const value of Object.values(byName)) {
      if (value && typeof value === "object") {
        return value as CameraState;
      }
    }
    return null;
  }

  private resolveCameraForView(
    view: ViewState,
    camerasByName: Record<string, any>,
    fallback: CameraState | null,
  ): CameraState | null {
    if (typeof view.camera_name === "string" && view.camera_name) {
      const selected = camerasByName[view.camera_name];
      if (selected && typeof selected === "object") {
        return selected as CameraState;
      }
    }
    return fallback;
  }

  private resolveViewRect(view: ViewState): ViewRect {
    const xRatio = this.clamp01(asNumber(view.x, 0));
    const yRatio = this.clamp01(asNumber(view.y, 0));
    const widthRatio = this.clamp01Positive(asNumber(view.width, 1));
    const heightRatio = this.clamp01Positive(asNumber(view.height, 1));

    const x = clamp(Math.floor(xRatio * this.canvas.width), 0, Math.max(0, this.canvas.width - 1));
    const y = clamp(Math.floor(yRatio * this.canvas.height), 0, Math.max(0, this.canvas.height - 1));
    const width = Math.max(1, Math.floor(widthRatio * this.canvas.width));
    const height = Math.max(1, Math.floor(heightRatio * this.canvas.height));
    return {
      x,
      y,
      width: Math.max(1, Math.min(width, this.canvas.width - x)),
      height: Math.max(1, Math.min(height, this.canvas.height - y)),
    };
  }

  private resolveCamera(
    cameraState: CameraState | null,
    mapSpec: MapSpec | null,
    rect: ViewRect,
  ): ResolvedViewCamera {
    const fallbackCenterX = rect.width / 2;
    const fallbackCenterY = rect.height / 2;
    const tileSize = mapSpec ? Math.max(1, asNumber(mapSpec.tile_size, 1)) : 1;
    const worldWidth = this.resolveCameraWorldSpan(
      cameraState?.width,
      tileSize,
      rect.width,
    );
    const worldHeight = this.resolveCameraWorldSpan(
      cameraState?.height,
      tileSize,
      rect.height,
    );
    const resolvedX = asNumber(cameraState?.x, fallbackCenterX);
    const resolvedY = asNumber(cameraState?.y, fallbackCenterY);

    if (!mapSpec) {
      return {
        x: resolvedX,
        y: resolvedY,
        worldWidth,
        worldHeight,
      };
    }

    const worldTotalWidth = mapSpec.width * mapSpec.tile_size;
    const worldTotalHeight = mapSpec.height * mapSpec.tile_size;
    const halfViewW = worldWidth / 2;
    const halfViewH = worldHeight / 2;

    const minX = halfViewW;
    const maxX = Math.max(halfViewW, worldTotalWidth - halfViewW);
    const minY = halfViewH;
    const maxY = Math.max(halfViewH, worldTotalHeight - halfViewH);

    return {
      x: clamp(resolvedX, minX, maxX),
      y: clamp(resolvedY, minY, maxY),
      worldWidth,
      worldHeight,
    };
  }

  private resolveCameraWorldSpan(
    maybeTiles: number | null | undefined,
    tileSize: number,
    fallbackPixels: number,
  ): number {
    if (
      typeof maybeTiles === "number"
      && Number.isFinite(maybeTiles)
      && maybeTiles > 0
    ) {
      return maybeTiles * tileSize;
    }
    return Math.max(1, fallbackPixels);
  }

  private drawTiles(
    mapSpec: MapSpec | null,
    view: ResolvedRenderView,
    viewBounds: WorldBounds,
  ): void {
    if (!mapSpec) {
      return;
    }

    const tileSize = mapSpec.tile_size;
    const defaultTileColor = this.options.tileColor || "#2f3648";

    if (!Array.isArray(mapSpec.tile_grid)) {
      return;
    }

    const gridHeight = mapSpec.tile_grid.length;
    if (gridHeight <= 0) {
      return;
    }
    const minTileY = clamp(
      Math.floor(viewBounds.top / tileSize),
      0,
      Math.max(0, gridHeight - 1),
    );
    const maxTileY = clamp(
      Math.ceil(viewBounds.bottom / tileSize) - 1,
      minTileY,
      Math.max(minTileY, gridHeight - 1),
    );

    for (let tileY = minTileY; tileY <= maxTileY; tileY += 1) {
      const row = mapSpec.tile_grid[tileY];
      if (!Array.isArray(row)) {
        continue;
      }
      if (row.length <= 0) {
        continue;
      }
      const minTileX = clamp(
        Math.floor(viewBounds.left / tileSize),
        0,
        Math.max(0, row.length - 1),
      );
      const maxTileX = clamp(
        Math.ceil(viewBounds.right / tileSize) - 1,
        minTileX,
        Math.max(minTileX, row.length - 1),
      );
      for (let tileX = minTileX; tileX <= maxTileX; tileX += 1) {
        const tileId = row[tileX];
        if (typeof tileId !== "number" || !Number.isFinite(tileId)) {
          continue;
        }
        if (Math.trunc(tileId) === 0) {
          continue;
        }

        const leftWorld = tileX * tileSize;
        const topWorld = tileY * tileSize;
        const rightWorld = leftWorld + tileSize;
        const bottomWorld = topWorld + tileSize;
        const screenX = this.worldToScreenX(leftWorld, view);
        const screenY = this.worldToScreenY(topWorld, view);
        const screenW = this.worldToScreenX(rightWorld, view) - screenX;
        const screenH = this.worldToScreenY(bottomWorld, view) - screenY;
        const tileDef = mapSpec.tile_defs?.[String(tileId)];

        const color = tileDef ? this.resolveTileColor(tileDef.color) : null;
        if (color) {
          this.ctx.fillStyle = color;
          this.ctx.fillRect(screenX, screenY, screenW, screenH);
          continue;
        }

        if (
          tileDef
          && typeof tileDef.sprite === "string"
          && this.drawTileSprite(tileDef.sprite, screenX, screenY, screenW, screenH)
        ) {
          continue;
        }

        this.ctx.fillStyle = defaultTileColor;
        this.ctx.fillRect(screenX, screenY, screenW, screenH);
      }
    }
  }

  private resolveTileColor(
    color:
      | {
          r: number;
          g: number;
          b: number;
          a?: number;
          symbol?: string | null;
          description?: string | null;
        }
      | null
      | undefined,
  ): string | null {
    if (!color) {
      return null;
    }
    const r = clamp(Math.floor(asNumber(color.r, 0)), 0, 255);
    const g = clamp(Math.floor(asNumber(color.g, 0)), 0, 255);
    const b = clamp(Math.floor(asNumber(color.b, 0)), 0, 255);
    const a = clamp(asNumber(color.a, 1), 0, 1);
    return `rgba(${r}, ${g}, ${b}, ${a})`;
  }

  private drawTileSprite(
    spriteName: string,
    screenX: number,
    screenY: number,
    screenW: number,
    screenH: number,
  ): boolean {
    const sprite = this.options.spritesByName?.[spriteName];
    if (!sprite) {
      return false;
    }
    if (!sprite.image) {
      const fallbackColor = this.resolveSpriteColor(sprite);
      if (!fallbackColor) {
        return false;
      }
      this.ctx.fillStyle = fallbackColor;
      this.ctx.fillRect(screenX, screenY, screenW, screenH);
      return true;
    }
    const image = this.assets.getImage(sprite.image);
    if (!image) {
      const fallbackColor = this.resolveSpriteColor(sprite);
      if (!fallbackColor) {
        return false;
      }
      this.ctx.fillStyle = fallbackColor;
      this.ctx.fillRect(screenX, screenY, screenW, screenH);
      return true;
    }

    const clipName =
      sprite.defaultClip && sprite.clips[sprite.defaultClip]
        ? sprite.defaultClip
        : Object.keys(sprite.clips)[0];
    const clip = clipName ? sprite.clips[clipName] : null;
    if (!clip || !Array.isArray(clip.frames) || clip.frames.length === 0) {
      const fallbackColor = this.resolveSpriteColor(sprite);
      if (!fallbackColor) {
        return false;
      }
      this.ctx.fillStyle = fallbackColor;
      this.ctx.fillRect(screenX, screenY, screenW, screenH);
      return true;
    }

    const ticksPerFrame = Math.max(
      1,
      Math.floor(asNumber(clip.ticksPerFrame, DEFAULT_TICKS_PER_FRAME)),
    );
    const elapsedFrames = Math.floor(this.frameCounter / ticksPerFrame);
    const frameCursor =
      clip.loop === false
        ? clamp(elapsedFrames, 0, clip.frames.length - 1)
        : elapsedFrames % clip.frames.length;
    const frameIndex = Math.max(0, Math.floor(clip.frames[frameCursor]));

    const frameWidth = Math.max(1, Math.floor(asNumber(sprite.frameWidth, 16)));
    const frameHeight = Math.max(1, Math.floor(asNumber(sprite.frameHeight, 16)));
    const row = Math.max(0, Math.floor(asNumber(sprite.row, 0)));
    const columns = Math.max(1, Math.floor(image.width / frameWidth));
    const sourceColumn = frameIndex % columns;
    const sourceRow = row + Math.floor(frameIndex / columns);
    const sourceX = sourceColumn * frameWidth;
    const sourceY = sourceRow * frameHeight;
    if (
      sourceX < 0
      || sourceY < 0
      || sourceX + frameWidth > image.width
      || sourceY + frameHeight > image.height
    ) {
      return false;
    }

    this.ctx.drawImage(
      image,
      sourceX,
      sourceY,
      frameWidth,
      frameHeight,
      screenX,
      screenY,
      screenW,
      screenH,
    );
    return true;
  }

  private drawActor(actor: ActorState, view: ResolvedRenderView): void {
    if (actor.active === false) {
      return;
    }

    const spriteConfig = this.resolveSpriteConfig(actor);
    const frameInfo = this.animation.getFrameInfo(actor);
    if (frameInfo && this.drawSprite(actor, frameInfo, view)) {
      return;
    }

    const w = actorWidth(actor);
    const h = actorHeight(actor);
    const leftWorld = actorCenterX(actor) - w / 2;
    const topWorld = actorCenterY(actor) - h / 2;
    const rightWorld = leftWorld + w;
    const bottomWorld = topWorld + h;
    const x = this.worldToScreenX(leftWorld, view);
    const y = this.worldToScreenY(topWorld, view);
    const drawW = this.worldToScreenX(rightWorld, view) - x;
    const drawH = this.worldToScreenY(bottomWorld, view) - y;
    this.ctx.fillStyle =
      this.resolveSpriteColor(spriteConfig) || this.resolveActorColor(actor);
    this.ctx.fillRect(x, y, drawW, drawH);
  }

  private drawSprite(
    actor: ActorState,
    frameInfo: SpriteFrameInfo | null,
    view: ResolvedRenderView,
  ): boolean {
    if (!frameInfo) {
      return false;
    }

    const { sprite, frameIndex, facing } = frameInfo;
    if (!sprite.image) {
      return false;
    }
    const image = this.assets.getImage(sprite.image);
    if (!image) {
      return false;
    }

    const frameWidth = Math.max(1, asNumber(sprite.frameWidth, 16));
    const frameHeight = Math.max(1, asNumber(sprite.frameHeight, 16));
    const row = Math.max(0, Math.floor(asNumber(sprite.row, 0)));
    const columns = Math.max(1, Math.floor(image.width / frameWidth));
    const normalizedFrame = Math.max(0, Math.floor(frameIndex));
    const sourceColumn = normalizedFrame % columns;
    const sourceRow = row + Math.floor(normalizedFrame / columns);
    const sourceX = sourceColumn * frameWidth;
    const sourceY = sourceRow * frameHeight;
    if (
      sourceX < 0
      || sourceY < 0
      || sourceX + frameWidth > image.width
      || sourceY + frameHeight > image.height
    ) {
      return false;
    }

    const useActorSize = typeof actor.w === "number" && typeof actor.h === "number";
    const drawWorldW = useActorSize
      ? Math.max(1, actorWidth(actor))
      : frameWidth * Math.max(0.1, asNumber(sprite.scale, 1));
    const drawWorldH = useActorSize
      ? Math.max(1, actorHeight(actor))
      : frameHeight * Math.max(0.1, asNumber(sprite.scale, 1));

    const offsetX = asNumber(sprite.offsetX, 0);
    const offsetY = asNumber(sprite.offsetY, 0);

    const centerWorldX = actorCenterX(actor) + offsetX;
    const centerWorldY = actorCenterY(actor) + offsetY;
    const leftWorld = centerWorldX - drawWorldW / 2;
    const topWorld = centerWorldY - drawWorldH / 2;
    const rightWorld = leftWorld + drawWorldW;
    const bottomWorld = topWorld + drawWorldH;

    const drawX = this.worldToScreenX(leftWorld, view);
    const drawY = this.worldToScreenY(topWorld, view);
    const drawW = this.worldToScreenX(rightWorld, view) - drawX;
    const drawH = this.worldToScreenY(bottomWorld, view) - drawY;
    const centerX = drawX + (drawW / 2);
    const centerY = drawY + (drawH / 2);

    if ((sprite.flipX !== false) && facing < 0) {
      this.ctx.save();
      this.ctx.translate(centerX, centerY);
      this.ctx.scale(-1, 1);
      this.ctx.drawImage(
        image,
        sourceX,
        sourceY,
        frameWidth,
        frameHeight,
        -drawW / 2,
        -drawH / 2,
        drawW,
        drawH,
      );
      this.ctx.restore();
      return true;
    }

    this.ctx.drawImage(
      image,
      sourceX,
      sourceY,
      frameWidth,
      frameHeight,
      drawX,
      drawY,
      drawW,
      drawH,
    );
    return true;
  }

  private drawDebugColliders(
    actors: ActorState[],
    view: ResolvedRenderView,
    viewBounds: WorldBounds,
  ): void {
    this.ctx.save();
    this.ctx.strokeStyle = "rgba(255, 255, 255, 0.45)";
    this.ctx.lineWidth = 1;

    for (const actor of actors) {
      if (actor.active === false) {
        continue;
      }
      if (!this.actorIntersectsViewBounds(actor, viewBounds)) {
        continue;
      }
      const w = actorWidth(actor);
      const h = actorHeight(actor);
      const leftWorld = actorCenterX(actor) - w / 2;
      const topWorld = actorCenterY(actor) - h / 2;
      const rightWorld = leftWorld + w;
      const bottomWorld = topWorld + h;
      const x = this.worldToScreenX(leftWorld, view);
      const y = this.worldToScreenY(topWorld, view);
      const drawW = this.worldToScreenX(rightWorld, view) - x;
      const drawH = this.worldToScreenY(bottomWorld, view) - y;
      this.ctx.strokeRect(x, y, drawW, drawH);
    }

    this.ctx.restore();
  }

  private resolveViewWorldBounds(view: ResolvedRenderView): WorldBounds {
    const halfW = view.camera.worldWidth / 2;
    const halfH = view.camera.worldHeight / 2;
    return {
      left: view.camera.x - halfW,
      top: view.camera.y - halfH,
      right: view.camera.x + halfW,
      bottom: view.camera.y + halfH,
    };
  }

  private actorIntersectsViewBounds(actor: ActorState, bounds: WorldBounds): boolean {
    const w = actorWidth(actor);
    const h = actorHeight(actor);
    const leftWorld = actorCenterX(actor) - (w / 2);
    const topWorld = actorCenterY(actor) - (h / 2);
    const rightWorld = leftWorld + w;
    const bottomWorld = topWorld + h;
    return !(
      rightWorld < bounds.left
      || leftWorld > bounds.right
      || bottomWorld < bounds.top
      || topWorld > bounds.bottom
    );
  }

  private actorVisibleInView(actor: ActorState, viewId: string): boolean {
    const actorRecord = actor as Record<string, unknown>;
    const actorViewId = typeof actorRecord.view_id === "string"
      ? actorRecord.view_id
      : "";
    if (actorViewId) {
      return actorViewId === viewId;
    }
    const actorViewIds = actorRecord.view_ids;
    if (Array.isArray(actorViewIds)) {
      let sawAny = false;
      for (const entry of actorViewIds) {
        if (typeof entry !== "string" || !entry) {
          continue;
        }
        sawAny = true;
        if (entry === viewId) {
          return true;
        }
      }
      if (sawAny) {
        return false;
      }
    }
    return true;
  }

  private resolveActorColor(actor: ActorState): string {
    const byUid = this.options.actorColorsByUid?.[actor.uid];
    if (byUid) {
      return byUid;
    }

    const byType = this.options.actorColorsByType?.[actor.type];
    if (byType) {
      return byType;
    }

    return DEFAULT_TYPE_COLORS[actor.type] || this.options.defaultActorColor || "#ffffff";
  }

  private resolveSpriteConfig(actor: ActorState): SpriteAnimationConfig | null {
    const byNameKey = typeof actor.sprite === "string" ? actor.sprite : null;
    if (byNameKey) {
      const byName = this.options.spritesByName?.[byNameKey];
      if (byName) {
        return byName;
      }
    }

    const byUid = this.options.spritesByUid?.[actor.uid];
    if (byUid) {
      return byUid;
    }

    const byType = this.options.spritesByType?.[actor.type];
    if (byType) {
      return byType;
    }

    return null;
  }

  private resolveSpriteColor(
    sprite:
      | {
          color?: {
            r: number;
            g: number;
            b: number;
            a?: number;
          };
        }
      | null
      | undefined,
  ): string | null {
    if (!sprite?.color) {
      return null;
    }
    const r = clamp(Math.floor(asNumber(sprite.color.r, 0)), 0, 255);
    const g = clamp(Math.floor(asNumber(sprite.color.g, 0)), 0, 255);
    const b = clamp(Math.floor(asNumber(sprite.color.b, 0)), 0, 255);
    const a = clamp(asNumber(sprite.color.a, 1), 0, 1);
    return `rgba(${r}, ${g}, ${b}, ${a})`;
  }

  private worldToScreenX(worldX: number, view: ResolvedRenderView): number {
    const leftWorld = view.camera.x - (view.camera.worldWidth / 2);
    return view.rect.x + ((worldX - leftWorld) / view.camera.worldWidth) * view.rect.width;
  }

  private worldToScreenY(worldY: number, view: ResolvedRenderView): number {
    const topWorld = view.camera.y - (view.camera.worldHeight / 2);
    return view.rect.y + ((worldY - topWorld) / view.camera.worldHeight) * view.rect.height;
  }

  private screenToWorldX(screenX: number, view: ResolvedRenderView): number {
    const leftWorld = view.camera.x - (view.camera.worldWidth / 2);
    const ratio = (screenX - view.rect.x) / view.rect.width;
    return leftWorld + (ratio * view.camera.worldWidth);
  }

  private screenToWorldY(screenY: number, view: ResolvedRenderView): number {
    const topWorld = view.camera.y - (view.camera.worldHeight / 2);
    const ratio = (screenY - view.rect.y) / view.rect.height;
    return topWorld + (ratio * view.camera.worldHeight);
  }

  private clamp01(value: number): number {
    if (!Number.isFinite(value)) {
      return 0;
    }
    if (value < 0) {
      return 0;
    }
    if (value > 1) {
      return 1;
    }
    return value;
  }

  private clamp01Positive(value: number): number {
    if (!Number.isFinite(value) || value <= 0) {
      return 1;
    }
    if (value > 1) {
      return 1;
    }
    return value;
  }
}
