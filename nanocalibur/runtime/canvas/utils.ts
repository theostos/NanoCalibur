import { ActorState, PhasePayload } from "./types";

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function moveToward(value: number, target: number, maxDelta: number): number {
  if (value < target) {
    return Math.min(value + maxDelta, target);
  }
  if (value > target) {
    return Math.max(value - maxDelta, target);
  }
  return value;
}

export function asNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function diffSets(current: Set<string>, previous: Set<string>): PhasePayload {
  const begin: string[] = [];
  const on: string[] = [];
  const end: string[] = [];

  for (const item of current) {
    on.push(item);
    if (!previous.has(item)) {
      begin.push(item);
    }
  }

  for (const item of previous) {
    if (!current.has(item)) {
      end.push(item);
    }
  }

  return { begin, on, end };
}

export function mapMouseButton(buttonCode: number): string {
  if (buttonCode === 0) return "left";
  if (buttonCode === 1) return "middle";
  if (buttonCode === 2) return "right";
  return `button_${buttonCode}`;
}

export function actorCenterX(actor: ActorState): number {
  return asNumber(actor.x, 0);
}

export function actorCenterY(actor: ActorState): number {
  return asNumber(actor.y, 0);
}

export function actorWidth(actor: ActorState): number {
  return Math.max(1, asNumber(actor.w, 24));
}

export function actorHeight(actor: ActorState): number {
  return Math.max(1, asNumber(actor.h, 24));
}

export function overlapsActors(a: ActorState, b: ActorState): boolean {
  const aw = actorWidth(a);
  const ah = actorHeight(a);
  const bw = actorWidth(b);
  const bh = actorHeight(b);

  const aLeft = actorCenterX(a) - aw / 2;
  const aRight = actorCenterX(a) + aw / 2;
  const aTop = actorCenterY(a) - ah / 2;
  const aBottom = actorCenterY(a) + ah / 2;

  const bLeft = actorCenterX(b) - bw / 2;
  const bRight = actorCenterX(b) + bw / 2;
  const bTop = actorCenterY(b) - bh / 2;
  const bBottom = actorCenterY(b) + bh / 2;

  return aLeft < bRight && aRight > bLeft && aTop < bBottom && aBottom > bTop;
}
