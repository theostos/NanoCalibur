export type ActorState = Record<string, any> & {
  uid: string;
  type: string;
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  z?: number;
  block_mask?: number | null;
  vx?: number;
  vy?: number;
  onGround?: boolean;
  active?: boolean;
  parent?: string;
  sprite?: string;
};

export interface MapSpec {
  width: number;
  height: number;
  tile_size: number;
  tile_grid: number[][];
  tile_defs?: Record<
    string,
    {
      block_mask?: number | null;
      sprite?: string | null;
      color?: {
        r: number;
        g: number;
        b: number;
        symbol?: string | null;
        description?: string | null;
      } | null;
    }
  >;
}

export interface CameraState {
  name?: string;
  role_id?: string;
  x?: number;
  y?: number;
  width?: number | null;
  height?: number | null;
  target_uid?: string;
  offset_x?: number;
  offset_y?: number;
}

export interface SceneState {
  gravityEnabled?: boolean;
}

export interface PhasePayload {
  begin: string[];
  on: string[];
  end: string[];
}

export interface CollisionPair {
  aUid: string;
  bUid: string;
}

export interface AnimationClipConfig {
  frames: number[];
  ticksPerFrame?: number;
  loop?: boolean;
}

export interface SpriteAnimationConfig {
  image: string;
  frameWidth: number;
  frameHeight: number;
  symbol?: string;
  description?: string;
  row?: number;
  scale?: number;
  flipX?: boolean;
  offsetX?: number;
  offsetY?: number;
  defaultClip?: string;
  clips: Record<string, AnimationClipConfig>;
}

export interface PhysicsBodyConfig {
  enabled?: boolean;
  dynamic?: boolean;
  collidable?: boolean;
}

export interface CanvasHostOptions {
  width?: number;
  height?: number;
  backgroundColor?: string;
  tileColor?: string;
  pixelated?: boolean;
  fixedStepMs?: number;
  maxSubSteps?: number;
  showHud?: boolean;
  showDebugColliders?: boolean;
  defaultActorColor?: string;
  actorColorsByType?: Record<string, string>;
  actorColorsByUid?: Record<string, string>;
  assets?: Record<string, string>;
  spritesByType?: Record<string, SpriteAnimationConfig>;
  spritesByUid?: Record<string, SpriteAnimationConfig>;
  spritesByName?: Record<string, SpriteAnimationConfig>;
  physics?: {
    gravity?: number;
    defaultBody?: PhysicsBodyConfig;
    bodiesByType?: Record<string, PhysicsBodyConfig>;
    bodiesByUid?: Record<string, PhysicsBodyConfig>;
  };
  symbolic?: {
    emptySymbol?: string;
    tileSymbol?: string;
    fallbackSymbol?: string;
    maxWidth?: number;
    maxHeight?: number;
    cropWidth?: number;
    cropHeight?: number;
  };
}

export interface SpecResourceDef {
  name: string;
  path: string;
}

export interface SpecSpriteDef {
  resource: string;
  frame_width: number;
  frame_height: number;
  symbol?: string;
  description?: string;
  row?: number;
  scale?: number;
  flip_x?: boolean;
  offset_x?: number;
  offset_y?: number;
  default_clip?: string;
  clips?: Record<
    string,
    {
      frames?: number[];
      ticks_per_frame?: number;
      loop?: boolean;
    }
  >;
}

export interface ResolvedBodyConfig {
  enabled: boolean;
  dynamic: boolean;
  collidable: boolean;
}

export interface PhysicsBodyRuntime {
  uid: string;
  x: number;
  y: number;
  w: number;
  h: number;
  blockMask: number | null;
  vx: number;
  vy: number;
  onGround: boolean;
  active: boolean;
  prevX: number;
  prevY: number;
  config: ResolvedBodyConfig;
}

export interface AnimationRuntime {
  clipName: string;
  frameCursor: number;
  ticksInFrame: number;
  facing: 1 | -1;
}

export interface WorldCamera {
  x: number;
  y: number;
}

export interface SpriteFrameInfo {
  sprite: SpriteAnimationConfig;
  frameIndex: number;
  facing: 1 | -1;
}

export interface SymbolicLegendItem {
  symbol: string;
  description: string;
}

export interface SymbolicFrame {
  width: number;
  height: number;
  rows: string[];
  legend: SymbolicLegendItem[];
}

export const EPSILON = 0.001;
export const DEFAULT_WIDTH = 960;
export const DEFAULT_HEIGHT = 540;
export const DEFAULT_FIXED_STEP_MS = 1000 / 60;
export const DEFAULT_MAX_SUB_STEPS = 6;
export const DEFAULT_TICKS_PER_FRAME = 8;
export const MOVEMENT_SPEED_THRESHOLD = 8;

export const DEFAULT_TYPE_COLORS: Record<string, string> = {
  Player: "#4db7ff",
  Enemy: "#ec6f66",
  Coin: "#ffd86b",
};
