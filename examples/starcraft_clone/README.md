# StarCraft Clone Example

A modern NanoCalibur 1v1 RTS-like sample using:

- multi-file project layout
- `CodeBlock` + `AbstractCodeBlock`
- role-scoped interfaces
- external fixed map (`maps/arena_1v1.txt`)
- `BlockInSprite` / `ColorSprite` sprite fallback flow
- runtime actor spawning (`scene.spawn(...)`)
- drag selection + right-click move/attack orders
- click-to-place building construction flow
- supply cap/usage economy with production gating
- tile-aware placement validation (cannot place on wall tiles)
- tech/prerequisite loss when structures are destroyed
- command queue (queue-next mode)
- player rally points for production flows
- role-scoped camera panning + recenter
- fog-of-war actor visibility per role
- worker shuttle economy (harvest -> return to HQ -> harvest loop)
- selection-gated production UI (HQ/Barracks/Factory/Lab sections)
- timed production/research/construction with interface progress bar

## Build

```bash
nanocalibur-build-game examples/starcraft_clone/main.py --project ./nanocalibur-demo
```

## Run

From `nanocalibur-demo`:

```bash
npm run session:auto -- 9020
```

Open the printed join URLs for `human_1` and `human_2`.

## Notes

- Left click:
  - if a build is queued from HUD button, starts timed construction at click position.
  - click one of your buildings to select it and unlock its production buttons.
  - otherwise performs single select / drag box select for your units.
- Right click:
  - on enemy = attack order.
  - on empty ground = command-mode order for current selection (spread formation).
- Command mode:
  - `Move`: right-click ground performs pure move.
  - `Attack-Move`: right-click ground performs move with auto-engage enemies in acquisition radius.
- Queue:
  - click `Queue Next`, then your next right-click order is queued (executed after current order).
- Rally:
  - click `Set Rally`, then left-click map to move your role rally point.
- Camera:
  - hold arrow keys to pan your own role camera.
  - press `f` to recenter on your HQ.
- Fog:
  - enemy/neutral actors are hidden unless revealed by your unit/building vision.
- Placement feedback:
  - HUD shows preview coordinates, validity flag, and explicit invalid reason.
- Economy uses cargo shuttling (workers carry resources back to HQ).
- Units and buildings are spawned at runtime (not preloaded inactive pools).
