import json
import textwrap

from exporter import export_project


def test_export_project_writes_spec_and_logic_files(tmp_path):
    source = textwrap.dedent(
        """
        class Player(ActorModel):
            life: int
            x: int
            y: int

        def heal(player: Player["main_character"], amount: Global["heal"]):
            player.life = player.life + amount

        def is_dead(player: Player) -> bool:
            return player.life <= 0

        game = Game()
        game.add_global("heal", 2)
        game.add_actor(Player, "main_character", life=1, x=5, y=6)
        game.add_rule(KeyboardCondition.is_pressed("A"), heal)
        game.add_rule(LogicalRelated(is_dead, Any(Player)), heal)
        game.set_map(TileMap(width=8, height=8, tile_size=16, solid=[(1, 1)]))
        game.set_camera(Camera.fixed(100, 200))
        """
    )

    export_project(source, str(tmp_path))

    spec_path = tmp_path / "game_spec.json"
    ir_path = tmp_path / "game_ir.json"
    ts_path = tmp_path / "game_logic.ts"
    js_path = tmp_path / "game_logic.js"
    esm_path = tmp_path / "game_logic.mjs"
    assert spec_path.exists()
    assert ir_path.exists()
    assert ts_path.exists()
    assert js_path.exists()
    assert esm_path.exists()

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec["schemas"]["Player"]["life"] == "int"
    assert spec["map"]["tile_size"] == 16
    assert spec["camera"]["mode"] == "fixed"
    assert spec["rules"][0]["condition"]["kind"] == "keyboard"
    assert spec["rules"][0]["condition"]["phase"] == "on"
    assert spec["predicates"][0]["name"] == "is_dead"

    ir_data = json.loads(ir_path.read_text(encoding="utf-8"))
    assert ir_data["actions"][0]["name"] == "heal"
    assert ir_data["predicates"][0]["name"] == "is_dead"
