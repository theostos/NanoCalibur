#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');

const inviteToken = process.env.NC_INVITE_TOKEN || '';
const baseUrl = (process.env.NC_BASE_URL || 'http://127.0.0.1:7070').replace(/\/$/, '');

if (!inviteToken) {
  console.error('NC_INVITE_TOKEN is required for human:play.');
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

const openPath = `/?mode=session&baseUrl=${encodeURIComponent(baseUrl)}&inviteToken=${encodeURIComponent(inviteToken)}`;

const child = spawn(
  webpackDevServer,
  ['--open', openPath],
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
