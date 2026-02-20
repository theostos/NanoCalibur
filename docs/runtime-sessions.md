# Runtime and Sessions

NanoCalibur supports:

- standalone local browser runtime
- headless runtime
- multiplayer session runtime over HTTP

## Session Lifecycle

Typical flow:

1. `POST /sessions` to create a new session.
2. `POST /join` with an invite token to claim a role.
3. `POST /sessions/{id}/start` (admin token) to start gameplay.
4. send commands via `POST /sessions/{id}/commands`.
5. read snapshots via `GET /sessions/{id}/stream` (SSE) or `/frame` + `/state`.

## Useful Endpoints

- health/runtime:
- `GET /health`
- `GET /tools`
- `POST /tools/call`
- `GET /state`
- `GET /frame`
- session:
- `GET /sessions`
- `POST /sessions`
- `POST /join`
- `GET /sessions/{id}/open-roles`
- `POST /sessions/{id}/start`
- `POST /sessions/{id}/stop`
- `PATCH /sessions/{id}/pace`
- `POST /sessions/{id}/commands`
- `GET /sessions/{id}/stream`

## Loop Modes

Configured from DSL `game.set_multiplayer(...)`:

- `real_time`
- `turn_based`
- `hybrid`

For `turn_based` and `hybrid`, actions must call `scene.next_turn()` to advance turns.

## Determinism and Seeds

- each session has a seed
- if omitted, server generates one
- seeds are unique per session
- seed and pacing changes are persisted in replay events

## Local vs Authoritative State

- authoritative state is server-owned (`globals`, actors, server role fields, physics, safe conditions)
- client-owned role locals (`Local[...]`) are not synchronized to server
- clients can still use local state for UI and input mapping (for example keybinds)
