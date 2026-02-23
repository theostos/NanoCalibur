# Starcraft Clone Sandbox

This folder contains a modular RTS sandbox scene used to validate engine features independently.

Current features:
- Two-player multiplayer scene (`human_1` required, `human_2` optional).
- Each player starts with one `Worker` and one `HQ`.
- Left click selects only owned units/buildings.
- Right click computes a path and moves selected owned worker along that path.
- Right click on a mineral/gas node starts a timed gather loop (travel, harvest progress, return, unload progress).
- Units/buildings are treated as path blockers.
- Selection creates a visible selection marker around the selected object.
- Resource nodes are available near each HQ and in central map clusters for panning tests.
- Bottom HUD is selection-sensitive:
  - Selecting an `HQ` enables `Train Worker` when resources/supply allow it.
  - Selecting a `Worker` enables structure commands (`HQ`, `Supply Depot`, `Barracks`, `Academy`, `Starport`) with requirement checks.
  - Selecting an `Academy` enables timed attack/armor upgrades.
- Timed tasks expose progress in HUD (bar + percentage + ETA) for the currently selected producer.

Build:

```bash
nanocalibur-build-game examples/starcraft_clone/main.py --project ./nanocalibur-demo
```

Run:

```bash
cd nanocalibur-demo
npm run session:auto -- 9020
```
