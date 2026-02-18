import {
  ActorState,
  CanvasHostOptions,
  CollisionPair,
  EPSILON,
  MapSpec,
  PhysicsBodyConfig,
  PhysicsBodyRuntime,
  ResolvedBodyConfig,
} from "./types";
import {
  actorCenterX,
  actorCenterY,
  actorHeight,
  actorWidth,
  asNumber,
  overlapsActors,
} from "./utils";

export class PhysicsSystem {
  private readonly options: CanvasHostOptions;
  private readonly bodies = new Map<string, PhysicsBodyRuntime>();
  private readonly tileBlockMasks = new Map<string, number>();
  private mapSpec: MapSpec | null = null;
  private gravityEnabled = false;
  private readonly gravityAcceleration: number;

  constructor(options: CanvasHostOptions) {
    this.options = options;
    this.gravityAcceleration = asNumber(options.physics?.gravity, 1200);
  }

  setMap(mapSpec: MapSpec | null): void {
    this.mapSpec = mapSpec;
    this.tileBlockMasks.clear();
    if (!mapSpec) {
      return;
    }

    if (Array.isArray(mapSpec.tile_grid)) {
      for (let tileY = 0; tileY < mapSpec.tile_grid.length; tileY += 1) {
        const row = mapSpec.tile_grid[tileY];
        if (!Array.isArray(row)) {
          continue;
        }
        for (let tileX = 0; tileX < row.length; tileX += 1) {
          const tileIdRaw = row[tileX];
          if (typeof tileIdRaw !== "number" || !Number.isFinite(tileIdRaw)) {
            continue;
          }
          const tileId = Math.trunc(tileIdRaw);
          if (tileId === 0) {
            continue;
          }
          const tileDef = mapSpec.tile_defs?.[String(tileId)];
          if (!tileDef || typeof tileDef !== "object") {
            continue;
          }
          const tileBlockMask = this.normalizeMaskValue(tileDef.block_mask);
          if (tileBlockMask === null) {
            continue;
          }
          this.tileBlockMasks.set(`${tileX},${tileY}`, tileBlockMask);
        }
      }
    }
  }

  getMap(): MapSpec | null {
    return this.mapSpec;
  }

  getBody(uid: string): PhysicsBodyRuntime | undefined {
    return this.bodies.get(uid);
  }

  setGravityEnabled(enabled: boolean): void {
    this.gravityEnabled = Boolean(enabled);
  }

  syncBodiesFromActors(actors: ActorState[], preserveVelocity: boolean): void {
    const alive = new Set<string>();

    for (const actor of actors) {
      alive.add(actor.uid);

      const body = this.ensureBody(actor);
      body.config = this.resolveBodyConfig(actor);
      body.w = actorWidth(actor);
      body.h = actorHeight(actor);
      body.blockMask = this.resolveActorMask(actor);
      body.active = actor.active !== false;
      body.x = actorCenterX(actor);
      body.y = actorCenterY(actor);

      if (!preserveVelocity) {
        body.vx = asNumber(actor.vx, body.vx);
        body.vy = asNumber(actor.vy, body.vy);
      }
    }

    for (const uid of this.bodies.keys()) {
      if (!alive.has(uid)) {
        this.bodies.delete(uid);
      }
    }
  }

  integrate(dtSeconds: number): void {
    for (const body of this.bodies.values()) {
      body.prevX = body.x;
      body.prevY = body.y;

      if (!body.config.enabled || !body.config.dynamic || !body.active) {
        continue;
      }

      if (this.gravityEnabled) {
        body.vy += this.gravityAcceleration * dtSeconds;
      }

      body.x += body.vx * dtSeconds;
      this.resolveHorizontalTileCollisions(body);

      body.y += body.vy * dtSeconds;
      body.onGround = false;
      this.resolveVerticalTileCollisions(body);

      this.clampBodyToWorld(body);
    }
  }

  resolvePostActionSolidCollisions(): void {
    for (const body of this.bodies.values()) {
      if (!body.config.enabled || !body.active || body.blockMask === null) {
        continue;
      }
      if (!this.isBodyTouchingBlockingTile(body)) {
        continue;
      }
      body.x = body.prevX;
      body.y = body.prevY;
      body.vx = 0;
      body.vy = 0;
    }
  }

  writeBodiesToActors(actors: ActorState[]): void {
    for (const actor of actors) {
      const body = this.bodies.get(actor.uid);
      if (!body || !body.config.enabled) {
        continue;
      }
      actor.x = body.x;
      actor.y = body.y;
      actor.vx = body.vx;
      actor.vy = body.vy;
      actor.onGround = body.onGround;
    }
  }

  detectCollisions(actors: ActorState[]): CollisionPair[] {
    const collisions: CollisionPair[] = [];
    for (let i = 0; i < actors.length; i += 1) {
      const a = actors[i];
      if (!this.isActorCollisionEnabled(a)) {
        continue;
      }
      for (let j = i + 1; j < actors.length; j += 1) {
        const b = actors[j];
        if (!this.isActorCollisionEnabled(b)) {
          continue;
        }
        if (overlapsActors(a, b)) {
          collisions.push({ aUid: a.uid, bUid: b.uid });
        }
      }
    }
    return collisions;
  }

  private ensureBody(actor: ActorState): PhysicsBodyRuntime {
    const existing = this.bodies.get(actor.uid);
    if (existing) {
      return existing;
    }

    const config = this.resolveBodyConfig(actor);
    const body: PhysicsBodyRuntime = {
      uid: actor.uid,
      x: actorCenterX(actor),
      y: actorCenterY(actor),
      w: actorWidth(actor),
      h: actorHeight(actor),
      blockMask: this.resolveActorMask(actor),
      vx: asNumber(actor.vx, 0),
      vy: asNumber(actor.vy, 0),
      onGround: false,
      active: actor.active !== false,
      prevX: actorCenterX(actor),
      prevY: actorCenterY(actor),
      config,
    };
    this.bodies.set(actor.uid, body);
    return body;
  }

  private resolveBodyConfig(actor: ActorState): ResolvedBodyConfig {
    const inferredDefault: PhysicsBodyConfig = {
      enabled: true,
      dynamic: actor.type === "Player" || actor.type === "Enemy",
      collidable: true,
    };

    const defaultBody = this.options.physics?.defaultBody || {};
    const byType = this.options.physics?.bodiesByType?.[actor.type] || {};
    const byUid = this.options.physics?.bodiesByUid?.[actor.uid] || {};
    const merged: PhysicsBodyConfig = {
      ...inferredDefault,
      ...defaultBody,
      ...byType,
      ...byUid,
    };

    return {
      enabled: merged.enabled !== false,
      dynamic: Boolean(merged.dynamic),
      collidable: merged.collidable !== false,
    };
  }

  private resolveHorizontalTileCollisions(body: PhysicsBodyRuntime): void {
    if (
      !this.mapSpec ||
      body.vx === 0 ||
      body.blockMask === null
    ) {
      return;
    }

    const tileSize = this.mapSpec.tile_size;
    const halfW = body.w / 2;
    const halfH = body.h / 2;
    const top = body.y - halfH + 1;
    const bottom = body.y + halfH - 1;
    const topTile = Math.floor(top / tileSize);
    const bottomTile = Math.floor(bottom / tileSize);

    if (body.vx > 0) {
      const rightEdge = body.x + halfW;
      const tileX = Math.floor(rightEdge / tileSize);
      for (let tileY = topTile; tileY <= bottomTile; tileY += 1) {
        if (this.isTileBlockingForActorMask(tileX, tileY, body.blockMask)) {
          body.x = tileX * tileSize - halfW - EPSILON;
          body.vx = 0;
          return;
        }
      }
      return;
    }

    const leftEdge = body.x - halfW;
    const tileX = Math.floor(leftEdge / tileSize);
    for (let tileY = topTile; tileY <= bottomTile; tileY += 1) {
      if (this.isTileBlockingForActorMask(tileX, tileY, body.blockMask)) {
        body.x = (tileX + 1) * tileSize + halfW + EPSILON;
        body.vx = 0;
        return;
      }
    }
  }

  private resolveVerticalTileCollisions(body: PhysicsBodyRuntime): void {
    if (
      !this.mapSpec ||
      body.vy === 0 ||
      body.blockMask === null
    ) {
      return;
    }

    const tileSize = this.mapSpec.tile_size;
    const halfW = body.w / 2;
    const halfH = body.h / 2;
    const left = body.x - halfW + 1;
    const right = body.x + halfW - 1;
    const leftTile = Math.floor(left / tileSize);
    const rightTile = Math.floor(right / tileSize);

    if (body.vy > 0) {
      const bottomEdge = body.y + halfH;
      const tileY = Math.floor(bottomEdge / tileSize);
      for (let tileX = leftTile; tileX <= rightTile; tileX += 1) {
        if (this.isTileBlockingForActorMask(tileX, tileY, body.blockMask)) {
          body.y = tileY * tileSize - halfH - EPSILON;
          body.vy = 0;
          body.onGround = true;
          return;
        }
      }
      return;
    }

    const topEdge = body.y - halfH;
    const tileY = Math.floor(topEdge / tileSize);
    for (let tileX = leftTile; tileX <= rightTile; tileX += 1) {
      if (this.isTileBlockingForActorMask(tileX, tileY, body.blockMask)) {
        body.y = (tileY + 1) * tileSize + halfH + EPSILON;
        body.vy = 0;
        return;
      }
    }
  }

  private clampBodyToWorld(body: PhysicsBodyRuntime): void {
    if (!this.mapSpec) {
      return;
    }

    const worldWidth = this.mapSpec.width * this.mapSpec.tile_size;
    const worldHeight = this.mapSpec.height * this.mapSpec.tile_size;
    const halfW = body.w / 2;
    const halfH = body.h / 2;

    const minX = halfW;
    const maxX = Math.max(halfW, worldWidth - halfW);
    const minY = halfH;
    const maxY = Math.max(halfH, worldHeight - halfH);

    if (body.x < minX) {
      body.x = minX;
      body.vx = 0;
    } else if (body.x > maxX) {
      body.x = maxX;
      body.vx = 0;
    }

    if (body.y < minY) {
      body.y = minY;
      body.vy = 0;
    } else if (body.y > maxY) {
      body.y = maxY;
      body.vy = 0;
      body.onGround = true;
    }
  }

  private isBodyTouchingBlockingTile(body: PhysicsBodyRuntime): boolean {
    if (!this.mapSpec || body.blockMask === null) {
      return false;
    }
    const corners: Array<[number, number]> = [
      [body.x - body.w / 2 + 1, body.y - body.h / 2 + 1],
      [body.x + body.w / 2 - 1, body.y - body.h / 2 + 1],
      [body.x - body.w / 2 + 1, body.y + body.h / 2 - 1],
      [body.x + body.w / 2 - 1, body.y + body.h / 2 - 1],
    ];

    for (const [x, y] of corners) {
      const tileX = Math.floor(x / this.mapSpec.tile_size);
      const tileY = Math.floor(y / this.mapSpec.tile_size);
      if (this.isTileBlockingForActorMask(tileX, tileY, body.blockMask)) {
        return true;
      }
    }
    return false;
  }

  private isActorCollisionEnabled(actor: ActorState): boolean {
    if (actor.active === false) {
      return false;
    }
    const body = this.bodies.get(actor.uid);
    if (body && !body.config.collidable) {
      return false;
    }
    return true;
  }

  private resolveActorMask(actor: ActorState): number | null {
    return this.normalizeMaskValue(actor.block_mask);
  }

  private normalizeMaskValue(value: unknown): number | null {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      return null;
    }
    return Math.trunc(value);
  }

  private isTileBlockingForActorMask(
    tileX: number,
    tileY: number,
    actorMask: number,
  ): boolean {
    if (!this.mapSpec) {
      return false;
    }
    if (
      tileX < 0 ||
      tileY < 0 ||
      tileX >= this.mapSpec.width ||
      tileY >= this.mapSpec.height
    ) {
      return true;
    }
    const tileMask = this.tileBlockMasks.get(`${tileX},${tileY}`);
    if (tileMask === undefined) {
      return false;
    }
    return tileMask > actorMask;
  }
}
