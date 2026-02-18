import {
  ActorState,
  AnimationRuntime,
  CanvasHostOptions,
  DEFAULT_TICKS_PER_FRAME,
  MOVEMENT_SPEED_THRESHOLD,
  PhysicsBodyRuntime,
  SpriteAnimationConfig,
  SpriteFrameInfo,
} from "./types";
import { asNumber, clamp } from "./utils";

export class AnimationSystem {
  private readonly options: CanvasHostOptions;
  private readonly getBodyByUid: (uid: string) => PhysicsBodyRuntime | undefined;
  private readonly animations = new Map<string, AnimationRuntime>();
  private readonly clipOverrides = new Map<string, string>();

  constructor(
    options: CanvasHostOptions,
    getBodyByUid: (uid: string) => PhysicsBodyRuntime | undefined,
  ) {
    this.options = options;
    this.getBodyByUid = getBodyByUid;
  }

  play(
    actorOrUid: ActorState | Record<string, any> | string,
    clipName: string,
  ): void {
    const uid = typeof actorOrUid === "string" ? actorOrUid : actorOrUid?.uid;
    if (typeof uid !== "string" || !uid) {
      return;
    }
    this.clipOverrides.set(uid, clipName);
  }

  update(actors: ActorState[]): void {
    const alive = new Set<string>();

    for (const actor of actors) {
      const sprite = this.resolveSpriteConfig(actor);
      if (!sprite) {
        continue;
      }

      alive.add(actor.uid);
      const body = this.getBodyByUid(actor.uid);
      const preferredClip = this.clipOverrides.get(actor.uid);
      const selectedClip = this.selectClipName(sprite, body, preferredClip);
      const clip = this.resolveClip(sprite, selectedClip);
      if (!clip || clip.clip.frames.length === 0) {
        continue;
      }

      let runtime = this.animations.get(actor.uid);
      if (!runtime) {
        runtime = {
          clipName: clip.name,
          frameCursor: 0,
          ticksInFrame: 0,
          facing: 1,
        };
        this.animations.set(actor.uid, runtime);
      }

      if (runtime.clipName !== clip.name) {
        runtime.clipName = clip.name;
        runtime.frameCursor = 0;
        runtime.ticksInFrame = 0;
      }

      if (body) {
        if (body.vx > MOVEMENT_SPEED_THRESHOLD) {
          runtime.facing = 1;
        } else if (body.vx < -MOVEMENT_SPEED_THRESHOLD) {
          runtime.facing = -1;
        }
      }

      runtime.ticksInFrame += 1;
      const ticksPerFrame = Math.max(
        1,
        asNumber(clip.clip.ticksPerFrame, DEFAULT_TICKS_PER_FRAME),
      );
      if (runtime.ticksInFrame >= ticksPerFrame) {
        runtime.ticksInFrame = 0;
        if (runtime.frameCursor < clip.clip.frames.length - 1) {
          runtime.frameCursor += 1;
        } else if (clip.clip.loop !== false) {
          runtime.frameCursor = 0;
        }
      }
    }

    for (const uid of this.animations.keys()) {
      if (!alive.has(uid)) {
        this.animations.delete(uid);
      }
    }
    for (const uid of this.clipOverrides.keys()) {
      if (!alive.has(uid)) {
        this.clipOverrides.delete(uid);
      }
    }
  }

  getFrameInfo(actor: ActorState): SpriteFrameInfo | null {
    const sprite = this.resolveSpriteConfig(actor);
    if (!sprite) {
      return null;
    }

    const runtime = this.animations.get(actor.uid);
    if (!runtime) {
      return null;
    }

    const clip = this.resolveClip(sprite, runtime.clipName);
    if (!clip || clip.clip.frames.length === 0) {
      return null;
    }

    const frameIndex = clip.clip.frames[
      clamp(runtime.frameCursor, 0, clip.clip.frames.length - 1)
    ];
    return {
      sprite,
      frameIndex,
      facing: runtime.facing,
    };
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

  private selectClipName(
    sprite: SpriteAnimationConfig,
    body: PhysicsBodyRuntime | undefined,
    preferredClip: string | undefined,
  ): string {
    if (preferredClip && sprite.clips[preferredClip]) {
      return preferredClip;
    }

    if (body && body.config.dynamic) {
      if (!body.onGround && sprite.clips.jump && body.vy < 0) {
        return "jump";
      }
      if (!body.onGround && sprite.clips.fall && body.vy >= 0) {
        return "fall";
      }
      if (Math.abs(body.vx) > MOVEMENT_SPEED_THRESHOLD && sprite.clips.run) {
        return "run";
      }
      if (sprite.clips.idle) {
        return "idle";
      }
    }

    if (sprite.defaultClip && sprite.clips[sprite.defaultClip]) {
      return sprite.defaultClip;
    }

    const first = Object.keys(sprite.clips)[0];
    return first || "idle";
  }

  private resolveClip(
    sprite: SpriteAnimationConfig,
    clipName: string,
  ): { name: string; clip: { frames: number[]; ticksPerFrame?: number; loop?: boolean } } | null {
    if (sprite.clips[clipName]) {
      return { name: clipName, clip: sprite.clips[clipName] };
    }
    if (sprite.defaultClip && sprite.clips[sprite.defaultClip]) {
      return { name: sprite.defaultClip, clip: sprite.clips[sprite.defaultClip] };
    }
    const entries = Object.entries(sprite.clips);
    if (entries.length === 0) {
      return null;
    }
    return { name: entries[0][0], clip: entries[0][1] };
  }
}
