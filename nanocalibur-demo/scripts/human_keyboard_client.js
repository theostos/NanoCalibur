#!/usr/bin/env node

const readline = require('readline');

const baseUrl = (process.env.NC_BASE_URL || 'http://127.0.0.1:7070').replace(/\/$/, '');
const inviteToken = process.env.NC_INVITE_TOKEN || process.argv[2] || '';

if (!inviteToken) {
  console.error('Usage: NC_INVITE_TOKEN=<invite_token> node scripts/human_keyboard_client.js');
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

function clearScreen() {
  process.stdout.write('\x1b[2J\x1b[H');
}

function formatFrame(snapshot) {
  const frame = snapshot?.frame || {};
  const state = snapshot?.state || {};
  const rows = Array.isArray(frame.rows) ? frame.rows : [];
  const legend = Array.isArray(frame.legend)
    ? frame.legend.map((item) => `${item.symbol}: ${item.description}`).join('\n')
    : '';

  const elapsed = state?.scene?.elapsed;
  const turn = state?.scene?.turn;
  const globals = state?.globals || {};

  const lines = [];
  lines.push(`elapsed=${elapsed} turn=${turn}`);
  lines.push(`globals=${JSON.stringify(globals)}`);
  lines.push('');
  lines.push(...rows);
  if (legend) {
    lines.push('');
    lines.push('Legend');
    lines.push(legend);
  }
  lines.push('');
  lines.push('Controls: zqsd / wasd / arrows | e=spawn_bonus | n=llm_dummy_next_turn | Ctrl+C quit');
  return lines.join('\n');
}

function mapKeyToCommand(key) {
  if (!key || typeof key !== 'object') {
    return null;
  }

  const name = key.name;
  const seq = key.sequence;

  if (name === 'up') return { kind: 'input', keyboard: { on: ['z'] } };
  if (name === 'left') return { kind: 'input', keyboard: { on: ['q'] } };
  if (name === 'down') return { kind: 'input', keyboard: { on: ['s'] } };
  if (name === 'right') return { kind: 'input', keyboard: { on: ['d'] } };

  if (seq === 'z' || seq === 'w') return { kind: 'input', keyboard: { on: ['z'] } };
  if (seq === 'q' || seq === 'a') return { kind: 'input', keyboard: { on: ['q'] } };
  if (seq === 's') return { kind: 'input', keyboard: { on: ['s'] } };
  if (seq === 'd') return { kind: 'input', keyboard: { on: ['d'] } };

  if (seq === 'e') return { kind: 'tool', name: 'spawn_bonus' };
  if (seq === 'n') return { kind: 'tool', name: 'llm_dummy_next_turn' };

  return null;
}

async function main() {
  const joined = await requestJson('/join', 'POST', {
    invite_token: inviteToken,
  });

  const sessionId = joined.session_id;
  const accessToken = joined.access_token;
  const roleId = joined.role_id;

  console.log(`[human] joined session=${sessionId} role=${roleId}`);

  let streamResponse;
  try {
    streamResponse = await fetch(`${baseUrl}/sessions/${encodeURIComponent(sessionId)}/stream`, {
      headers: {
        Accept: 'text/event-stream',
        'x-role-token': accessToken,
      },
    });
  } catch (error) {
    throw new Error(`failed to open stream: ${error.message || String(error)}`);
  }

  if (!streamResponse.ok || !streamResponse.body) {
    const text = await streamResponse.text();
    throw new Error(text || `stream error ${streamResponse.status}`);
  }

  const decoder = new TextDecoder('utf-8');
  let sseBuffer = '';

  const renderSnapshot = (snapshot) => {
    clearScreen();
    process.stdout.write(formatFrame(snapshot));
  };

  const streamTask = (async () => {
    for await (const chunk of streamResponse.body) {
      sseBuffer += decoder.decode(chunk, { stream: true });
      while (true) {
        const splitIndex = sseBuffer.indexOf('\n\n');
        if (splitIndex < 0) break;
        const rawEvent = sseBuffer.slice(0, splitIndex);
        sseBuffer = sseBuffer.slice(splitIndex + 2);

        const lines = rawEvent.split('\n');
        let eventName = '';
        let dataLine = '';
        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventName = line.slice('event:'.length).trim();
          } else if (line.startsWith('data:')) {
            dataLine += line.slice('data:'.length).trim();
          }
        }

        if (eventName === 'snapshot' && dataLine) {
          try {
            const snapshot = JSON.parse(dataLine);
            renderSnapshot(snapshot);
          } catch (_error) {
            // ignore malformed snapshot payloads
          }
        }
      }
    }
  })().catch((error) => {
    console.error('\n[human] stream ended with error:', error.message || String(error));
  });

  readline.emitKeypressEvents(process.stdin);
  if (process.stdin.isTTY) {
    process.stdin.setRawMode(true);
  }

  process.stdin.on('keypress', async (_str, key) => {
    if (key && key.ctrl && key.name === 'c') {
      process.exit(0);
      return;
    }

    const command = mapKeyToCommand(key);
    if (!command) {
      return;
    }

    try {
      await requestJson(`/sessions/${encodeURIComponent(sessionId)}/commands`, 'POST', {
        access_token: accessToken,
        commands: [command],
      });
    } catch (error) {
      console.error(`\n[human] command error: ${error.message || String(error)}`);
    }
  });

  await streamTask;
}

main().catch((error) => {
  console.error('[human] failed to start:', error);
  process.exit(1);
});
