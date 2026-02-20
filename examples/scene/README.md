# Scene Example

This folder contains two versions of the same game:

- `main.py`: modular multi-file layout (`shared.py`, `roles.py`, `controls.py`, ...).
- `monolithic.py`: single-file layout with one `CodeBlock.begin("main")`.

## Build (multi-file)

```bash
nanocalibur-build-game examples/scene/main.py --project ./nanocalibur-demo
```

## Build (monolithic)

```bash
nanocalibur-build-game examples/scene/monolithic.py --project ./nanocalibur-demo
```

Then run from `nanocalibur-demo`:

```bash
npm run session:auto -- 9020
```
