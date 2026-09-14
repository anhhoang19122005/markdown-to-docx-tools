from __future__ import annotations

import argparse
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from activity_diagram_to_usecase.docx_renderer import render_merged, render_use_case
from activity_diagram_to_usecase.flow_analyzer import analyze_diagram, debug_text
from activity_diagram_to_usecase.markdown_renderer import (
    render_markdown,
    render_merged_markdown,
)
from activity_diagram_to_usecase.plantuml_parser import parse_file

SUPPORTED_SUFFIXES = {".puml", ".plantuml", ".md", ".markdown"}


def discover_inputs(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if not input_path.is_dir():
        raise FileNotFoundError(input_path)
    result: list[Path] = []
    for path in sorted(input_path.rglob("*")):
        if path.suffix.casefold() not in SUPPORTED_SUFFIXES:
            continue
        if path.suffix.casefold() in {".md", ".markdown"}:
            text = path.read_text(encoding="utf-8-sig")
            lowered = text.casefold()
            if "@startuml" not in lowered or "@enduml" not in lowered:
                continue
        result.append(path)
    return result


def load_results(paths: list[Path]):
    results = []
    for path in paths:
        for diagram in parse_file(path):
            results.append(analyze_diagram(diagram))
    return results


def convert(input_path: Path, output: Path | None, merged: bool) -> list[Path]:
    paths = discover_inputs(input_path)
    if not paths:
        raise ValueError(f"No PlantUML diagrams found under {input_path}")
    results = load_results(paths)
    if merged:
        target = output or _default_output_dir(input_path)
        if target.suffix.casefold() != ".docx":
            target = target / "UseCaseSpecification.docx"
        docx_path = render_merged([result.use_case for result in results], target)
        markdown_path = docx_path.with_suffix(".md")
        render_merged_markdown([result.use_case for result in results], markdown_path)
        return [markdown_path, docx_path]

    output_path = output
    output_dir = output_path or _default_output_dir(input_path)
    fixed_docx = None
    if output_dir.suffix.casefold() == ".docx":
        if len(results) != 1:
            raise ValueError("--output <file.docx> with multiple diagrams requires --merged")
        fixed_docx = output_dir
        output_dir = output_dir.parent
    generated: list[Path] = []
    input_root = input_path if input_path.is_dir() else input_path.parent
    input_root = input_root.resolve()
    for result in results:
        source = Path(result.use_case.source_path or "activity.md").resolve()
        try:
            relative = source.relative_to(input_root)
        except ValueError:
            relative = Path(source.name)
        if result.diagram.block_index > 1:
            relative = relative.with_name(
                f"{relative.stem}-{result.diagram.block_index}{relative.suffix}"
            )
        if fixed_docx:
            docx_path = fixed_docx
        else:
            docx_path = output_dir / relative.parent / f"{relative.stem}.docx"
        markdown_path = docx_path.with_suffix(".md")
        render_markdown(result.use_case, markdown_path)
        render_use_case(result.use_case, docx_path)
        generated.extend([markdown_path, docx_path])
    return generated


def debug(input_path: Path, output: Path | None) -> list[Path]:
    paths = discover_inputs(input_path)
    if not paths:
        raise ValueError(f"No PlantUML diagrams found under {input_path}")
    results = load_results(paths)
    texts = [debug_text(result) for result in results]
    if output:
        if len(texts) == 1 and output.suffix.casefold() == ".txt":
            targets = [output]
        else:
            targets = [
                output / f"{Path(result.use_case.source_path or 'activity').stem}.debug.txt"
                for result in results
            ]
        for target, content in zip(targets, texts):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return targets
    print("\n".join(texts), end="")
    return []


def _default_output_dir(input_path: Path) -> Path:
    return input_path.parent / "use-case-specifications"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    convert_parser = subparsers.add_parser("convert")
    convert_parser.add_argument("input", type=Path)
    convert_parser.add_argument("--output", type=Path)
    convert_parser.add_argument("--merged", action="store_true")
    debug_parser = subparsers.add_parser("debug")
    debug_parser.add_argument("input", type=Path)
    debug_parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "convert":
            generated = convert(args.input, args.output, args.merged)
            for path in generated:
                print(path)
        else:
            debug(args.input, args.output)
        return 0
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
