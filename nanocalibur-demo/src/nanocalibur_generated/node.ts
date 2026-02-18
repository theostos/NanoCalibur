import { createNanoCaliburHeadless, createNanoCaliburInterpreter } from './index';
import { HeadlessHttpServer, HeadlessHttpServerOptions } from './headless_http_server';

export function createNanoCaliburHttpServerNode(options: Record<string, any> = {}): HeadlessHttpServer {
  const host = createNanoCaliburHeadless(options);
  return new HeadlessHttpServer(host);
}

export type { HeadlessHttpServerOptions };
export { HeadlessHttpServer, createNanoCaliburHeadless, createNanoCaliburInterpreter };
