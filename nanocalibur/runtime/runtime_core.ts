import {
  CollisionFrameInput,
  InterpreterState,
  NanoCaliburFrameInput,
  NanoCaliburInterpreter,
  ToolFrameInput,
} from "./interpreter";
import { AnimationSystem } from "./canvas/animation";
import { PhysicsSystem } from "./canvas/physics";
import {
  ActorState,
  CanvasHostOptions,
  MapSpec,
  PhasePayload,
  SceneState,
  SpecResourceDef,
  SpecSpriteDef,
  SpriteAnimationConfig,
} from "./canvas/types";
import { asNumber } from "./canvas/utils";

export interface RuntimeStepInput {
  keyboard?: PhasePayload;
  mouse?: PhasePayload;
  uiButtons?: string[];
  toolCalls?: Array<string | ToolFrameInput>;
  roleId?: string;
  role_id?: string;
}

function toSpriteConfig(specSprite: SpecSpriteDef): SpriteAnimationConfig | null {
  if (!specSprite || typeof specSprite !== "object") {
    return null;
  }

  const clipsObj = specSprite.clips || {};
  const clips: SpriteAnimationConfig["clips"] = {};

  for (const [clipName, clipDef] of Object.entries(clipsObj)) {
    if (!clipDef || !Array.isArray(clipDef.frames) || clipDef.frames.length === 0) {
      continue;
    }
    clips[clipName] = {
      frames: clipDef.frames,
      ticksPerFrame: clipDef.ticks_per_frame,
      loop: clipDef.loop,
    };
  }

  if (Object.keys(clips).length === 0) {
    return null;
  }

  return {
    image: specSprite.resource,
    frameWidth: specSprite.frame_width,
    frameHeight: specSprite.frame_height,
    symbol: specSprite.symbol,
    description: specSprite.description,
    row: specSprite.row,
    scale: specSprite.scale,
    flipX: specSprite.flip_x,
    offsetX: specSprite.offset_x,
    offsetY: specSprite.offset_y,
    defaultClip: specSprite.default_clip,
    clips,
  };
}

export function mergeSpecOptions(
  options: CanvasHostOptions,
  spec: Record<string, any> | null,
): CanvasHostOptions {
  const resources = Array.isArray(spec?.resources)
    ? (spec?.resources as SpecResourceDef[])
    : [];
  const spritesByUidSpec = (spec?.sprites?.by_uid || {}) as Record<string, SpecSpriteDef>;
  const spritesByNameSpec = (spec?.sprites?.by_name || {}) as Record<
    string,
    SpecSpriteDef
  >;
  const spritesByTypeSpec = (spec?.sprites?.by_type || {}) as Record<
    string,
    SpecSpriteDef
  >;

  const assets: Record<string, string> = {};
  for (const resource of resources) {
    if (
      resource &&
      typeof resource.name === "string" &&
      typeof resource.path === "string"
    ) {
      assets[resource.name] = resource.path;
    }
  }

  const spritesByUid: Record<string, SpriteAnimationConfig> = {};
  for (const [uid, specSprite] of Object.entries(spritesByUidSpec)) {
    const parsed = toSpriteConfig(specSprite);
    if (parsed) {
      spritesByUid[uid] = parsed;
    }
  }

  const spritesByName: Record<string, SpriteAnimationConfig> = {};
  for (const [name, specSprite] of Object.entries(spritesByNameSpec)) {
    const parsed = toSpriteConfig(specSprite);
    if (parsed) {
      spritesByName[name] = parsed;
    }
  }

  const spritesByType: Record<string, SpriteAnimationConfig> = {};
  for (const [actorType, specSprite] of Object.entries(spritesByTypeSpec)) {
    const parsed = toSpriteConfig(specSprite);
    if (parsed) {
      spritesByType[actorType] = parsed;
    }
  }

  return {
    ...options,
    assets: {
      ...assets,
      ...(options.assets || {}),
    },
    spritesByUid: {
      ...spritesByUid,
      ...(options.spritesByUid || {}),
    },
    spritesByName: {
      ...spritesByName,
      ...(options.spritesByName || {}),
    },
    spritesByType: {
      ...spritesByType,
      ...(options.spritesByType || {}),
    },
  };
}

export class RuntimeCore {
  private readonly interpreter: NanoCaliburInterpreter;
  private readonly options: CanvasHostOptions;
  private readonly physics: PhysicsSystem;
  private readonly animation: AnimationSystem;

  constructor(
    interpreter: NanoCaliburInterpreter,
    options: CanvasHostOptions = {},
  ) {
    this.interpreter = interpreter;
    this.options = mergeSpecOptions(options, this.interpreter.getSpec());

    this.physics = new PhysicsSystem(this.options);
    this.animation = new AnimationSystem(this.options, (uid) =>
      this.physics.getBody(uid),
    );

    this.interpreter.setRuntimeHooks({
      playAnimation: (actor, clipName) => this.animation.play(actor, clipName),
      scene: {
        setGravityEnabled: (enabled) => this.physics.setGravityEnabled(enabled),
      },
    });

    const state = this.interpreter.getState();
    this.refreshMap(state);
    this.refreshScene(state);
    const actors = state.actors as ActorState[];
    this.applySpriteDefaultDimensions(actors);
    this.physics.syncBodiesFromActors(actors, false);
    this.physics.writeBodiesToActors(actors);
    this.animation.update(actors);
  }

  getInterpreter(): NanoCaliburInterpreter {
    return this.interpreter;
  }

  getOptions(): CanvasHostOptions {
    return this.options;
  }

  getAnimationSystem(): AnimationSystem {
    return this.animation;
  }

  getState(): InterpreterState {
    return this.interpreter.getState();
  }

  getMap(): MapSpec | null {
    return this.physics.getMap();
  }

  step(dtSeconds: number, input: RuntimeStepInput = {}): void {
    const beforeState = this.interpreter.getState();
    this.refreshMap(beforeState);
    this.refreshScene(beforeState);
    const beforeActors = beforeState.actors as ActorState[];
    this.applySpriteDefaultDimensions(beforeActors);

    this.physics.syncBodiesFromActors(beforeActors, false);
    this.physics.integrate(dtSeconds);
    this.physics.writeBodiesToActors(beforeActors);
    this.physics.resolvePostActionSolidCollisions();
    this.physics.writeBodiesToActors(beforeActors);

    const actorOverlaps = this.physics.detectCollisions(beforeActors);
    const contacts = this.physics.detectContacts(beforeActors);
    const tileOverlaps = this.physics.detectTileOverlaps(beforeActors);
    const actorsByUid = new Map(beforeActors.map((actor) => [actor.uid, actor] as const));
    const overlapFrameEvents: CollisionFrameInput[] = [
      ...actorOverlaps.map((pair) => ({ aUid: pair.aUid, bUid: pair.bUid })),
      ...tileOverlaps
        .map((item): CollisionFrameInput | null => {
          const actor = actorsByUid.get(item.actorUid);
          if (!actor) {
            return null;
          }
          return {
            a: actor,
            b: {
              uid: `__tile_${item.tileX}_${item.tileY}`,
              type: "Tile",
              tile_x: item.tileX,
              tile_y: item.tileY,
              block_mask: item.tileMask,
            },
          };
        })
        .filter((entry): entry is CollisionFrameInput => entry !== null),
    ];

    const frame: NanoCaliburFrameInput = {
      keyboard: input.keyboard,
      mouse: input.mouse,
      uiButtons: input.uiButtons,
      toolCalls: input.toolCalls,
      roleId:
        typeof input.roleId === "string"
          ? input.roleId
          : typeof input.role_id === "string"
            ? input.role_id
            : undefined,
      collisions: overlapFrameEvents,
      contacts: contacts.map((pair) => ({ aUid: pair.aUid, bUid: pair.bUid })),
    };

    this.interpreter.tick(frame);

    const afterState = this.interpreter.getState();
    this.refreshMap(afterState);
    this.refreshScene(afterState);
    const afterActors = afterState.actors as ActorState[];
    this.applySpriteDefaultDimensions(afterActors);

    this.physics.syncBodiesFromActors(afterActors, true);
    this.physics.resolvePostActionSolidCollisions();
    this.physics.writeBodiesToActors(afterActors);
    this.animation.update(afterActors);
  }

  private applySpriteDefaultDimensions(actors: ActorState[]): void {
    for (const actor of actors) {
      const sprite = this.resolveSpriteConfig(actor);
      if (!sprite) {
        continue;
      }
      const scale = Math.max(0.1, asNumber(sprite.scale, 1));
      if (typeof actor.w !== "number") {
        actor.w = sprite.frameWidth * scale;
      }
      if (typeof actor.h !== "number") {
        actor.h = sprite.frameHeight * scale;
      }
    }
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

  private refreshMap(state: InterpreterState): void {
    const mapSpec = (state.map as MapSpec | null) || null;
    this.physics.setMap(mapSpec);
  }

  private refreshScene(state: InterpreterState): void {
    const scene = (state.scene as SceneState | null) || null;
    this.physics.setGravityEnabled(Boolean(scene?.gravityEnabled));
  }
}
