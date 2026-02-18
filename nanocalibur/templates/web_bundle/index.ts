import * as gameLogic from './game_logic';
import {
  CanvasHost,
  CanvasHostOptions,
  HeadlessHost,
  NanoCaliburMCPServer,
} from './bridge';
import { NanoCaliburInterpreter } from './interpreter';

type Callable = (...args: any[]) => any;

declare const require: any;

const spec = require('./game_spec.json') as Record<string, any>;

function pickFunctions(names: string[]): Record<string, Callable> {
  const out: Record<string, Callable> = {};
  const moduleObj = gameLogic as Record<string, unknown>;

  for (const name of names) {
    const fn = moduleObj[name];
    if (typeof fn === 'function') {
      out[name] = fn as Callable;
    }
  }
  return out;
}

export function createNanoCaliburInterpreter(): NanoCaliburInterpreter {
  const actionNames = Array.isArray(spec.actions) ? (spec.actions as string[]) : [];
  const predicateNames = Array.isArray(spec.predicates)
    ? spec.predicates.map((item: any) => (typeof item === 'string' ? item : item.name))
    : [];

  const actions = pickFunctions(actionNames);
  const predicates = pickFunctions(predicateNames);
  return new NanoCaliburInterpreter(spec, actions, predicates);
}

export function attachNanoCalibur(
  canvas: HTMLCanvasElement,
  options: CanvasHostOptions = {},
): CanvasHost {
  const interpreter = createNanoCaliburInterpreter();
  return new CanvasHost(canvas, interpreter, options);
}

export async function startNanoCalibur(
  canvas: HTMLCanvasElement,
  options: CanvasHostOptions = {},
): Promise<CanvasHost> {
  const host = attachNanoCalibur(canvas, options);
  await host.start();
  return host;
}

export function createNanoCaliburHeadless(
  options: CanvasHostOptions = {},
): HeadlessHost {
  const interpreter = createNanoCaliburInterpreter();
  return new HeadlessHost(interpreter, options);
}

export function createNanoCaliburMCPServer(
  options: CanvasHostOptions = {},
): NanoCaliburMCPServer {
  const host = createNanoCaliburHeadless(options);
  return new NanoCaliburMCPServer(host);
}

export type {
  CanvasHostOptions,
  PhysicsBodyConfig,
  SpriteAnimationConfig,
  SymbolicFrame,
} from './bridge';
export {
  CanvasHost,
  HeadlessHost,
  NanoCaliburInterpreter,
  NanoCaliburMCPServer,
};
