#!/usr/bin/env node

const baseUrl = (process.env.NC_BASE_URL || 'http://127.0.0.1:7070').replace(/\/$/, '');
const inviteToken = process.env.NC_INVITE_TOKEN || process.argv[2] || '';
const intervalMsRaw = Number(process.env.NC_INTERVAL_MS || '400');
const intervalMs = Number.isFinite(intervalMsRaw) && intervalMsRaw > 0 ? Math.floor(intervalMsRaw) : 400;

if (!inviteToken) {
  console.error('Usage: NC_INVITE_TOKEN=<invite_token> node scripts/dummy_random_client.js');
  process.exit(1);
}

async function requestJson(path, method, payload, extraHeaders = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...extraHeaders,
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });

  const text = await response.text();
  const decoded = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const message = decoded && decoded.error ? decoded.error : `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return decoded;
}

function pickToolCommand(toolNames) {
  if (!Array.isArray(toolNames) || toolNames.length === 0) {
    return { kind: 'noop' };
  }
  const index = Math.floor(Math.random() * toolNames.length);
  return {
    kind: 'tool',
    name: toolNames[index],
  };
}

async function main() {
  const joined = await requestJson('/join', 'POST', {
    invite_token: inviteToken,
  });

  const sessionId = joined.session_id;
  const accessToken = joined.access_token;
  const roleId = joined.role_id;

  const toolsPayload = await requestJson(
    `/sessions/${encodeURIComponent(sessionId)}/tools`,
    'GET',
    null,
    { 'x-role-token': accessToken },
  );
  const allTools = Array.isArray(toolsPayload?.tools) ? toolsPayload.tools : [];
  const llmTools = allTools
    .map((item) => (item && typeof item.name === 'string' ? item.name : ''))
    .filter((name) => name.startsWith('llm_dummy_'));

  if (llmTools.length === 0) {
    console.error('[dummy] no llm_dummy_* tools found in session; sending noop commands.');
  } else {
    console.log(`[dummy] discovered tools: ${llmTools.join(', ')}`);
  }
  console.log(`[dummy] joined session=${sessionId} role=${roleId}`);

  const timer = setInterval(async () => {
    try {
      const result = await requestJson(`/sessions/${encodeURIComponent(sessionId)}/commands`, 'POST', {
        access_token: accessToken,
        commands: [pickToolCommand(llmTools)],
        tick: false,
      });
      const elapsed = result?.state?.scene?.elapsed;
      const turn = result?.state?.scene?.turn;
      console.log(`[dummy] queued elapsed=${elapsed} turn=${turn}`);
    } catch (error) {
      console.error('[dummy] command error:', error.message || String(error));
    }
  }, intervalMs);

  process.on('SIGINT', () => {
    clearInterval(timer);
    process.exit(0);
  });
  process.on('SIGTERM', () => {
    clearInterval(timer);
    process.exit(0);
  });
}

main().catch((error) => {
  console.error('[dummy] failed to start:', error);
  process.exit(1);
});
