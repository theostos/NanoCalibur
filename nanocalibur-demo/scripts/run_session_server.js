#!/usr/bin/env node

const path = require('path');

const COMPILED_DIR = path.resolve(__dirname, '..', '.nanocalibur_headless');

const { createNanoCaliburHeadless } = require(path.join(COMPILED_DIR, 'index.js'));
const { HeadlessHttpServer } = require(path.join(COMPILED_DIR, 'headless_http_server.js'));
const { SessionManager } = require(path.join(COMPILED_DIR, 'session_manager.js'));

const host = process.env.NC_HOST || '127.0.0.1';
const requestedPort = Number(process.env.NC_PORT || '7070');

function createHost() {
  return createNanoCaliburHeadless();
}

async function main() {
  const manager = new SessionManager();
  const server = new HeadlessHttpServer(createHost(), manager, createHost);

  const port = await server.start({
    host,
    port: Number.isFinite(requestedPort) ? requestedPort : 7070,
  });

  const baseUrl = `http://${host}:${port}`;
  console.log(`[nanocalibur] session server started at ${baseUrl}`);
  console.log('[nanocalibur] create a session: POST /sessions');
  console.log('[nanocalibur] join with invite: POST /join');

  const shutdown = async () => {
    try {
      await server.stop();
    } finally {
      process.exit(0);
    }
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

main().catch((error) => {
  console.error('[nanocalibur] failed to start session server:', error);
  process.exit(1);
});
