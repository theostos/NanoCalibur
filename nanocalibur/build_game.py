#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import shutil
import sys
from pathlib import Path
from typing import List


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


def _resolve_module_file(candidate_base: Path) -> Path | None:
    module_file = candidate_base.with_suffix(".py")
    if module_file.exists() and module_file.is_file():
        return module_file.resolve()
    package_init = candidate_base / "__init__.py"
    if package_init.exists() and package_init.is_file():
        return package_init.resolve()
    return None


def _extract_local_import_paths(
    stmt: ast.stmt,
    *,
    project_root: Path,
    current_file: Path,
) -> List[Path]:
    paths: List[Path] = []

    if isinstance(stmt, ast.ImportFrom):
        if stmt.level <= 0:
            return []
        base = current_file.parent
        for _ in range(max(stmt.level - 1, 0)):
            base = base.parent
        if stmt.module:
            target = base.joinpath(*stmt.module.split("."))
            resolved = _resolve_module_file(target)
            if resolved is not None:
                paths.append(resolved)
            return paths
        for alias in stmt.names:
            if alias.name == "*":
                continue
            target = base.joinpath(*alias.name.split("."))
            resolved = _resolve_module_file(target)
            if resolved is not None:
                paths.append(resolved)
        return paths

    if isinstance(stmt, ast.Import):
        for alias in stmt.names:
            target = project_root.joinpath(*alias.name.split("."))
            resolved = _resolve_module_file(target)
            if resolved is not None:
                paths.append(resolved)
    return paths


def _collect_game_source(main_path: Path) -> str:
    if not main_path.exists():
        raise FileNotFoundError(f"Game entry file not found: {main_path}")
    if not main_path.is_file():
        raise FileNotFoundError(f"Game entry path is not a file: {main_path}")

    project_root = main_path.parent.resolve()
    visited: set[Path] = set()
    ordered_sources: list[tuple[Path, str]] = []

    def visit(path: Path) -> None:
        path = path.resolve()
        if path in visited:
            return
        visited.add(path)

        source = path.read_text(encoding="utf-8")
        module = ast.parse(source)

        deps: list[Path] = []
        kept_body: list[ast.stmt] = []
        for stmt in module.body:
            local_deps = _extract_local_import_paths(
                stmt,
                project_root=project_root,
                current_file=path,
            )
            if local_deps:
                deps.extend(local_deps)
                continue
            kept_body.append(stmt)

        for dep in deps:
            visit(dep)

        filtered_module = ast.Module(body=kept_body, type_ignores=[])
        ast.fix_missing_locations(filtered_module)
        ordered_sources.append((path, ast.unparse(filtered_module)))

    visit(main_path)

    chunks: list[str] = []
    for path, chunk in ordered_sources:
        try:
            rel = path.relative_to(project_root)
        except ValueError:
            rel = path
        chunks.append(f"# --- source: {rel} ---\n{chunk}")
    return "\n\n".join(chunks)


def build_web_input(
    main_path: Path,
    output_dir: Path,
    *,
    require_code_blocks: bool,
) -> Path:
    source = _collect_game_source(main_path)
    src_dir = output_dir / "src"
    generated_dir = src_dir / GENERATED_DIR_NAME

    generated_dir.mkdir(parents=True, exist_ok=True)

    export_project(
        source,
        str(generated_dir),
        source_path=str(main_path),
        require_code_blocks=require_code_blocks,
        unboxed_disable_flag="--allow-unboxed",
    )

    runtime_dir = ROOT / "nanocalibur" / "runtime"
    for runtime_file in (
        "interpreter.ts",
        "runtime_core.ts",
        "canvas_host.ts",
        "headless_host.ts",
        "headless_http_server.ts",
        "session_runtime.ts",
        "session_manager.ts",
        "replay_store_sqlite.ts",
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
            "Build a NanoCalibur game from a Python entry module (main.py) "
            "and local imports into a browser-consumable TypeScript bundle."
        )
    )
    parser.add_argument(
        "main",
        help="Path to the Python game entry file (typically main.py).",
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
    parser.add_argument(
        "--allow-unboxed",
        action="store_true",
        help=(
            "Disable strict CodeBlock filtering and keep top-level non-import statements "
            "that are outside any CodeBlock."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    main_path = Path(args.main).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(exist_ok=True)

    bundle_dir = build_web_input(
        main_path,
        output_dir,
        require_code_blocks=not args.allow_unboxed,
    )

    print(f"Generated NanoCalibur bundle: {bundle_dir}")
    print(f"- {bundle_dir / 'game_spec.json'}")
    print(f"- {bundle_dir / 'game_ir.json'}")
    print(f"- {bundle_dir / 'game_logic.ts'}")
    print(f"- {bundle_dir / 'interpreter.ts'}")
    print(f"- {bundle_dir / 'runtime_core.ts'}")
    print(f"- {bundle_dir / 'canvas_host.ts'}")
    print(f"- {bundle_dir / 'headless_host.ts'}")
    print(f"- {bundle_dir / 'headless_http_server.ts'}")
    print(f"- {bundle_dir / 'session_runtime.ts'}")
    print(f"- {bundle_dir / 'session_manager.ts'}")
    print(f"- {bundle_dir / 'replay_store_sqlite.ts'}")
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
