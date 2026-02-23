import { InterpreterState } from "./interpreter";
import {
  ActorState,
  CanvasHostOptions,
  DEFAULT_HEIGHT,
  DEFAULT_WIDTH,
  MapSpec,
  SpriteAnimationConfig,
  SymbolicFrame,
  SymbolicStackActorItem,
  SymbolicStackCell,
  SymbolicLegendItem,
} from "./canvas/types";
import { actorCenterX, actorCenterY, asNumber } from "./canvas/utils";

interface SymbolicViewport {
  width: number;
  height: number;
  originX: number;
  originY: number;
}

interface TileSymbolInfo {
  symbol: string;
  description: string;
}

export interface SymbolicViewer {
  roleId?: string | null;
  roleKind?: string | null;
}

export class SymbolicRenderer {
  private readonly options: CanvasHostOptions;

  constructor(options: CanvasHostOptions) {
    this.options = options;
  }

  render(
    state: InterpreterState,
    mapSpec: MapSpec | null,
    viewer: SymbolicViewer = {},
  ): SymbolicFrame {
    const actors = (state.actors || []) as ActorState[];
    const tileSize = mapSpec ? Math.max(1, asNumber(mapSpec.tile_size, 32)) : 32;
    const cameraState = this.resolveViewerCamera(state, viewer.roleId || null);
    const roleKind = typeof viewer.roleKind === "string" ? viewer.roleKind.toLowerCase() : null;
    if (roleKind === "ai" && viewer.roleId && !cameraState) {
      return {
        width: 0,
        height: 0,
        rows: [],
        legend: [],
        stacks: [],
      };
    }
    const viewport = this.resolveViewport(state, actors, mapSpec, tileSize, cameraState);
    const { width, height, originX, originY } = viewport;

    const emptySymbol = this.normalizeSymbol(this.options.symbolic?.emptySymbol) || ".";
    const tileSymbol = this.normalizeSymbol(this.options.symbolic?.tileSymbol) || "#";

    const grid: string[][] = Array.from({ length: height }, () =>
      Array.from({ length: width }, () => emptySymbol),
    );

    const legendBySymbol = new Map<string, string>();
    if (mapSpec) {
      this.drawTiles(mapSpec, viewport, grid, legendBySymbol, tileSymbol);
    }

    const sortedActors = [...actors]
      .filter((actor) => actor.active !== false)
      .sort((a, b) => asNumber(a.z, 0) - asNumber(b.z, 0));
    const stackByCell = new Map<string, SymbolicStackActorItem[]>();

    for (const actor of sortedActors) {
      const { symbol, description } = this.resolveActorSymbol(actor);
      const bounds = this.resolveActorTileBounds(actor, tileSize);
      for (let worldTileY = bounds.minTileY; worldTileY <= bounds.maxTileY; worldTileY += 1) {
        const tileY = worldTileY - originY;
        if (tileY < 0 || tileY >= viewport.height) {
          continue;
        }
        for (let worldTileX = bounds.minTileX; worldTileX <= bounds.maxTileX; worldTileX += 1) {
          const tileX = worldTileX - originX;
          if (tileX < 0 || tileX >= viewport.width) {
            continue;
          }
          grid[tileY][tileX] = symbol;
          if (!legendBySymbol.has(symbol)) {
            legendBySymbol.set(symbol, description);
          }
          const cellKey = `${tileX},${tileY}`;
          const actorStack = stackByCell.get(cellKey) || [];
          actorStack.push({
            uid: typeof actor.uid === "string" ? actor.uid : "",
            type: typeof actor.type === "string" ? actor.type : "",
            symbol,
            description,
            z: asNumber(actor.z, 0),
          });
          stackByCell.set(cellKey, actorStack);
        }
      }
    }

    const legend: SymbolicLegendItem[] = Array.from(legendBySymbol.entries()).map(
      ([symbol, description]) => ({ symbol, description }),
    );
    const stacks = this.buildStacks(stackByCell, grid);

    return {
      width,
      height,
      rows: grid.map((row) => row.join("")),
      legend,
      stacks,
    };
  }

  private resolveActorTileBounds(
    actor: ActorState,
    tileSize: number,
  ): { minTileX: number; maxTileX: number; minTileY: number; maxTileY: number } {
    const width = this.resolveActorDrawWidth(actor, tileSize);
    const height = this.resolveActorDrawHeight(actor, tileSize);
    const centerTileX = Math.floor(actorCenterX(actor) / tileSize);
    const centerTileY = Math.floor(actorCenterY(actor) / tileSize);
    if (width <= tileSize && height <= tileSize) {
      return {
        minTileX: centerTileX,
        maxTileX: centerTileX,
        minTileY: centerTileY,
        maxTileY: centerTileY,
      };
    }
    const halfW = width / 2;
    const halfH = height / 2;
    const minTileX = Math.floor((actorCenterX(actor) - halfW) / tileSize);
    const maxTileX = Math.floor((actorCenterX(actor) + halfW - 0.001) / tileSize);
    const minTileY = Math.floor((actorCenterY(actor) - halfH) / tileSize);
    const maxTileY = Math.floor((actorCenterY(actor) + halfH - 0.001) / tileSize);
    return {
      minTileX,
      maxTileX: Math.max(minTileX, maxTileX),
      minTileY,
      maxTileY: Math.max(minTileY, maxTileY),
    };
  }

  private resolveActorDrawWidth(actor: ActorState, tileSize: number): number {
    if (typeof actor.w === "number" && Number.isFinite(actor.w) && actor.w > 0) {
      return actor.w;
    }
    const sprite = this.resolveSpriteConfig(actor);
    if (sprite) {
      const scale = Math.max(0.1, asNumber(sprite.scale, 1));
      return Math.max(1, asNumber(sprite.frameWidth, tileSize) * scale);
    }
    return tileSize;
  }

  private resolveActorDrawHeight(actor: ActorState, tileSize: number): number {
    if (typeof actor.h === "number" && Number.isFinite(actor.h) && actor.h > 0) {
      return actor.h;
    }
    const sprite = this.resolveSpriteConfig(actor);
    if (sprite) {
      const scale = Math.max(0.1, asNumber(sprite.scale, 1));
      return Math.max(1, asNumber(sprite.frameHeight, tileSize) * scale);
    }
    return tileSize;
  }

  private buildStacks(
    stackByCell: Map<string, SymbolicStackActorItem[]>,
    grid: string[][],
  ): SymbolicStackCell[] {
    const stacks: SymbolicStackCell[] = [];
    for (const [cellKey, actors] of stackByCell.entries()) {
      if (!Array.isArray(actors) || actors.length <= 1) {
        continue;
      }
      const parts = cellKey.split(",");
      if (parts.length !== 2) {
        continue;
      }
      const x = Number(parts[0]);
      const y = Number(parts[1]);
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        continue;
      }
      if (y < 0 || y >= grid.length || x < 0 || x >= grid[y].length) {
        continue;
      }
      stacks.push({
        x,
        y,
        symbol: grid[y][x],
        actors,
      });
    }
    stacks.sort((a, b) => (a.y - b.y) || (a.x - b.x));
    return stacks;
  }

  private resolveViewport(
    state: InterpreterState,
    actors: ActorState[],
    mapSpec: MapSpec | null,
    tileSize: number,
    cameraState: Record<string, any> | null,
  ): SymbolicViewport {
    const world = this.resolveWorldDimensions(actors, mapSpec, tileSize);
    const requestedWidth = this.resolveRequestedCropDimension(
      "width",
      tileSize,
      mapSpec,
      world.width,
      cameraState && typeof cameraState.width === "number" ? cameraState.width : null,
    );
    const requestedHeight = this.resolveRequestedCropDimension(
      "height",
      tileSize,
      mapSpec,
      world.height,
      cameraState && typeof cameraState.height === "number" ? cameraState.height : null,
    );
    const viewportWidth =
      mapSpec != null
        ? Math.max(1, Math.min(requestedWidth, world.width))
        : Math.max(1, requestedWidth);
    const viewportHeight =
      mapSpec != null
        ? Math.max(1, Math.min(requestedHeight, world.height))
        : Math.max(1, requestedHeight);

    const fallbackCenterX =
      world.width > 0 ? ((world.minX + world.maxX + 1) * tileSize) / 2 : tileSize / 2;
    const fallbackCenterY =
      world.height > 0 ? ((world.minY + world.maxY + 1) * tileSize) / 2 : tileSize / 2;
    const centerWorldX = asNumber(cameraState?.x, fallbackCenterX);
    const centerWorldY = asNumber(cameraState?.y, fallbackCenterY);

    let originX = Math.floor(centerWorldX / tileSize - viewportWidth / 2);
    let originY = Math.floor(centerWorldY / tileSize - viewportHeight / 2);

    if (mapSpec) {
      const maxOriginX = Math.max(0, mapSpec.width - viewportWidth);
      const maxOriginY = Math.max(0, mapSpec.height - viewportHeight);
      originX = Math.max(0, Math.min(originX, maxOriginX));
      originY = Math.max(0, Math.min(originY, maxOriginY));
    } else {
      const minOriginX = Math.min(0, world.minX);
      const minOriginY = Math.min(0, world.minY);
      const maxOriginX = Math.max(minOriginX, world.maxX - viewportWidth + 1);
      const maxOriginY = Math.max(minOriginY, world.maxY - viewportHeight + 1);
      originX = Math.max(minOriginX, Math.min(originX, maxOriginX));
      originY = Math.max(minOriginY, Math.min(originY, maxOriginY));
    }

    return {
      width: viewportWidth,
      height: viewportHeight,
      originX,
      originY,
    };
  }

  private resolveWorldDimensions(
    actors: ActorState[],
    mapSpec: MapSpec | null,
    tileSize: number,
  ): { width: number; height: number; minX: number; minY: number; maxX: number; maxY: number } {
    if (mapSpec) {
      const width = this.applyDimensionLimit(Math.max(1, mapSpec.width), "width");
      const height = this.applyDimensionLimit(Math.max(1, mapSpec.height), "height");
      return {
        width,
        height,
        minX: 0,
        minY: 0,
        maxX: width - 1,
        maxY: height - 1,
      };
    }

    let minX = 0;
    let minY = 0;
    let maxX = 0;
    let maxY = 0;
    let hasActor = false;
    for (const actor of actors) {
      if (actor.active === false) {
        continue;
      }
      hasActor = true;
      const tileX = Math.floor(actorCenterX(actor) / tileSize);
      const tileY = Math.floor(actorCenterY(actor) / tileSize);
      minX = Math.min(minX, tileX);
      minY = Math.min(minY, tileY);
      maxX = Math.max(maxX, tileX);
      maxY = Math.max(maxY, tileY);
    }

    if (!hasActor) {
      minX = 0;
      minY = 0;
      maxX = 0;
      maxY = 0;
    }

    return {
      width: this.applyDimensionLimit(Math.max(1, maxX - minX + 1), "width"),
      height: this.applyDimensionLimit(Math.max(1, maxY - minY + 1), "height"),
      minX,
      minY,
      maxX,
      maxY,
    };
  }

  private resolveRequestedCropDimension(
    axis: "width" | "height",
    tileSize: number,
    mapSpec: MapSpec | null,
    worldDimension: number,
    cameraDimension: number | null,
  ): number {
    if (
      typeof cameraDimension === "number" &&
      Number.isFinite(cameraDimension) &&
      cameraDimension > 0
    ) {
      return this.applyDimensionLimit(Math.floor(cameraDimension), axis);
    }

    const explicit =
      axis === "width"
        ? this.options.symbolic?.cropWidth
        : this.options.symbolic?.cropHeight;
    if (typeof explicit === "number" && Number.isFinite(explicit) && explicit > 0) {
      return this.applyDimensionLimit(Math.floor(explicit), axis);
    }

    const screenPixels =
      axis === "width"
        ? asNumber(this.options.width, DEFAULT_WIDTH)
        : asNumber(this.options.height, DEFAULT_HEIGHT);
    if (screenPixels > 0) {
      return this.applyDimensionLimit(Math.max(1, Math.ceil(screenPixels / tileSize)), axis);
    }

    if (mapSpec) {
      const mapDimension = axis === "width" ? mapSpec.width : mapSpec.height;
      return this.applyDimensionLimit(Math.max(1, mapDimension), axis);
    }

    return this.applyDimensionLimit(Math.max(1, worldDimension), axis);
  }

  private resolveViewerCamera(
    state: InterpreterState,
    roleId: string | null,
  ): Record<string, any> | null {
    const byName =
      state &&
      state.cameras &&
      typeof state.cameras === "object"
        ? (state.cameras as Record<string, any>)
        : null;

    if (roleId) {
      if (byName) {
        for (const camera of Object.values(byName)) {
          if (!camera || typeof camera !== "object") {
            continue;
          }
          if (camera.role_id === roleId) {
            return camera;
          }
        }
      }

      // Role-scoped viewers must not silently fall back to another role camera.
      if (state && state.camera && typeof state.camera === "object") {
        const defaultCamera = state.camera as Record<string, any>;
        if (
          typeof defaultCamera.role_id !== "string" ||
          !defaultCamera.role_id ||
          defaultCamera.role_id === roleId
        ) {
          return defaultCamera;
        }
      }

      if (byName) {
        for (const camera of Object.values(byName)) {
          if (!camera || typeof camera !== "object") {
            continue;
          }
          if (typeof camera.role_id !== "string" || !camera.role_id) {
            return camera;
          }
        }
      }
      return null;
    }

    if (state && state.camera && typeof state.camera === "object") {
      return state.camera as Record<string, any>;
    }

    if (byName) {
      for (const camera of Object.values(byName)) {
        if (camera && typeof camera === "object") {
          return camera;
        }
      }
    }
    return null;
  }

  private drawTiles(
    mapSpec: MapSpec,
    viewport: SymbolicViewport,
    grid: string[][],
    legendBySymbol: Map<string, string>,
    tileSymbol: string,
  ): void {
    const blockingDescription = "a solid tile";
    if (!Array.isArray(mapSpec.tile_grid)) {
      return;
    }

    for (let localY = 0; localY < viewport.height; localY += 1) {
      const worldY = viewport.originY + localY;
      if (worldY < 0 || worldY >= mapSpec.height) {
        continue;
      }
      const row = mapSpec.tile_grid[worldY];
      if (!Array.isArray(row)) {
        continue;
      }

      for (let localX = 0; localX < viewport.width; localX += 1) {
        const worldX = viewport.originX + localX;
        if (worldX < 0 || worldX >= mapSpec.width || worldX >= row.length) {
          continue;
        }

        const rawTileId = row[worldX];
        if (typeof rawTileId !== "number" || !Number.isFinite(rawTileId)) {
          continue;
        }
        const tileId = Math.trunc(rawTileId);
        if (tileId === 0) {
          continue;
        }

        const tileDef = mapSpec.tile_defs?.[String(tileId)];
        if (tileDef && typeof tileDef === "object") {
          const tileInfo = this.resolveTileSymbolInfo(tileDef, tileSymbol);
          if (tileInfo) {
            grid[localY][localX] = tileInfo.symbol;
            if (!legendBySymbol.has(tileInfo.symbol)) {
              legendBySymbol.set(tileInfo.symbol, tileInfo.description);
            }
            continue;
          }
        }

        grid[localY][localX] = tileSymbol;
        if (!legendBySymbol.has(tileSymbol)) {
          legendBySymbol.set(tileSymbol, blockingDescription);
        }
      }
    }
  }

  private resolveTileSymbolInfo(
    tileDef: {
      sprite?: string | null;
      color?: {
        r: number;
        g: number;
        b: number;
        a?: number;
        symbol?: string | null;
        description?: string | null;
      } | null;
    },
    tileSymbol: string,
  ): TileSymbolInfo | null {
    if (tileDef.color && typeof tileDef.color === "object") {
      const symbol = this.normalizeSymbol(tileDef.color.symbol) || tileSymbol;
      const description =
        typeof tileDef.color.description === "string" && tileDef.color.description
          ? tileDef.color.description
          : "a colored tile";
      return { symbol, description };
    }

    if (typeof tileDef.sprite === "string" && tileDef.sprite) {
      const sprite = this.options.spritesByName?.[tileDef.sprite];
      const symbol = this.normalizeSymbol(sprite?.symbol) || tileSymbol;
      const description =
        (sprite && typeof sprite.description === "string" && sprite.description) ||
        `${tileDef.sprite} tile`;
      return { symbol, description };
    }
    return null;
  }

  private applyDimensionLimit(
    value: number,
    axis: "width" | "height",
  ): number {
    const configured =
      axis === "width" ? this.options.symbolic?.maxWidth : this.options.symbolic?.maxHeight;
    if (typeof configured !== "number" || !Number.isFinite(configured)) {
      return value;
    }
    return Math.max(1, Math.min(value, Math.floor(configured)));
  }

  private resolveActorSymbol(actor: ActorState): { symbol: string; description: string } {
    const sprite = this.resolveSpriteConfig(actor);
    const fallback =
      this.normalizeSymbol(this.options.symbolic?.fallbackSymbol) ||
      this.normalizeSymbol(actor.type) ||
      "?";

    const spriteSymbol = this.normalizeSymbol(sprite?.symbol);
    const symbol = spriteSymbol || fallback;
    const description =
      (sprite && typeof sprite.description === "string" && sprite.description) ||
      `${actor.type} actor`;

    return { symbol, description };
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

  private normalizeSymbol(value: unknown): string | null {
    if (typeof value !== "string") {
      return null;
    }
    if (!value) {
      return null;
    }
    return value[0];
  }
}
