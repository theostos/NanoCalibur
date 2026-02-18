import { InterpreterState } from "../interpreter";
import { AssetStore } from "./assets";
import { AnimationSystem } from "./animation";
import {
  ActorState,
  CanvasHostOptions,
  CameraState,
  DEFAULT_TICKS_PER_FRAME,
  DEFAULT_HEIGHT,
  DEFAULT_TYPE_COLORS,
  DEFAULT_WIDTH,
  MapSpec,
  SpriteFrameInfo,
  WorldCamera,
} from "./types";
import { actorCenterX, actorCenterY, actorHeight, actorWidth, asNumber, clamp } from "./utils";

export class CanvasRenderer {
  private readonly canvas: HTMLCanvasElement;
  private readonly ctx: CanvasRenderingContext2D;
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

    this.canvas.width = Math.floor(asNumber(options.width, DEFAULT_WIDTH));
    this.canvas.height = Math.floor(asNumber(options.height, DEFAULT_HEIGHT));
    if (this.canvas.tabIndex < 0) {
      this.canvas.tabIndex = 0;
    }

    const pixelated = options.pixelated !== false;
    if (pixelated) {
      this.ctx.imageSmoothingEnabled = false;
      this.canvas.style.imageRendering = "pixelated";
    }
  }

  render(state: InterpreterState, mapSpec: MapSpec | null): void {
    this.frameCounter += 1;
    const camera = this.resolveCamera(state.camera as CameraState | null, mapSpec);
    const actors = state.actors as ActorState[];
    const sortedActors = [...actors].sort(
      (a, b) => asNumber(a.z, 0) - asNumber(b.z, 0),
    );

    this.ctx.fillStyle = this.options.backgroundColor || "#10151f";
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    this.drawTiles(mapSpec, camera);

    for (const actor of sortedActors) {
      this.drawActor(actor, camera);
    }

    if (this.options.showDebugColliders) {
      this.drawDebugColliders(actors, camera);
    }
    if (this.options.showHud !== false) {
      this.drawHud(state);
    }
  }

  private resolveCamera(
    cameraState: CameraState | null,
    mapSpec: MapSpec | null,
  ): WorldCamera {
    const fallback: WorldCamera = {
      x: this.canvas.width / 2,
      y: this.canvas.height / 2,
    };

    if (!cameraState) {
      return fallback;
    }

    const resolved: WorldCamera = {
      x: asNumber(cameraState.x, fallback.x),
      y: asNumber(cameraState.y, fallback.y),
    };

    if (!mapSpec) {
      return resolved;
    }

    const worldWidth = mapSpec.width * mapSpec.tile_size;
    const worldHeight = mapSpec.height * mapSpec.tile_size;
    const halfViewW = this.canvas.width / 2;
    const halfViewH = this.canvas.height / 2;

    const minX = halfViewW;
    const maxX = Math.max(halfViewW, worldWidth - halfViewW);
    const minY = halfViewH;
    const maxY = Math.max(halfViewH, worldHeight - halfViewH);

    return {
      x: clamp(resolved.x, minX, maxX),
      y: clamp(resolved.y, minY, maxY),
    };
  }

  private drawTiles(mapSpec: MapSpec | null, camera: WorldCamera): void {
    if (!mapSpec) {
      return;
    }

    const tileSize = mapSpec.tile_size;
    const defaultTileColor = this.options.tileColor || "#2f3648";

    if (!Array.isArray(mapSpec.tile_grid)) {
      return;
    }

    for (let tileY = 0; tileY < mapSpec.tile_grid.length; tileY += 1) {
      const row = mapSpec.tile_grid[tileY];
      if (!Array.isArray(row)) {
        continue;
      }
      for (let tileX = 0; tileX < row.length; tileX += 1) {
        const tileId = row[tileX];
        if (typeof tileId !== "number" || !Number.isFinite(tileId)) {
          continue;
        }
        if (Math.trunc(tileId) === 0) {
          continue;
        }

        const worldX = tileX * tileSize + tileSize / 2;
        const worldY = tileY * tileSize + tileSize / 2;
        const screenX = this.worldToScreenX(worldX, camera) - tileSize / 2;
        const screenY = this.worldToScreenY(worldY, camera) - tileSize / 2;
        const tileDef = mapSpec.tile_defs?.[String(tileId)];

        const color = tileDef ? this.resolveTileColor(tileDef.color) : null;
        if (color) {
          this.ctx.fillStyle = color;
          this.ctx.fillRect(screenX, screenY, tileSize, tileSize);
          continue;
        }

        if (
          tileDef &&
          typeof tileDef.sprite === "string" &&
          this.drawTileSprite(tileDef.sprite, screenX, screenY, tileSize)
        ) {
          continue;
        }

        this.ctx.fillStyle = defaultTileColor;
        this.ctx.fillRect(screenX, screenY, tileSize, tileSize);
      }
    }
  }

  private resolveTileColor(
    color:
      | {
          r: number;
          g: number;
          b: number;
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
    return `rgb(${r}, ${g}, ${b})`;
  }

  private drawTileSprite(
    spriteName: string,
    screenX: number,
    screenY: number,
    tileSize: number,
  ): boolean {
    const sprite = this.options.spritesByName?.[spriteName];
    if (!sprite) {
      return false;
    }
    const image = this.assets.getImage(sprite.image);
    if (!image) {
      return false;
    }

    const clipName =
      sprite.defaultClip && sprite.clips[sprite.defaultClip]
        ? sprite.defaultClip
        : Object.keys(sprite.clips)[0];
    const clip = clipName ? sprite.clips[clipName] : null;
    if (!clip || !Array.isArray(clip.frames) || clip.frames.length === 0) {
      return false;
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
      sourceX < 0 ||
      sourceY < 0 ||
      sourceX + frameWidth > image.width ||
      sourceY + frameHeight > image.height
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
      tileSize,
      tileSize,
    );
    return true;
  }

  private drawActor(actor: ActorState, camera: WorldCamera): void {
    if (actor.active === false) {
      return;
    }

    const frameInfo = this.animation.getFrameInfo(actor);
    if (frameInfo && this.drawSprite(actor, frameInfo, camera)) {
      return;
    }

    const w = actorWidth(actor);
    const h = actorHeight(actor);
    const x = this.worldToScreenX(actorCenterX(actor), camera) - w / 2;
    const y = this.worldToScreenY(actorCenterY(actor), camera) - h / 2;
    this.ctx.fillStyle = this.resolveActorColor(actor);
    this.ctx.fillRect(x, y, w, h);
  }

  private drawSprite(
    actor: ActorState,
    frameInfo: SpriteFrameInfo | null,
    camera: WorldCamera,
  ): boolean {
    if (!frameInfo) {
      return false;
    }

    const { sprite, frameIndex, facing } = frameInfo;
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
      sourceX < 0 ||
      sourceY < 0 ||
      sourceX + frameWidth > image.width ||
      sourceY + frameHeight > image.height
    ) {
      return false;
    }

    const useActorSize = typeof actor.w === "number" && typeof actor.h === "number";
    const drawW = useActorSize
      ? Math.max(1, actorWidth(actor))
      : frameWidth * Math.max(0.1, asNumber(sprite.scale, 1));
    const drawH = useActorSize
      ? Math.max(1, actorHeight(actor))
      : frameHeight * Math.max(0.1, asNumber(sprite.scale, 1));

    const offsetX = asNumber(sprite.offsetX, 0);
    const offsetY = asNumber(sprite.offsetY, 0);

    const centerX = this.worldToScreenX(actorCenterX(actor), camera) + offsetX;
    const centerY = this.worldToScreenY(actorCenterY(actor), camera) + offsetY;
    const drawX = centerX - drawW / 2;
    const drawY = centerY - drawH / 2;

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

  private drawDebugColliders(actors: ActorState[], camera: WorldCamera): void {
    this.ctx.save();
    this.ctx.strokeStyle = "rgba(255, 255, 255, 0.45)";
    this.ctx.lineWidth = 1;

    for (const actor of actors) {
      if (actor.active === false) {
        continue;
      }
      const w = actorWidth(actor);
      const h = actorHeight(actor);
      const x = this.worldToScreenX(actorCenterX(actor), camera) - w / 2;
      const y = this.worldToScreenY(actorCenterY(actor), camera) - h / 2;
      this.ctx.strokeRect(x, y, w, h);
    }

    this.ctx.restore();
  }

  private drawHud(state: InterpreterState): void {
    this.ctx.save();
    this.ctx.fillStyle = "rgba(8, 10, 14, 0.62)";
    this.ctx.fillRect(10, 10, 240, 62);

    this.ctx.fillStyle = "#f2f5fa";
    this.ctx.font = "14px monospace";

    const globals = state.globals as Record<string, unknown>;
    const score = asNumber(globals.score, 0);
    const actors = Array.isArray(state.actors) ? state.actors.length : 0;

    this.ctx.fillText(`Score: ${score}`, 18, 34);
    this.ctx.fillText(`Actors: ${actors}`, 18, 54);
    this.ctx.restore();
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

  private worldToScreenX(worldX: number, camera: WorldCamera): number {
    return worldX - camera.x + this.canvas.width / 2;
  }

  private worldToScreenY(worldY: number, camera: WorldCamera): number {
    return worldY - camera.y + this.canvas.height / 2;
  }
}
