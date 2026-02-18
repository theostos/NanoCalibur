export interface RuntimeSceneContext {
  gravityEnabled?: boolean;
  setGravityEnabled?: (enabled: boolean) => void;
  spawnActor?: (actorType: string, uid: string, fields?: Record<string, any>) => any;
}

export interface GameContext {
  globals: Record<string, any>;
  actors: any[];
  tick: number;
  getActorByUid?: (uid: string) => any;
  playAnimation?: (actor: any, clipName: string) => void;
  destroyActor?: (actor: any) => void;
  scene?: RuntimeSceneContext;
}

const __NC_DEFAULT_RANDOM_ALPHABET =
  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

function __nc_random_int(minInclusive: number, maxInclusive: number): number {
  const lo = Math.ceil(Math.min(minInclusive, maxInclusive));
  const hi = Math.floor(Math.max(minInclusive, maxInclusive));
  return Math.floor(Math.random() * (hi - lo + 1)) + lo;
}

function __nc_random_bool(): boolean {
  return Math.random() < 0.5;
}

function __nc_random_string(length: number, alphabet: string = __NC_DEFAULT_RANDOM_ALPHABET): string {
  const size = Math.max(0, Math.floor(length));
  if (alphabet.length === 0) {
    return "";
  }
  let out = "";
  for (let i = 0; i < size; i += 1) {
    const idx = Math.floor(Math.random() * alphabet.length);
    out += alphabet[idx];
  }
  return out;
}

function __nc_random_float_uniform(minValue: number, maxValue: number): number {
  const lo = Math.min(minValue, maxValue);
  const hi = Math.max(minValue, maxValue);
  return lo + Math.random() * (hi - lo);
}

function __nc_random_float_normal(mean: number, stddev: number): number {
  // Box-Muller transform.
  let u = 0;
  let v = 0;
  while (u === 0) {
    u = Math.random();
  }
  while (v === 0) {
    v = Math.random();
  }
  const z = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  return mean + z * stddev;
}


export function move_right(ctx: GameContext): void {
  let player = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a: any) => a?.uid === "hero"));
  player.x = (player.x + player.speed);
  if (ctx.playAnimation) {
    ctx.playAnimation(player, "run");
  }
}

export function move_left(ctx: GameContext): void {
  let player = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a: any) => a?.uid === "hero"));
  player.x = (player.x - player.speed);
  if (ctx.playAnimation) {
    ctx.playAnimation(player, "run");
  }
}

export function move_up(ctx: GameContext): void {
  let player = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a: any) => a?.uid === "hero"));
  player.y = (player.y - player.speed);
  if (ctx.playAnimation) {
    ctx.playAnimation(player, "run");
  }
}

export function move_down(ctx: GameContext): void {
  let player = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a: any) => a?.uid === "hero"));
  player.y = (player.y + player.speed);
  if (ctx.playAnimation) {
    ctx.playAnimation(player, "run");
  }
}

export function idle(ctx: GameContext): void {
  let player = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a: any) => a?.uid === "hero"));
  if (ctx.playAnimation) {
    ctx.playAnimation(player, "idle");
  }
}

export function collect_coin(ctx: GameContext): void {
  let hero = (ctx.getActorByUid ? ctx.getActorByUid("__nanocalibur_collision_left__") : ctx.actors.find((a: any) => a?.uid === "__nanocalibur_collision_left__"));
  let coin = (ctx.getActorByUid ? ctx.getActorByUid("__nanocalibur_collision_right__") : ctx.actors.find((a: any) => a?.uid === "__nanocalibur_collision_right__"));
  let score = ctx.globals["score"];
  if ((coin.active && (coin.uid != "coin_pet"))) {
    if (ctx.destroyActor) {
      ctx.destroyActor(coin);
    } else {
      coin.active = false;
    }
    score = (score + 1);
  }
  ctx.globals["score"] = score;
}

export function enable_gravity(ctx: GameContext): void {
  let scene = ctx.scene;
  if (ctx.scene && ctx.scene.setGravityEnabled) {
    ctx.scene.setGravityEnabled(Boolean(true));
  }
}

export function disable_gravity(ctx: GameContext): void {
  let scene = ctx.scene;
  if (ctx.scene && ctx.scene.setGravityEnabled) {
    ctx.scene.setGravityEnabled(Boolean(false));
  }
}

export function* spawn_bonus(ctx: GameContext): Generator<number, void, unknown> {
  let scene = ctx.scene;
  let tick = ctx.tick;
  const __actors_last_coin = ctx.actors.filter((a: any) => a?.type === "Coin");
  let last_coin = __actors_last_coin[__actors_last_coin.length + (-1)];
  const __step__ = 1;
  for (let _ = 0; __step__ >= 0 ? _ < 20 : _ > 20; _ += __step__) {
    yield tick;
  }
  if (ctx.scene && ctx.scene.spawnActor) {
    ctx.scene.spawnActor("Coin", "", { "x": (last_coin.x + 32), "y": 224, "active": true, "sprite": "coin" });
  }
}