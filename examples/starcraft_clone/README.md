# Starcraft Clone Sandbox (Feature 01)

This folder contains a modular RTS sandbox scene used to validate engine features independently.

Current feature:
- Two-player multiplayer scene (`human_1` required, `human_2` optional).
- Each player starts with one `Worker` and one `HQ`.
- Left click selects only owned units/buildings.
- Right click computes a path and moves selected owned worker along that path.
- Units/buildings are treated as path blockers.
- Selection now creates a visible selection marker around the selected object.
- Resource nodes are available near each HQ and in central map clusters for panning tests.
- Bottom HUD shows current selection and role resources.

Build:

```bash
nanocalibur-build-game examples/starcraft_clone/main.py --project ./nanocalibur-demo
```

Run:

```bash
cd nanocalibur-demo
npm run session:auto -- 9020
```
