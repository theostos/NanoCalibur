#!/usr/bin/env node

const { spawn } = require('child_process');
const fs = require('fs');
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

function trimTrailingSlash(value) {
  if (typeof value !== 'string') {
    return '';
  }
  return value.trim().replace(/\/$/, '');
}

function normalizeUrlOrigin(value, fallback = '') {
  const candidate = trimTrailingSlash(value || fallback);
  if (!candidate) {
    return '';
  }
  try {
    return new URL(candidate).origin;
  } catch (_error) {
    return candidate;
  }
}

function normalizeUrlBase(value, fallback = '') {
  const candidate = trimTrailingSlash(value || fallback);
  if (!candidate) {
    return '';
  }
  try {
    const parsed = new URL(candidate);
    const normalizedPath = parsed.pathname === '/' ? '' : parsed.pathname.replace(/\/$/, '');
    return `${parsed.origin}${normalizedPath}`;
  } catch (_error) {
    return candidate;
  }
}

function isLocalhostUrl(value) {
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.toLowerCase();
    return host === '127.0.0.1' || host === 'localhost' || host === '::1' || host === '0.0.0.0';
  } catch (_error) {
    return false;
  }
}

function toPositiveIntOrDefault(rawValue, fallbackValue) {
  const parsed = Number.parseInt(`${rawValue}`, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallbackValue;
  }
  return parsed;
}

function toOptionalTimeoutMs(rawValue) {
  const parsed = Number.parseInt(`${rawValue}`, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
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

function ensureParentDir(filePath) {
  const parent = path.dirname(filePath);
  fs.mkdirSync(parent, { recursive: true });
}

function timestamp() {
  return new Date().toISOString();
}

function attachOutputToLog(stream, label, logStream) {
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
      logStream.write(`[${timestamp()}] [${label}] ${line}\n`);
    }
  });
  stream.on('end', () => {
    if (!buffer) {
      return;
    }
    logStream.write(`[${timestamp()}] [${label}] ${buffer}\n`);
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

function humanShareInvites(invites) {
  return invites
    .filter((entry) => (
      entry
      && typeof entry.role_id === 'string'
      && (entry.role_kind === 'human' || entry.role_kind === 'hybrid')
      && typeof entry.invite_token === 'string'
      && entry.invite_token.length > 0
    ))
    .sort((a, b) => a.role_id.localeCompare(b.role_id, undefined, { numeric: true }));
}

function buildSessionShareUrl(webBaseUrl, apiBaseUrl, inviteToken) {
  const normalizedWebBase = trimTrailingSlash(webBaseUrl);
  return `${normalizedWebBase}/?mode=session&baseUrl=${encodeURIComponent(apiBaseUrl)}&inviteToken=${encodeURIComponent(inviteToken)}`;
}

async function waitForRequiredRolesConnected(baseUrl, sessionId, timeoutMs) {
  const startedAt = Date.now();
  let lastPrintedSignature = '';
  let lastPendingRoles = [];

  while (true) {
    const payload = await requestJson(baseUrl, '/sessions', 'GET');
    const sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
    const session = sessions.find((entry) => entry && entry.session_id === sessionId);
    if (session && Array.isArray(session.roles)) {
      const requiredRoles = session.roles.filter((entry) => entry && entry.required !== false);
      const pending = requiredRoles
        .filter((entry) => entry.connected !== true)
        .map((entry) => entry.role_id)
        .filter((roleId) => typeof roleId === 'string');
      lastPendingRoles = pending;
      if (pending.length === 0) {
        return;
      }
      const signature = pending.join(',');
      if (signature !== lastPrintedSignature) {
        lastPrintedSignature = signature;
        console.log(`[stack] waiting for required roles: ${pending.join(', ')}`);
      }
    }

    if (typeof timeoutMs === 'number' && timeoutMs > 0 && Date.now() - startedAt >= timeoutMs) {
      throw new Error(
        `Timed out waiting for required roles to connect for session '${sessionId}'. `
        + `Still missing: ${lastPendingRoles.join(', ') || 'unknown'}.`,
      );
    }
    await delay(500);
  }
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
        startedBaseUrl = trimTrailingSlash(match[1]);
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

async function startWebHost(requestedWebPort, envExtras = {}) {
  return new Promise((resolve, reject) => {
    const args = ['scripts/run_human_web.js', '--web-only'];
    if (requestedWebPort) {
      args.push(String(requestedWebPort));
    }
    const child = spawn(nodeCmd, args, {
      cwd: projectDir,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        ...envExtras,
        NC_WEB_ONLY: '1',
        BROWSER: process.env.BROWSER || 'none',
      },
    });

    let settled = false;

    attachPrefixedOutput(child.stdout, '[web] ', process.stdout, (line) => {
      const match = line.match(/Launching (?:session web host|browser client) at (\S+)/);
      if (!match || settled) {
        return;
      }
      settled = true;
      const launchedUrl = trimTrailingSlash(match[1]);
      const webUrl = normalizeUrlOrigin(launchedUrl);
      resolve({ child, webUrl });
    });
    attachPrefixedOutput(child.stderr, '[web] ', process.stderr);

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
        reject(new Error(`web host exited before startup (${reason}).`));
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

function launchClientToLog(label, args, envExtras, logPath) {
  ensureParentDir(logPath);
  const logStream = fs.createWriteStream(logPath, { flags: 'a' });
  logStream.write(`[${timestamp()}] [${label}] start\n`);

  const child = spawn(nodeCmd, args, {
    cwd: projectDir,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      ...envExtras,
    },
  });

  attachOutputToLog(child.stdout, `${label}:stdout`, logStream);
  attachOutputToLog(child.stderr, `${label}:stderr`, logStream);

  child.on('error', (error) => {
    logStream.write(`[${timestamp()}] [${label}] error: ${error.message || String(error)}\n`);
  });

  child.on('exit', (code, signal) => {
    const reason = signal ? `signal ${signal}` : `code ${code}`;
    logStream.write(`[${timestamp()}] [${label}] exited (${reason})\n`);
    logStream.end();
    console.log(`[stack] ${label} exited (${reason}).`);
  });
  return child;
}

async function main() {
  const requestedWebPort = process.argv[2] || process.env.NC_WEB_PORT || '';
  const shouldStartWebHost = (process.env.NC_START_WEB_HOST || '1') !== '0';
  const shouldLaunchDummy = (process.env.NC_LAUNCH_DUMMY || '1') !== '0';
  const shouldLaunchLocalHuman = process.env.NC_LAUNCH_LOCAL_HUMAN === '1';
  const shouldAutoStartSession = (process.env.NC_AUTOSTART_SESSION || '1') !== '0';
  const shouldLogDummyToFile = (process.env.NC_DUMMY_LOG_TO_FILE || '1') !== '0';
  const waitTimeoutMs = toOptionalTimeoutMs(process.env.NC_WAIT_TIMEOUT_MS || '');
  const webHost = process.env.NC_WEB_HOST || '127.0.0.1';
  const dummyLogPath = path.resolve(
    projectDir,
    process.env.NC_DUMMY_LOG_PATH || path.join('logs', 'dummy.log'),
  );
  const fallbackWebPort = toPositiveIntOrDefault(
    requestedWebPort || process.env.NC_WEB_PORT || '9000',
    9000,
  );

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

  let localWebUrl = normalizeUrlOrigin(`http://${webHost}:${fallbackWebPort}`);
  if (shouldStartWebHost) {
    const { child: webChild, webUrl } = await startWebHost(requestedWebPort, {
      NC_DEV_PROXY_TARGET: baseUrl,
    });
    children.push(webChild);
    localWebUrl = normalizeUrlOrigin(webUrl, localWebUrl);
  }

  const created = await requestJson(baseUrl, '/sessions', 'POST', {});
  const sessionId = created.session_id;
  const adminToken = created.admin_token;
  const invites = Array.isArray(created.invites) ? created.invites : [];
  if (!sessionId || !adminToken || invites.length === 0) {
    throw new Error('Invalid session creation response from server.');
  }

  const usedRoleIds = new Set();

  if (shouldLaunchLocalHuman) {
    const localHumanInvite = process.env.NC_HUMAN_INVITE_TOKEN
      ? { invite_token: process.env.NC_HUMAN_INVITE_TOKEN, role_id: 'human_manual' }
      : pickInvite(invites, ['human', 'hybrid'], usedRoleIds);
    if (!localHumanInvite || !localHumanInvite.invite_token) {
      throw new Error('Could not resolve invite token for a local human role.');
    }
    if (localHumanInvite.role_id) {
      usedRoleIds.add(localHumanInvite.role_id);
    }
    const humanArgs = ['scripts/run_human_web.js'];
    if (requestedWebPort) {
      humanArgs.push(String(requestedWebPort));
    }
    const humanChild = launchClient(
      'human:play',
      humanArgs,
      {
        NC_BASE_URL: baseUrl,
        NC_INVITE_TOKEN: localHumanInvite.invite_token,
      },
    );
    children.push(humanChild);
    console.log(`[stack] local human role: ${localHumanInvite.role_id || 'manual'}`);
  }

  if (shouldLaunchDummy) {
    const dummyInvite = process.env.NC_DUMMY_INVITE_TOKEN
      ? { invite_token: process.env.NC_DUMMY_INVITE_TOKEN, role_id: 'dummy_manual' }
      : pickInvite(invites, ['ai', 'hybrid'], usedRoleIds);
    if (!dummyInvite || !dummyInvite.invite_token) {
      console.warn('[stack] no dummy/AI invite found; skipping dummy client.');
    } else {
      if (dummyInvite.role_id) {
        usedRoleIds.add(dummyInvite.role_id);
      }
      const dummyEnv = {
        NC_BASE_URL: baseUrl,
        NC_INVITE_TOKEN: dummyInvite.invite_token,
        NC_INTERVAL_MS: process.env.NC_INTERVAL_MS || '400',
      };
      const dummyChild = shouldLogDummyToFile
        ? launchClientToLog(
          'dummy:random',
          ['scripts/dummy_random_client.js'],
          dummyEnv,
          dummyLogPath,
        )
        : launchClient(
          'dummy:random',
          ['scripts/dummy_random_client.js'],
          dummyEnv,
        );
      children.push(dummyChild);
      console.log(`[stack] dummy role: ${dummyInvite.role_id || 'manual'}`);
      if (shouldLogDummyToFile) {
        console.log(`[stack] dummy logs: ${dummyLogPath}`);
      }
    }
  }

  const shareWebBase = normalizeUrlBase(
    process.env.NC_PUBLIC_WEB_URL || process.env.NC_SHARE_WEB_URL || localWebUrl,
  );
  const requestedApiBase = normalizeUrlBase(
    process.env.NC_PUBLIC_BASE_URL || process.env.NC_SHARE_BASE_URL || '',
  );
  const useSinglePublicUrlProxy =
    shouldStartWebHost
    && shareWebBase
    && (!requestedApiBase || requestedApiBase === shareWebBase);
  const shareApiBase = useSinglePublicUrlProxy
    ? `${shareWebBase}/__nc_api`
    : (requestedApiBase || baseUrl);

  const shareInvites = humanShareInvites(invites);
  console.log(`[stack] session created: ${sessionId}`);
  console.log(`[stack] loop mode: ${created.loop_mode}, tick rate: ${created.tick_rate}`);
  if (useSinglePublicUrlProxy) {
    console.log('[stack] using web host API proxy: /__nc_api -> local session server');
  }
  if (shareInvites.length === 0) {
    console.warn('[stack] no human/hybrid invites found to share.');
  } else {
    console.log('[stack] share these player URLs:');
    for (const invite of shareInvites) {
      const url = buildSessionShareUrl(shareWebBase, shareApiBase, invite.invite_token);
      console.log(`[share] ${invite.role_id}: ${url}`);
    }
  }

  if (isLocalhostUrl(shareWebBase) || isLocalhostUrl(shareApiBase)) {
    console.warn(
      '[stack] sharing warning: URL uses localhost. For remote players (ngrok), set NC_PUBLIC_WEB_URL and NC_PUBLIC_BASE_URL.',
    );
  }

  if (shouldAutoStartSession) {
    console.log('[stack] waiting for required roles before auto-start...');
    await waitForRequiredRolesConnected(baseUrl, sessionId, waitTimeoutMs);
    await requestJson(
      baseUrl,
      `/sessions/${encodeURIComponent(sessionId)}/start`,
      'POST',
      { admin_token: adminToken },
    );
    console.log(`[stack] session started: ${sessionId}`);
  } else {
    console.log('[stack] auto-start disabled (NC_AUTOSTART_SESSION=0).');
  }

  console.log('[stack] press Ctrl+C to stop server and clients.');
  await new Promise(() => {});
}

main().catch((error) => {
  console.error('[stack] failed:', error.message || error);
  process.exit(1);
});
