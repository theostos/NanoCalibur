# NanoCalibur Agent Notes

## Mission
NanoCalibur is a tiny game engine pipeline:
1. Parse a simple Python DSL scene file.
2. Compile/export a structured game spec + generated TypeScript game logic.
3. Run the game with a standalone TypeScript runtime.

Primary goal: keep the engine minimal, explicit, and easy for LLMs to both generate games and interact with running games.

## Core Product Principles
- Keep the DSL small and predictable.
- Prefer explicit data over hidden runtime conventions.
- No deprecated compatibility layers during this phase.
- Runtime should support both visual debugging and high-throughput headless execution.

## Current Runtime Architecture
- `interpreter.ts`: executes rules/actions against runtime state.
- `runtime_core.ts`: shared simulation core (physics + animation + interpreter stepping).
- `canvas_host.ts`: browser host (input loop + canvas rendering).
- `headless_host.ts`: non-browser host for fast stepping and tool-driven interaction.
- `headless_http_server.ts`: HTTP endpoint layer over `HeadlessHost`.
- `symbolic_renderer.ts`: grid-character rendering for LLM/RL consumption.

## LLM Interaction Goal (Important)
The project must make LLM interaction first-class, not an afterthought.

### Tool-driven actions
- DSL supports `ToolCalling(name, tool_docstring)` conditions.
- Exported spec includes tool metadata.
- Headless runtime exposes tool calls via `HeadlessHost.callTool(...)`.
- HTTP runtime exposes tool calls for remote clients (`POST /tools/call`).
- `NanoCaliburMCPServer` provides minimal MCP-style handlers:
  - `tools/list`
  - `tools/call`
  - `nanocalibur/render`
  - `nanocalibur/state`
- Python bridge (`nanocalibur.mcp_bridge`) can metaprogram a FastMCP server from HTTP-discovered tools.

### Symbolic rendering
- Sprites support optional symbolic metadata:
  - `symbol` (single character)
  - `description` (short natural-language description)
- Symbolic renderer returns:
  - grid rows
  - legend (`symbol -> description`)

## DSL/Model Expectations
- `TileMap` uses `masks=[(x, y, mask)]` only.
- Blocking semantics are mask-based.
- `None` actor mask means no blocking.
- Equal actor masks mutually block and separate.
- Actor animation/lifecycle actions use instance methods (`actor.play("clip")`, `actor.destroy()`), not static `Actor.play(...)`/`Actor.destroy(...)`.
- UI overlay is opt-in via `game.set_interface(html)`; no default hardcoded interface should be assumed.
- Collision conditions are split by intent: `OnOverlap(...)` (legacy alias `CollisionRelated(...)`) and `OnContact(...)`.
- Keep condition/action semantics deterministic and statically checkable where possible.

## Dev Rules
- Prefer removing obsolete paths over maintaining backward compatibility in this phase.
- Add/maintain unit tests for compiler, exporter, and runtime behavior whenever features change.
- Keep generated bundle templates aligned with runtime entry points.
