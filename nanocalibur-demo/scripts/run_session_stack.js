#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');

const projectDir = path.resolve(__dirname, '..');
const isWin = process.platform === 'win32';
const npmCmd = isWin ? 'npm.cmd' : 'npm';
const nodeCmd = process.execPath;

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function parseJsonSafely(raw) {
  if (!raw) {
    return {};
  }
  try {
    return JSON.parse(raw);
  } catch (_error) {
    return {};
  }
}

async function requestJson(baseUrl, route, method, payload, headers = {}) {
  const response = await fetch(`${baseUrl}${route}`, {
    method,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...headers,
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const text = await response.text();
  const decoded = parseJsonSafely(text);
  if (!response.ok) {
    const message = decoded && decoded.error
      ? decoded.error
      : `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return decoded;
}

function attachPrefixedOutput(stream, prefix, target, onLine) {
  let buffer = '';
  stream.on('data', (chunk) => {
    buffer += String(chunk);
    while (true) {
      const idx = buffer.indexOf('\n');
      if (idx < 0) {
        break;
      }
      const line = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 1);
      target.write(`${prefix}${line}\n`);
      if (onLine) {
        onLine(line);
      }
    }
  });
  stream.on('end', () => {
    if (!buffer) {
      return;
    }
    target.write(`${prefix}${buffer}\n`);
    if (onLine) {
      onLine(buffer);
    }
  });
}

function pickInvite(invites, preferredKinds, excludedRoleIds = new Set()) {
  for (const kind of preferredKinds) {
    const match = invites.find((entry) => (
      entry
      && typeof entry.role_id === 'string'
      && !excludedRoleIds.has(entry.role_id)
      && entry.role_kind === kind
    ));
    if (match) {
      return match;
    }
  }
  return invites.find((entry) => (
    entry
    && typeof entry.role_id === 'string'
    && !excludedRoleIds.has(entry.role_id)
  )) || null;
}

async function waitForRequiredRolesConnected(baseUrl, sessionId, timeoutMs = 60_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const payload = await requestJson(baseUrl, '/sessions', 'GET');
    const sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
    const session = sessions.find((entry) => entry && entry.session_id === sessionId);
    if (session && Array.isArray(session.roles)) {
      const requiredRoles = session.roles.filter((entry) => entry && entry.required !== false);
      const allConnected = requiredRoles.every((entry) => entry.connected === true);
      if (allConnected) {
        return;
      }
    }
    await delay(250);
  }
  throw new Error(
    `Timed out waiting for required roles to connect for session '${sessionId}'.`,
  );
}

async function startSessionServer() {
  return new Promise((resolve, reject) => {
    const child = spawn(npmCmd, ['run', 'headless:server'], {
      cwd: projectDir,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: process.env,
    });

    let settled = false;
    let startedBaseUrl = null;

    attachPrefixedOutput(child.stdout, '[server] ', process.stdout, (line) => {
      const match = line.match(/session server started at (\S+)/);
      if (match) {
        startedBaseUrl = match[1];
        if (!settled) {
          settled = true;
          resolve({ child, baseUrl: startedBaseUrl });
        }
      }
    });
    attachPrefixedOutput(child.stderr, '[server] ', process.stderr);

    child.on('error', (error) => {
      if (!settled) {
        settled = true;
        reject(error);
      }
    });

    child.on('exit', (code, signal) => {
      if (!settled) {
        settled = true;
        const reason = signal ? `signal ${signal}` : `code ${code}`;
        reject(new Error(`headless server exited before startup (${reason}).`));
      }
    });
  });
}

function launchClient(label, args, envExtras) {
  const child = spawn(nodeCmd, args, {
    cwd: projectDir,
    stdio: 'inherit',
    env: {
      ...process.env,
      ...envExtras,
    },
  });

  child.on('exit', (code, signal) => {
    const reason = signal ? `signal ${signal}` : `code ${code}`;
    console.log(`[stack] ${label} exited (${reason}).`);
  });
  return child;
}

async function main() {
  const requestedWebPort = process.argv[2] || process.env.NC_WEB_PORT || '';
  const children = [];

  const shutdown = () => {
    for (const child of children) {
      if (child && !child.killed) {
        child.kill('SIGINT');
      }
    }
  };

  process.on('SIGINT', () => {
    shutdown();
    process.exit(0);
  });
  process.on('SIGTERM', () => {
    shutdown();
    process.exit(0);
  });

  const { child: serverChild, baseUrl } = await startSessionServer();
  children.push(serverChild);

  const created = await requestJson(baseUrl, '/sessions', 'POST', {});
  const sessionId = created.session_id;
  const adminToken = created.admin_token;
  const invites = Array.isArray(created.invites) ? created.invites : [];
  if (!sessionId || !adminToken || invites.length === 0) {
    throw new Error('Invalid session creation response from server.');
  }

  const usedRoleIds = new Set();
  const humanInvite = process.env.NC_HUMAN_INVITE_TOKEN
    ? { invite_token: process.env.NC_HUMAN_INVITE_TOKEN, role_id: 'human_manual' }
    : pickInvite(invites, ['human', 'hybrid'], usedRoleIds);
  if (!humanInvite || !humanInvite.invite_token) {
    throw new Error('Could not resolve invite token for a human role.');
  }
  if (humanInvite.role_id) {
    usedRoleIds.add(humanInvite.role_id);
  }

  const dummyInvite = process.env.NC_DUMMY_INVITE_TOKEN
    ? { invite_token: process.env.NC_DUMMY_INVITE_TOKEN, role_id: 'dummy_manual' }
    : pickInvite(invites, ['ai', 'hybrid'], usedRoleIds);
  if (!dummyInvite || !dummyInvite.invite_token) {
    throw new Error('Could not resolve invite token for a dummy/AI role.');
  }
  if (dummyInvite.role_id) {
    usedRoleIds.add(dummyInvite.role_id);
  }

  const dummyChild = launchClient(
    'dummy:random',
    ['scripts/dummy_random_client.js'],
    {
      NC_BASE_URL: baseUrl,
      NC_INVITE_TOKEN: dummyInvite.invite_token,
      NC_INTERVAL_MS: process.env.NC_INTERVAL_MS || '400',
    },
  );
  children.push(dummyChild);

  const humanArgs = ['scripts/run_human_web.js'];
  if (requestedWebPort) {
    humanArgs.push(String(requestedWebPort));
  }
  const humanChild = launchClient(
    'human:play',
    humanArgs,
    {
      NC_BASE_URL: baseUrl,
      NC_INVITE_TOKEN: humanInvite.invite_token,
    },
  );
  children.push(humanChild);

  await waitForRequiredRolesConnected(baseUrl, sessionId);
  await requestJson(
    baseUrl,
    `/sessions/${encodeURIComponent(sessionId)}/start`,
    'POST',
    { admin_token: adminToken },
  );

  console.log(`[stack] session started: ${sessionId}`);
  console.log(`[stack] loop mode: ${created.loop_mode}, tick rate: ${created.tick_rate}`);
  console.log(`[stack] human role: ${humanInvite.role_id || 'n/a'}`);
  console.log(`[stack] dummy role: ${dummyInvite.role_id || 'n/a'}`);
  console.log(`[stack] press Ctrl+C to stop server and clients.`);

  await new Promise(() => {});
}

main().catch((error) => {
  console.error('[stack] failed:', error.message || error);
  process.exit(1);
});
