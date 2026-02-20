# NanoCalibur Agent Notes

## Mission

Keep NanoCalibur small, deterministic, and LLM-friendly:

1. Python DSL (AST-only, no execution).
2. Deterministic compile/export (`ProjectSpec`, IR, generated TS).
3. Runtime parity across browser, headless, and session server.

## Architecture Map

### Python Compiler Stack

- `nanocalibur/dsl_markers.py`: authoring surface (markers + decorators).
- `nanocalibur/compiler/`: function-body compiler (`ActionIR`/`PredicateIR`/`CallableIR`).
- `nanocalibur/project_compiler.py`: whole-project orchestration + validations.
- `nanocalibur/game_model.py`: spec dataclasses and enums.
- `nanocalibur/exporter.py`: writes `game_spec.json`, `game_ir.json`, `game_logic.ts`.
- `nanocalibur/ts_generator.py`: IR -> TypeScript code.
- `nanocalibur/build_game.py`: entry CLI to produce generated bundle.

### TypeScript Runtime Stack

- `nanocalibur/runtime/interpreter.ts`: rule evaluation and scene state mutation.
- `nanocalibur/runtime/runtime_core.ts`: physics+animation+interpreter stepping.
- `nanocalibur/runtime/canvas_host.ts`: local browser runtime loop.
- `nanocalibur/runtime/headless_host.ts`: non-browser stepping API.
- `nanocalibur/runtime/headless_http_server.ts`: HTTP/session endpoints.
- `nanocalibur/runtime/session_runtime.ts` + `session_manager.ts`: role queues, loops, pacing, seeds.
- `nanocalibur/runtime/symbolic_renderer.ts`: symbolic frame/legend output.

### Web Bundle Integration

- `nanocalibur-demo/src/main.ts`: browser/session client behavior.
- generated code lives under `src/nanocalibur_generated`.

## Current Product Invariants

- DSL is explicit; no compatibility legacy is required for removed APIs.
- Conditions must use `@safe_condition` / `@unsafe_condition`.
- Input/tool conditions are role-scoped and require declared role ids.
- Camera model is explicit and role-bound (`Camera(..., Role["id"]) + scene.add_camera`).
- `Local[...]` role fields are client-owned, never server-authoritative.
- `HumanRole` is built-in and immutable; includes local `keybinds`.

## Change Workflow (Required)

When modifying features:

1. Update DSL markers + compiler validations first.
2. Update `game_model.py` + exporter serialization.
3. Update runtime behavior (browser/headless/session) to match semantics.
4. Update docs (`README.md`, `docs/`, `LLM.md`) in same change.
5. Add/adjust tests for compiler + exporter + runtime paths.

Never ship semantics that exist in only one layer.

## Public API Contract

- Keep `nanocalibur.__all__` small and stable.
- Treat `nanocalibur.dsl_markers` as the DSL authoring surface.
- Avoid exporting internal compiler constants/helpers.
- If a symbol is internal-only, keep it out of package exports and prefer
  underscore naming for helper functions/modules.

When adding/changing public behavior:

1. Add/refresh type hints.
2. Add/refresh docstrings (Google style).
3. Update `docs/api.md` / `LLM.md` / `README.md`.
4. Add a regression test.

## Testing Commands

Use repository root:

```bash
PYTHONPATH=. pytest -q
```

For demo bundle compile sanity:

```bash
cd nanocalibur-demo
npm run build
```

For generated code refresh:

```bash
nanocalibur-build-game ./examples/scene.py --project ./nanocalibur-demo
```

For docs:

```bash
python -m pip install -e ".[docs]"
mkdocs build --strict
```

## High-Risk Areas

- Role-scoped behavior (`id`, selectors, session role mapping).
- Safe vs unsafe condition routing.
- Local role variables (`Local[...]`) leaking into server logic.
- Camera scoping and per-role rendering.
- Physics regressions around parented actors and blocking masks.

Any change in these areas should include dedicated regression tests.

## Documentation Contract

- Human docs are MkDocs-based (`mkdocs.yml`, `docs/`).
- LLM docs live in root `LLM.md` and must stay concise and operational.
- `agent.md` must remain architecture- and workflow-focused for maintenance agents.
