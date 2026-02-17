import * as ex from 'excalibur';
import * as gameLogic from './game_logic';
import { NanoCaliburInterpreter } from './interpreter';
import { NanoCaliburBridge } from './bridge';

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

export function attachNanoCalibur(scene: ex.Scene): NanoCaliburBridge {
  const interpreter = createNanoCaliburInterpreter();
  return new NanoCaliburBridge(scene, interpreter);
}

export { NanoCaliburBridge, NanoCaliburInterpreter };
