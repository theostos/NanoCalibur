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
      body.parentUid =
        typeof actor.parent === "string" && actor.parent.trim().length > 0
          ? actor.parent
          : undefined;
      body.x = actorCenterX(actor);
      body.y = actorCenterY(actor);

      body.vx = asNumber(actor.vx, body.vx);
      body.vy = asNumber(actor.vy, body.vy);
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
    this.resolvePostActionTileBlocking();
    this.resolveActorMaskCollisions();
    // Actor separation can push actors into solid tiles near boundaries.
    // Run tile blocking once more to keep post-action state valid.
    this.resolvePostActionTileBlocking();
  }

  private resolvePostActionTileBlocking(): void {
    const constrainedAttachmentRoots = new Set<string>();
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
      if (body.parentUid) {
        constrainedAttachmentRoots.add(body.parentUid);
      }
    }

    if (constrainedAttachmentRoots.size === 0) {
      return;
    }

    for (const rootUid of constrainedAttachmentRoots) {
      this.rollbackAttachmentTreeToPrevious(rootUid);
    }
  }

  private resolveActorMaskCollisions(): void {
    const candidates = Array.from(this.bodies.values()).filter((body) =>
      this.isBodyActorMaskCollisionEnabled(body),
    );
    if (candidates.length < 2) {
      return;
    }

    for (let pass = 0; pass < 4; pass += 1) {
      let moved = false;

      for (let i = 0; i < candidates.length; i += 1) {
        const a = candidates[i];
        for (let j = i + 1; j < candidates.length; j += 1) {
          const b = candidates[j];
          if (a.blockMask !== b.blockMask) {
            continue;
          }
          if (this.areBodiesDirectlyAttached(a, b)) {
            continue;
          }

          const overlapX = (a.w + b.w) / 2 - Math.abs(a.x - b.x);
          const overlapY = (a.h + b.h) / 2 - Math.abs(a.y - b.y);
          if (overlapX <= 0 || overlapY <= 0) {
            continue;
          }

          const resolveOnX = overlapX <= overlapY;
          const overlap = (resolveOnX ? overlapX : overlapY) + EPSILON;
          const attachmentConstraintRoot = this.resolveAttachmentConstraintRoot(
            a,
            b,
            resolveOnX,
          );
          if (attachmentConstraintRoot) {
            this.rollbackAttachmentTreeToPrevious(attachmentConstraintRoot);
            moved = true;
            continue;
          }
          const direction = this.resolveSeparationDirection(a, b, resolveOnX);
          if (!this.separateBodiesAlongAxis(a, b, overlap, resolveOnX, direction)) {
            continue;
          }
          moved = true;
        }
      }

      if (!moved) {
        break;
      }
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

  detectContacts(actors: ActorState[]): CollisionPair[] {
    const contacts: CollisionPair[] = [];
    for (let i = 0; i < actors.length; i += 1) {
      const a = actors[i];
      if (!this.isActorCollisionEnabled(a)) {
        continue;
      }
      const bodyA = this.bodies.get(a.uid);
      if (!bodyA || !this.isBodyActorMaskCollisionEnabled(bodyA)) {
        continue;
      }

      for (let j = i + 1; j < actors.length; j += 1) {
        const b = actors[j];
        if (!this.isActorCollisionEnabled(b)) {
          continue;
        }
        const bodyB = this.bodies.get(b.uid);
        if (!bodyB || !this.isBodyActorMaskCollisionEnabled(bodyB)) {
          continue;
        }
        if (this.areBodiesDirectlyAttached(bodyA, bodyB)) {
          continue;
        }
        if (bodyA.blockMask !== bodyB.blockMask) {
          continue;
        }
        if (this.areBodiesTouchingOrOverlapping(bodyA, bodyB)) {
          contacts.push({ aUid: a.uid, bUid: b.uid });
        }
      }
    }
    return contacts;
  }

  detectTileOverlaps(
    actors: ActorState[],
  ): Array<{ actorUid: string; tileX: number; tileY: number; tileMask: number }> {
    const overlaps: Array<{
      actorUid: string;
      tileX: number;
      tileY: number;
      tileMask: number;
    }> = [];
    if (!this.mapSpec) {
      return overlaps;
    }

    for (const actor of actors) {
      if (!this.isActorCollisionEnabled(actor)) {
        continue;
      }
      const body = this.bodies.get(actor.uid);
      if (!body || body.blockMask === null) {
        continue;
      }

      const leftTile = Math.floor((body.x - body.w / 2 + 1) / this.mapSpec.tile_size);
      const rightTile = Math.floor((body.x + body.w / 2 - 1) / this.mapSpec.tile_size);
      const topTile = Math.floor((body.y - body.h / 2 + 1) / this.mapSpec.tile_size);
      const bottomTile = Math.floor((body.y + body.h / 2 - 1) / this.mapSpec.tile_size);

      for (let tileY = topTile; tileY <= bottomTile; tileY += 1) {
        for (let tileX = leftTile; tileX <= rightTile; tileX += 1) {
          if (!this.mapSpec) {
            continue;
          }
          if (
            tileX < 0 ||
            tileY < 0 ||
            tileX >= this.mapSpec.width ||
            tileY >= this.mapSpec.height
          ) {
            continue;
          }
          if (!this.isTileBlockingForActorMask(tileX, tileY, body.blockMask)) {
            continue;
          }
          const tileMask = this.tileBlockMasks.get(`${tileX},${tileY}`);
          if (tileMask === undefined) {
            continue;
          }
          overlaps.push({
            actorUid: actor.uid,
            tileX,
            tileY,
            tileMask,
          });
        }
      }
    }
    return overlaps;
  }

  private ensureBody(actor: ActorState): PhysicsBodyRuntime {
    const existing = this.bodies.get(actor.uid);
    if (existing) {
      return existing;
    }

    const config = this.resolveBodyConfig(actor);
    const body: PhysicsBodyRuntime = {
      uid: actor.uid,
      parentUid:
        typeof actor.parent === "string" && actor.parent.trim().length > 0
          ? actor.parent
          : undefined,
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

  private isBodyActorMaskCollisionEnabled(body: PhysicsBodyRuntime): boolean {
    return (
      body.active &&
      body.config.enabled &&
      body.config.collidable &&
      body.blockMask !== null
    );
  }

  private areBodiesDirectlyAttached(
    a: PhysicsBodyRuntime,
    b: PhysicsBodyRuntime,
  ): boolean {
    return a.parentUid === b.uid || b.parentUid === a.uid;
  }

  private resolveSeparationDirection(
    a: PhysicsBodyRuntime,
    b: PhysicsBodyRuntime,
    onX: boolean,
  ): number {
    const aAxis = onX ? a.x : a.y;
    const bAxis = onX ? b.x : b.y;
    if (aAxis < bAxis) {
      return -1;
    }
    if (aAxis > bAxis) {
      return 1;
    }

    const aPrev = onX ? a.prevX : a.prevY;
    const bPrev = onX ? b.prevX : b.prevY;
    if (aPrev < bPrev) {
      return -1;
    }
    if (aPrev > bPrev) {
      return 1;
    }
    return a.uid < b.uid ? -1 : 1;
  }

  private separateBodiesAlongAxis(
    a: PhysicsBodyRuntime,
    b: PhysicsBodyRuntime,
    overlap: number,
    onX: boolean,
    direction: number,
  ): boolean {
    let moveA = 0;
    let moveB = 0;
    if (a.config.dynamic && b.config.dynamic) {
      const aMoved = this.bodyMovedAlongAxis(a, onX);
      const bMoved = this.bodyMovedAlongAxis(b, onX);
      if (aMoved && !bMoved) {
        moveA = overlap;
      } else if (!aMoved && bMoved) {
        moveB = overlap;
      } else {
        moveA = overlap / 2;
        moveB = overlap - moveA;
      }
    } else if (a.config.dynamic) {
      moveA = overlap;
    } else if (b.config.dynamic) {
      moveB = overlap;
    } else {
      return false;
    }

    if (onX) {
      if (moveA > 0) {
        a.x += direction * moveA;
        a.vx = 0;
      }
      if (moveB > 0) {
        b.x -= direction * moveB;
        b.vx = 0;
      }
    } else {
      if (moveA > 0) {
        a.y += direction * moveA;
        a.vy = 0;
      }
      if (moveB > 0) {
        b.y -= direction * moveB;
        b.vy = 0;
      }
    }

    if (moveA > 0) {
      this.clampBodyToWorld(a);
    }
    if (moveB > 0) {
      this.clampBodyToWorld(b);
    }
    return true;
  }

  private resolveAttachmentConstraintRoot(
    a: PhysicsBodyRuntime,
    b: PhysicsBodyRuntime,
    onX: boolean,
  ): string | null {
    const aConstraintRoot = this.resolveAttachmentConstraintRootForPairMember(a, b, onX);
    if (aConstraintRoot) {
      return aConstraintRoot;
    }
    return this.resolveAttachmentConstraintRootForPairMember(b, a, onX);
  }

  private resolveAttachmentConstraintRootForPairMember(
    attachedCandidate: PhysicsBodyRuntime,
    other: PhysicsBodyRuntime,
    onX: boolean,
  ): string | null {
    if (!attachedCandidate.parentUid) {
      return null;
    }

    const rootUid = this.findAttachmentRootUid(attachedCandidate.uid);
    if (!rootUid) {
      return null;
    }
    if (this.findAttachmentRootUid(other.uid) === rootUid) {
      return null;
    }

    const rootBody = this.bodies.get(rootUid);
    if (!rootBody || !this.bodyMovedAlongAxis(rootBody, onX)) {
      return null;
    }
    return rootUid;
  }

  private findAttachmentRootUid(uid: string): string | null {
    const visited = new Set<string>();
    let currentUid: string | undefined = uid;

    while (currentUid) {
      if (visited.has(currentUid)) {
        return null;
      }
      visited.add(currentUid);
      const current = this.bodies.get(currentUid);
      if (!current) {
        return null;
      }
      if (!current.parentUid) {
        return currentUid;
      }
      currentUid = current.parentUid;
    }

    return null;
  }

  private bodyMovedAlongAxis(body: PhysicsBodyRuntime, onX: boolean): boolean {
    const current = onX ? body.x : body.y;
    const previous = onX ? body.prevX : body.prevY;
    const velocity = onX ? body.vx : body.vy;
    return Math.abs(current - previous) > EPSILON || Math.abs(velocity) > EPSILON;
  }

  private rollbackAttachmentTreeToPrevious(rootUid: string): void {
    const visited = new Set<string>();
    const queue: string[] = [rootUid];

    while (queue.length > 0) {
      const uid = queue.shift()!;
      if (visited.has(uid)) {
        continue;
      }
      visited.add(uid);

      const body = this.bodies.get(uid);
      if (body) {
        body.x = body.prevX;
        body.y = body.prevY;
        body.vx = 0;
        body.vy = 0;
      }

      for (const candidate of this.bodies.values()) {
        if (candidate.parentUid === uid && !visited.has(candidate.uid)) {
          queue.push(candidate.uid);
        }
      }
    }
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

  private areBodiesTouchingOrOverlapping(
    a: PhysicsBodyRuntime,
    b: PhysicsBodyRuntime,
  ): boolean {
    const dx = Math.abs(a.x - b.x);
    const dy = Math.abs(a.y - b.y);
    const halfW = (a.w + b.w) / 2;
    const halfH = (a.h + b.h) / 2;
    const tolerance = EPSILON * 2;

    return dx <= halfW + tolerance && dy <= halfH + tolerance;
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
