# NanoCalibur Documentation

NanoCalibur is a deterministic engine pipeline:

1. Write game logic in a constrained Python DSL.
2. Compile to `game_spec.json` + generated TypeScript runtime glue.
3. Run in browser or headless HTTP mode (human, bot, or LLM clients).

## Install

```bash
pip install -e .
```

With docs tooling:

```bash
pip install -e ".[docs]"
```

## Main CLI

Build a game bundle from a Python entrypoint:

```bash
nanocalibur-build-game ./examples/scene/main.py --project ./nanocalibur-demo
```

The generated files are copied to:

- `nanocalibur-demo/src/nanocalibur_generated`

## Human Docs Commands

```bash
mkdocs serve
mkdocs build
```

## Next Reading

- First run: `docs/quickstart.md`
- Engine model: `docs/concepts.md`
- DSL details: `docs/dsl-reference.md`
- Session API and multiplayer flow: `docs/runtime-sessions.md`
- Python API docs: `docs/api.md`
- Full LLM-focused authoring guide: `LLM.md`
