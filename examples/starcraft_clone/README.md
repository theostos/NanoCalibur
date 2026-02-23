# Starcraft Clone Sandbox

This folder contains a modular RTS sandbox scene used to validate engine features independently.

Current features:
- Two-player multiplayer scene (`human_1` required, `human_2` optional).
- Each player starts with one `Worker` and one `HQ`.
- Left click selects only owned units/buildings.
- Right click computes a path and moves selected owned movable units along that path.
- Right click on a mineral/gas node starts a timed gather loop (travel, harvest progress, return, unload progress).
- Workers unload to the nearest owned HQ when gather starts.
- Same-team moving units pass through each other while enemy units still block.
- Selection creates a visible selection marker around the selected object.
- Resource nodes are available near each HQ and in central map clusters for panning tests.
- Bottom HUD is selection-sensitive:
  - Selecting an `HQ` shows `Train Worker`.
  - Selecting a `Worker` shows structure commands (`HQ`, `Supply Depot`, `Barracks`, `Academy`, `Starport`).
  - Selecting an `Academy` shows timed attack/armor upgrades.
  - Buttons are hidden when not relevant; if relevant but not affordable/allowed, they stay visible and disabled.
- Building placement is explicit: choose a worker command, then click a valid map location.
- Construction uses visible in-world placeholders:
  - Site appears immediately, is attackable, non-usable, and non-blocking until complete.
  - Build progress and HP advance together with construction percentage.
  - A worker must be near/inside the site to progress it.
  - Construction can be resumed by assigning another worker to the same unfinished site.
- Timed tasks expose progress in HUD (bar + integer percentage + ETA) for the currently selected producer.

Build:

```bash
nanocalibur-build-game examples/starcraft_clone/main.py --project ./nanocalibur-demo
```

Run:

```bash
cd nanocalibur-demo
npm run session:auto -- 9020
```
