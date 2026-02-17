export interface GameContext {
  globals: Record<string, any>;
  actors: any[];
  getActorByUid?: (uid: string) => any;
}


export function move_right(ctx: GameContext): void {
  let player = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a: any) => a?.uid === "hero"));
  player.x = (player.x + player.speed);
}

export function move_left(ctx: GameContext): void {
  let player = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a: any) => a?.uid === "hero"));
  player.x = (player.x - player.speed);
}

export function move_up(ctx: GameContext): void {
  let player = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a: any) => a?.uid === "hero"));
  player.y = (player.y - player.speed);
}

export function move_down(ctx: GameContext): void {
  let player = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a: any) => a?.uid === "hero"));
  player.y = (player.y + player.speed);
}

export function collect_coin(ctx: GameContext): void {
  let hero = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a: any) => a?.uid === "hero"));
  let coin = (ctx.getActorByUid ? ctx.getActorByUid("coin_1") : ctx.actors.find((a: any) => a?.uid === "coin_1"));
  let score = ctx.globals["score"];
  if (coin.active) {
    coin.active = false;
    score = (score + 1);
  }
  ctx.globals["score"] = score;
}