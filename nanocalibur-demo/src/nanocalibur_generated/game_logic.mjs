export function move_right(ctx) {
  let player = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a) => a?.uid === "hero"));
  player.x = (player.x + player.speed);
}

export function move_left(ctx) {
  let player = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a) => a?.uid === "hero"));
  player.x = (player.x - player.speed);
}

export function move_up(ctx) {
  let player = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a) => a?.uid === "hero"));
  player.y = (player.y - player.speed);
}

export function move_down(ctx) {
  let player = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a) => a?.uid === "hero"));
  player.y = (player.y + player.speed);
}

export function collect_coin(ctx) {
  let hero = (ctx.getActorByUid ? ctx.getActorByUid("hero") : ctx.actors.find((a) => a?.uid === "hero"));
  let coin = (ctx.getActorByUid ? ctx.getActorByUid("coin_1") : ctx.actors.find((a) => a?.uid === "coin_1"));
  let score = ctx.globals["score"];
  if (coin.active) {
    coin.active = false;
    score = (score + 1);
  }
  ctx.globals["score"] = score;
}