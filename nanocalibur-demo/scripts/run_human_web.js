#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');
const net = require('net');

const inviteToken = process.env.NC_INVITE_TOKEN || '';
const baseUrl = (process.env.NC_BASE_URL || 'http://127.0.0.1:7070').replace(/\/$/, '');
const webOnly = process.env.NC_WEB_ONLY === '1' || process.argv.includes('--web-only');
const cliArgs = process.argv.slice(2).filter((arg) => arg !== '--web-only');
const defaultPort = 9000;
const requestedPort = cliArgs[0] || process.env.NC_WEB_PORT || `${defaultPort}`;
const webHost = process.env.NC_WEB_HOST || '127.0.0.1';

if (!inviteToken && !webOnly) {
  console.error('NC_INVITE_TOKEN is required for human:play (unless NC_WEB_ONLY=1).');
  process.exit(1);
}

const isWin = process.platform === 'win32';
const webpackDevServer = path.resolve(
  __dirname,
  '..',
  'node_modules',
  '.bin',
  isWin ? 'webpack-dev-server.cmd' : 'webpack-dev-server',
);

const openPath = webOnly
  ? (process.env.NC_OPEN_PATH || '/')
  : `/?mode=session&baseUrl=${encodeURIComponent(baseUrl)}&inviteToken=${encodeURIComponent(inviteToken)}`;

function normalizePort(value) {
  const parsed = Number.parseInt(`${value}`, 10);
  if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 65535) {
    throw new Error(`Invalid web port "${value}"`);
  }
  return parsed;
}

function isPortFree(port, host) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', (error) => {
      if (error && error.code === 'EADDRINUSE') {
        resolve(false);
        return;
      }
      reject(error);
    });
    server.once('listening', () => {
      server.close(() => resolve(true));
    });
    server.listen(port, host);
  });
}

async function findAvailablePort(startPort, host, maxAttempts = 50) {
  for (let offset = 0; offset < maxAttempts; offset += 1) {
    const candidate = startPort + offset;
    // eslint-disable-next-line no-await-in-loop
    if (await isPortFree(candidate, host)) {
      return candidate;
    }
  }
  throw new Error(`No available port found from ${startPort} to ${startPort + maxAttempts - 1}`);
}

async function main() {
  const startPort = normalizePort(requestedPort);
  const port = await findAvailablePort(startPort, webHost);

  if (port !== startPort) {
    console.warn(`Requested web port ${startPort} is busy, using ${port} instead.`);
  }
  if (webOnly) {
    console.log(`Launching session web host at http://${webHost}:${port}${openPath}`);
  } else {
    console.log(`Launching browser client at http://${webHost}:${port}${openPath}`);
  }

  const child = spawn(
    webpackDevServer,
    [
      '--host',
      webHost,
      '--port',
      `${port}`,
      '--allowed-hosts',
      'all',
      '--open',
      openPath,
    ],
    {
      cwd: path.resolve(__dirname, '..'),
      stdio: 'inherit',
      env: {
        ...process.env,
        WATCHPACK_POLLING: process.env.WATCHPACK_POLLING || 'true',
        BROWSER: process.env.BROWSER || 'default',
      },
    },
  );

  child.on('exit', (code) => {
    process.exit(code || 0);
  });
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
