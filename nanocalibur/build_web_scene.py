#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nanocalibur.exporter import export_project


GENERATED_DIR_NAME = "nanocalibur_generated"
TEMPLATES_DIR = ROOT / "nanocalibur" / "templates" / "web_bundle"


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_template(filename: str) -> str:
    template_path = TEMPLATES_DIR / filename
    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")
    return template_path.read_text(encoding="utf-8")


def build_web_input(scene_path: Path, output_dir: Path) -> Path:
    if not scene_path.exists():
        raise FileNotFoundError(f"Scene file not found: {scene_path}")

    source = scene_path.read_text(encoding="utf-8")
    src_dir = output_dir / "src"
    generated_dir = src_dir / GENERATED_DIR_NAME

    generated_dir.mkdir(parents=True, exist_ok=True)

    export_project(source, str(generated_dir), source_path=str(scene_path))

    runtime_dir = ROOT / "nanocalibur" / "runtime"
    for runtime_file in (
        "interpreter.ts",
        "runtime_core.ts",
        "canvas_host.ts",
        "headless_host.ts",
        "headless_http_server.ts",
        "symbolic_renderer.ts",
    ):
        shutil.copy2(runtime_dir / runtime_file, generated_dir / runtime_file)
    canvas_runtime_dir = runtime_dir / "canvas"
    generated_canvas_dir = generated_dir / "canvas"
    if generated_canvas_dir.exists():
        shutil.rmtree(generated_canvas_dir)
    shutil.copytree(canvas_runtime_dir, generated_canvas_dir)

    _write_text(generated_dir / "bridge.ts", _read_template("bridge.ts"))
    _write_text(generated_dir / "index.ts", _read_template("index.ts"))
    _write_text(generated_dir / "node.ts", _read_template("node.ts"))
    _write_text(
        output_dir / "README.generated.md",
        _read_template("README.generated.md"),
    )

    return generated_dir


def sync_into_web_project(bundle_dir: Path, project_dir: Path) -> Path:
    src_dir = project_dir / "src"
    if not src_dir.exists():
        raise FileNotFoundError(f"Web project src directory not found: {src_dir}")

    target_dir = src_dir / GENERATED_DIR_NAME
    if bundle_dir.resolve() == target_dir.resolve():
        return target_dir
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(bundle_dir, target_dir)
    return target_dir


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compile a NanoCalibur Python scene and generate a browser-consumable "
            "TypeScript input bundle."
        )
    )
    parser.add_argument(
        "scene",
        help="Path to the Python DSL scene file to compile.",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "build" / GENERATED_DIR_NAME),
        help="Directory where the generated bundle will be written.",
    )
    parser.add_argument(
        "--project",
        default=None,
        help=(
            "Optional project root directory. If provided, the generated bundle "
            "is copied to <project>/src/nanocalibur_generated."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    scene_path = Path(args.scene).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(exist_ok=True)

    bundle_dir = build_web_input(scene_path, output_dir)

    print(f"Generated NanoCalibur bundle: {bundle_dir}")
    print(f"- {bundle_dir / 'game_spec.json'}")
    print(f"- {bundle_dir / 'game_ir.json'}")
    print(f"- {bundle_dir / 'game_logic.ts'}")
    print(f"- {bundle_dir / 'interpreter.ts'}")
    print(f"- {bundle_dir / 'runtime_core.ts'}")
    print(f"- {bundle_dir / 'canvas_host.ts'}")
    print(f"- {bundle_dir / 'headless_host.ts'}")
    print(f"- {bundle_dir / 'headless_http_server.ts'}")
    print(f"- {bundle_dir / 'symbolic_renderer.ts'}")
    print(f"- {bundle_dir / 'bridge.ts'}")
    print(f"- {bundle_dir / 'index.ts'}")
    print(f"- {bundle_dir / 'node.ts'}")

    if args.project:
        project_dir = Path(args.project).resolve()
        target_dir = sync_into_web_project(bundle_dir, project_dir)
        print(f"Copied bundle to project: {target_dir}")


if __name__ == "__main__":
    main()
