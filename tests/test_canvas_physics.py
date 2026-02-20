import json
import subprocess
import textwrap
from pathlib import Path


def test_non_dynamic_actor_post_action_tile_blocking(tmp_path):
    root = Path(__file__).resolve().parent.parent
    physics_ts_path = root / "nanocalibur" / "runtime" / "canvas" / "physics.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(physics_ts_path),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    physics_js_path = compiled_dir / "physics.js"

    script = textwrap.dedent(
        f"""
        const {{ PhysicsSystem }} = require({json.dumps(str(physics_js_path))});

        function runCase(actor) {{
          const physics = new PhysicsSystem({{}});
          physics.setMap({{
            width: 5,
            height: 5,
            tile_size: 32,
            tile_grid: [
              [0, 0, 0, 0, 0],
              [0, 0, 0, 0, 0],
              [0, 0, 1, 0, 0],
              [0, 0, 0, 0, 0],
              [0, 0, 0, 0, 0]
            ],
            tile_defs: {{
              "1": {{
                block_mask: 2,
                sprite: null,
                color: {{ r: 50, g: 50, b: 50 }}
              }}
            }}
          }});

          const actors = [actor];

          // Snapshot frame start state.
          physics.syncBodiesFromActors(actors, false);
          physics.integrate(0);

          // Simulate post-rule movement (e.g. parent binding in interpreter tick).
          actor.x = 70;
          actor.y = 70;
          physics.syncBodiesFromActors(actors, true);

          physics.resolvePostActionSolidCollisions();
          physics.writeBodiesToActors(actors);
          return {{ x: actor.x, y: actor.y }};
        }}

        const blocked = runCase({{
          uid: "coin_blocked",
          type: "Coin",
          x: 50,
          y: 50,
          w: 16,
          h: 16,
          active: true,
          block_mask: 1
        }});

        const unblocked = runCase({{
          uid: "coin_unblocked",
          type: "Coin",
          x: 50,
          y: 50,
          w: 16,
          h: 16,
          active: true
        }});

        console.log(JSON.stringify({{ blocked, unblocked }}));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["blocked"]["x"] == 50
    assert values["blocked"]["y"] == 50
    assert values["unblocked"]["x"] == 70
    assert values["unblocked"]["y"] == 70


def test_actor_overlap_with_different_masks_does_not_push(tmp_path):
    root = Path(__file__).resolve().parent.parent
    physics_ts_path = root / "nanocalibur" / "runtime" / "canvas" / "physics.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(physics_ts_path),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    physics_js_path = compiled_dir / "physics.js"

    script = textwrap.dedent(
        f"""
        const {{ PhysicsSystem }} = require({json.dumps(str(physics_js_path))});

        const physics = new PhysicsSystem({{}});
        physics.setMap({{
          width: 20,
          height: 20,
          tile_size: 32,
          tile_grid: Array.from({{ length: 20 }}, () => Array.from({{ length: 20 }}, () => 0)),
          tile_defs: {{}}
        }});

        const actors = [
          {{
            uid: "high",
            type: "Player",
            x: 100,
            y: 100,
            w: 20,
            h: 20,
            active: true,
            block_mask: 2
          }},
          {{
            uid: "low",
            type: "Player",
            x: 110,
            y: 100,
            w: 20,
            h: 20,
            active: true,
            block_mask: 1
          }}
        ];

        physics.syncBodiesFromActors(actors, false);
        physics.integrate(0);
        physics.resolvePostActionSolidCollisions();
        physics.writeBodiesToActors(actors);

        console.log(JSON.stringify({{
          highX: actors[0].x,
          lowX: actors[1].x
        }}));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["highX"] == 100
    assert values["lowX"] == 110


def test_actor_overlap_with_equal_masks_pushes_dynamic_actor(tmp_path):
    root = Path(__file__).resolve().parent.parent
    physics_ts_path = root / "nanocalibur" / "runtime" / "canvas" / "physics.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(physics_ts_path),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    physics_js_path = compiled_dir / "physics.js"

    script = textwrap.dedent(
        f"""
        const {{ PhysicsSystem }} = require({json.dumps(str(physics_js_path))});

        const physics = new PhysicsSystem({{}});
        physics.setMap({{
          width: 20,
          height: 20,
          tile_size: 32,
          tile_grid: Array.from({{ length: 20 }}, () => Array.from({{ length: 20 }}, () => 0)),
          tile_defs: {{}}
        }});

        const actors = [
          {{
            uid: "hero",
            type: "Player",
            x: 100,
            y: 100,
            w: 20,
            h: 20,
            active: true,
            block_mask: 1
          }},
          {{
            uid: "coin_pet",
            type: "Coin",
            x: 110,
            y: 100,
            w: 20,
            h: 20,
            active: true,
            block_mask: 1
          }}
        ];

        physics.syncBodiesFromActors(actors, false);
        physics.integrate(0);
        physics.resolvePostActionSolidCollisions();
        physics.writeBodiesToActors(actors);

        const distance = Math.abs(actors[0].x - actors[1].x);
        console.log(JSON.stringify({{
          heroX: actors[0].x,
          petX: actors[1].x,
          distance
        }}));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["heroX"] < 100
    assert values["petX"] == 110
    assert values["distance"] >= 20


def test_actor_overlap_still_reports_collision_pair(tmp_path):
    root = Path(__file__).resolve().parent.parent
    physics_ts_path = root / "nanocalibur" / "runtime" / "canvas" / "physics.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(physics_ts_path),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    physics_js_path = compiled_dir / "physics.js"

    script = textwrap.dedent(
        f"""
        const {{ PhysicsSystem }} = require({json.dumps(str(physics_js_path))});

        const physics = new PhysicsSystem({{}});
        physics.setMap({{
          width: 20,
          height: 20,
          tile_size: 32,
          tile_grid: Array.from({{ length: 20 }}, () => Array.from({{ length: 20 }}, () => 0)),
          tile_defs: {{}}
        }});

        const actors = [
          {{
            uid: "hero",
            type: "Player",
            x: 100,
            y: 100,
            w: 20,
            h: 20,
            active: true,
            block_mask: 1
          }},
          {{
            uid: "coin_pet",
            type: "Coin",
            x: 110,
            y: 100,
            w: 20,
            h: 20,
            active: true,
            block_mask: 1
          }}
        ];

        physics.syncBodiesFromActors(actors, false);
        physics.integrate(0);
        physics.writeBodiesToActors(actors);

        const collisions = physics.detectCollisions(actors);
        console.log(JSON.stringify({{
          heroX: actors[0].x,
          petX: actors[1].x,
          collisions
        }}));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["heroX"] == 100
    assert values["petX"] == 110
    assert values["collisions"] == [{"aUid": "hero", "bUid": "coin_pet"}]


def test_actor_contacts_require_equal_block_masks(tmp_path):
    root = Path(__file__).resolve().parent.parent
    physics_ts_path = root / "nanocalibur" / "runtime" / "canvas" / "physics.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(physics_ts_path),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    physics_js_path = compiled_dir / "physics.js"

    script = textwrap.dedent(
        f"""
        const {{ PhysicsSystem }} = require({json.dumps(str(physics_js_path))});

        const physics = new PhysicsSystem({{}});
        physics.setMap({{
          width: 20,
          height: 20,
          tile_size: 32,
          tile_grid: Array.from({{ length: 20 }}, () => Array.from({{ length: 20 }}, () => 0)),
          tile_defs: {{}}
        }});

        const equalMaskActors = [
          {{ uid: "hero", type: "Player", x: 100, y: 100, w: 20, h: 20, active: true, block_mask: 1 }},
          {{ uid: "coin_1", type: "Coin", x: 120, y: 100, w: 20, h: 20, active: true, block_mask: 1 }}
        ];
        physics.syncBodiesFromActors(equalMaskActors, false);
        physics.integrate(0);
        const equalContacts = physics.detectContacts(equalMaskActors);

        const differentMaskActors = [
          {{ uid: "hero2", type: "Player", x: 100, y: 100, w: 20, h: 20, active: true, block_mask: 1 }},
          {{ uid: "coin_2", type: "Coin", x: 120, y: 100, w: 20, h: 20, active: true, block_mask: 2 }}
        ];
        physics.syncBodiesFromActors(differentMaskActors, false);
        physics.integrate(0);
        const differentContacts = physics.detectContacts(differentMaskActors);

        console.log(JSON.stringify({{ equalContacts, differentContacts }}));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["equalContacts"] == [{"aUid": "hero", "bUid": "coin_1"}]
    assert values["differentContacts"] == []


def test_actor_tile_overlap_events_include_tile_coords(tmp_path):
    root = Path(__file__).resolve().parent.parent
    physics_ts_path = root / "nanocalibur" / "runtime" / "canvas" / "physics.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(physics_ts_path),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    physics_js_path = compiled_dir / "physics.js"

    script = textwrap.dedent(
        f"""
        const {{ PhysicsSystem }} = require({json.dumps(str(physics_js_path))});

        const physics = new PhysicsSystem({{}});
        physics.setMap({{
          width: 5,
          height: 5,
          tile_size: 32,
          tile_grid: [
            [0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0],
            [0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0]
          ],
          tile_defs: {{
            "1": {{
              block_mask: 2,
              sprite: null,
              color: {{ r: 40, g: 40, b: 40 }}
            }}
          }}
        }});

        const actors = [
          {{
            uid: "hero",
            type: "Player",
            x: 48,
            y: 48,
            w: 20,
            h: 20,
            active: true,
            block_mask: 1
          }}
        ];

        physics.syncBodiesFromActors(actors, false);
        physics.integrate(0);
        const overlaps = physics.detectTileOverlaps(actors);
        console.log(JSON.stringify(overlaps));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values == [{"actorUid": "hero", "tileX": 1, "tileY": 1, "tileMask": 2}]


def test_parented_actor_move_does_not_push_parent(tmp_path):
    root = Path(__file__).resolve().parent.parent
    physics_ts_path = root / "nanocalibur" / "runtime" / "canvas" / "physics.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(physics_ts_path),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    physics_js_path = compiled_dir / "physics.js"

    script = textwrap.dedent(
        f"""
        const {{ PhysicsSystem }} = require({json.dumps(str(physics_js_path))});

        const physics = new PhysicsSystem({{}});
        physics.setMap({{
          width: 20,
          height: 20,
          tile_size: 32,
          tile_grid: Array.from({{ length: 20 }}, () => Array.from({{ length: 20 }}, () => 0)),
          tile_defs: {{}}
        }});

        const actors = [
          {{
            uid: "hero",
            type: "Player",
            x: 100,
            y: 100,
            w: 32,
            h: 32,
            active: true,
            block_mask: 1
          }},
          {{
            uid: "coin_pet",
            type: "Coin",
            x: 128,
            y: 100,
            w: 16,
            h: 16,
            active: true,
            block_mask: 1,
            parent: "hero"
          }}
        ];

        physics.syncBodiesFromActors(actors, false);
        physics.integrate(0);

        // Simulate a direct post-action move of the child into the parent.
        actors[1].x = 108;
        physics.syncBodiesFromActors(actors, true);
        physics.resolvePostActionSolidCollisions();
        physics.writeBodiesToActors(actors);

        console.log(JSON.stringify({{
          heroX: actors[0].x,
          petX: actors[1].x
        }}));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["heroX"] == 100
    assert values["petX"] == 108


def test_moving_dynamic_actor_does_not_displace_idle_dynamic_actor(tmp_path):
    root = Path(__file__).resolve().parent.parent
    physics_ts_path = root / "nanocalibur" / "runtime" / "canvas" / "physics.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(physics_ts_path),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    physics_js_path = compiled_dir / "physics.js"

    script = textwrap.dedent(
        f"""
        const {{ PhysicsSystem }} = require({json.dumps(str(physics_js_path))});

        const physics = new PhysicsSystem({{}});
        physics.setMap({{
          width: 20,
          height: 20,
          tile_size: 32,
          tile_grid: Array.from({{ length: 20 }}, () => Array.from({{ length: 20 }}, () => 0)),
          tile_defs: {{}}
        }});

        const actors = [
          {{
            uid: "hero_a",
            type: "Player",
            x: 100,
            y: 100,
            w: 32,
            h: 32,
            vx: 120,
            vy: 0,
            active: true,
            block_mask: 1
          }},
          {{
            uid: "hero_b",
            type: "Player",
            x: 136,
            y: 100,
            w: 32,
            h: 32,
            vx: 0,
            vy: 0,
            active: true,
            block_mask: 1
          }}
        ];

        physics.syncBodiesFromActors(actors, false);
        physics.integrate(0.1);
        physics.resolvePostActionSolidCollisions();
        physics.writeBodiesToActors(actors);

        console.log(JSON.stringify({{
          heroAX: actors[0].x,
          heroBX: actors[1].x
        }}));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["heroBX"] == 136
    assert values["heroAX"] < 112


def test_parented_actor_touching_parent_does_not_block_parent_motion(tmp_path):
    root = Path(__file__).resolve().parent.parent
    physics_ts_path = root / "nanocalibur" / "runtime" / "canvas" / "physics.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(physics_ts_path),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    physics_js_path = compiled_dir / "physics.js"

    script = textwrap.dedent(
        f"""
        const {{ PhysicsSystem }} = require({json.dumps(str(physics_js_path))});

        const physics = new PhysicsSystem({{}});
        physics.setMap({{
          width: 20,
          height: 20,
          tile_size: 32,
          tile_grid: Array.from({{ length: 20 }}, () => Array.from({{ length: 20 }}, () => 0)),
          tile_defs: {{}}
        }});

        const actors = [
          {{
            uid: "hero",
            type: "Player",
            x: 100,
            y: 100,
            w: 32,
            h: 32,
            vx: 100,
            vy: 0,
            active: true,
            block_mask: 1
          }},
          {{
            uid: "coin_pet",
            type: "Coin",
            x: 116,
            y: 100,
            w: 16,
            h: 16,
            vx: 0,
            vy: 0,
            active: true,
            block_mask: 1,
            parent: "hero"
          }}
        ];

        physics.syncBodiesFromActors(actors, false);
        physics.integrate(0.1);
        physics.resolvePostActionSolidCollisions();
        physics.writeBodiesToActors(actors);

        console.log(JSON.stringify({{
          heroX: actors[0].x
        }}));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["heroX"] == 110


def test_parented_actor_blocks_non_parent_actor(tmp_path):
    root = Path(__file__).resolve().parent.parent
    physics_ts_path = root / "nanocalibur" / "runtime" / "canvas" / "physics.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(physics_ts_path),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    physics_js_path = compiled_dir / "physics.js"

    script = textwrap.dedent(
        f"""
        const {{ PhysicsSystem }} = require({json.dumps(str(physics_js_path))});

        const physics = new PhysicsSystem({{}});
        physics.setMap({{
          width: 20,
          height: 20,
          tile_size: 32,
          tile_grid: Array.from({{ length: 20 }}, () => Array.from({{ length: 20 }}, () => 0)),
          tile_defs: {{}}
        }});

        const actors = [
          {{
            uid: "hero_parent",
            type: "Player",
            x: 100,
            y: 100,
            w: 32,
            h: 32,
            active: true,
            block_mask: 1
          }},
          {{
            uid: "coin_pet",
            type: "Coin",
            x: 128,
            y: 100,
            w: 16,
            h: 16,
            active: true,
            block_mask: 1,
            parent: "hero_parent"
          }},
          {{
            uid: "hero_other",
            type: "Player",
            x: 138,
            y: 100,
            w: 32,
            h: 32,
            active: true,
            block_mask: 1
          }}
        ];

        physics.syncBodiesFromActors(actors, false);
        physics.integrate(0);
        physics.resolvePostActionSolidCollisions();
        physics.writeBodiesToActors(actors);

        console.log(JSON.stringify({{
          petX: actors[1].x,
          otherX: actors[2].x,
          distance: Math.abs(actors[1].x - actors[2].x)
        }}));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["petX"] == 128
    assert values["distance"] >= 24
    assert values["otherX"] != 138


def test_blocked_parented_child_rolls_back_parent_motion(tmp_path):
    root = Path(__file__).resolve().parent.parent
    physics_ts_path = root / "nanocalibur" / "runtime" / "canvas" / "physics.ts"
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "npx",
            "-p",
            "typescript",
            "tsc",
            str(physics_ts_path),
            "--target",
            "ES2020",
            "--module",
            "commonjs",
            "--outDir",
            str(compiled_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    physics_js_path = compiled_dir / "physics.js"

    script = textwrap.dedent(
        f"""
        const {{ PhysicsSystem }} = require({json.dumps(str(physics_js_path))});

        const physics = new PhysicsSystem({{}});
        physics.setMap({{
          width: 10,
          height: 10,
          tile_size: 32,
          tile_grid: [
            [0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,1,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0]
          ],
          tile_defs: {{
            "1": {{
              block_mask: 2,
              sprite: null,
              color: {{ r: 40, g: 40, b: 40 }}
            }}
          }}
        }});

        const actors = [
          {{
            uid: "hero",
            type: "Player",
            x: 120,
            y: 112,
            w: 32,
            h: 32,
            vx: 100,
            vy: 0,
            active: true,
            block_mask: 1
          }},
          {{
            uid: "coin_pet",
            type: "Coin",
            x: 152,
            y: 112,
            w: 16,
            h: 16,
            vx: 0,
            vy: 0,
            active: true,
            block_mask: 1,
            parent: "hero"
          }}
        ];

        // Frame 1
        physics.syncBodiesFromActors(actors, false);
        physics.integrate(0.1);
        physics.writeBodiesToActors(actors);
        actors[1].x += 10;
        physics.syncBodiesFromActors(actors, true);
        physics.resolvePostActionSolidCollisions();
        physics.writeBodiesToActors(actors);

        const afterFirst = {{
          heroX: actors[0].x,
          petX: actors[1].x,
          heroVx: actors[0].vx
        }};

        // Frame 2 with same attempted movement; should remain stable.
        actors[0].vx = 100;
        physics.syncBodiesFromActors(actors, false);
        physics.integrate(0.1);
        physics.writeBodiesToActors(actors);
        actors[1].x += 10;
        physics.syncBodiesFromActors(actors, true);
        physics.resolvePostActionSolidCollisions();
        physics.writeBodiesToActors(actors);

        console.log(JSON.stringify({{
          afterFirst,
          afterSecond: {{
            heroX: actors[0].x,
            petX: actors[1].x,
            heroVx: actors[0].vx
          }}
        }}));
        """
    )

    proc = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(proc.stdout.strip())
    assert values["afterFirst"]["heroX"] == 120
    assert values["afterFirst"]["petX"] == 152
    assert values["afterFirst"]["heroVx"] == 0
    assert values["afterSecond"]["heroX"] == 120
    assert values["afterSecond"]["petX"] == 152
    assert values["afterSecond"]["heroVx"] == 0
