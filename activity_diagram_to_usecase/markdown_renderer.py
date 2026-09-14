from __future__ import annotations

from html import escape
from pathlib import Path

from .models import FlowItem, FlowSection, UseCase


def render_markdown(use_case: UseCase, output_path: str | Path) -> Path:
    lines = [f"# {escape(use_case.name)}", "", "<table>", *table_rows(use_case), "</table>", ""]
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def render_merged_markdown(use_cases: list[UseCase], output_path: str | Path) -> Path:
    lines: list[str] = ["# Use Case Specifications", ""]
    for index, use_case in enumerate(use_cases):
        if index:
            lines.extend(["", "---", ""])
        lines.extend([f"## {escape(use_case.name)}", "", "<table>", *table_rows(use_case), "</table>"])
    lines.append("")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def table_rows(use_case: UseCase) -> list[str]:
    rows: list[str] = []
    rows.append(_merged_row("Use case name:", use_case.name))
    rows.append(_merged_row("Brief description:", use_case.description))
    rows.append(_merged_row("Primary actor:", use_case.primary_actor))
    rows.append(
        _merged_row(
            "Secondary actors:",
            ", ".join(use_case.secondary_actors) if use_case.secondary_actors else "None",
        )
    )
    rows.append(_condition_row("Precondition:", use_case.preconditions))
    rows.append(_condition_row("Postcondition:", use_case.postconditions))
    rows.append(_merged_row("Main flow:", "", SECTION=True))
    rows.extend(["<tr><th>Actor</th><th>System</th></tr>", *flow_rows(use_case.main_flow)])
    rows.append(_merged_row("Alternate flow:", "", SECTION=True))
    rows.extend(section_rows(use_case.alternate_flows))
    rows.append(_merged_row("Exception flow:", "", SECTION=True))
    rows.extend(section_rows(use_case.exception_flows))
    return rows


def section_rows(sections: list[FlowSection]) -> list[str]:
    if not sections:
        return [_merged_row("None.", "")]
    rows: list[str] = []
    for section in sections:
        rows.append(_merged_row(section.title, ""))
        rows.extend(flow_rows(section.items))
    return rows


def flow_rows(items: list[FlowItem]) -> list[str]:
    rows = []
    for item in items:
        text = f"{item.number}. {item.text}" if item.number else item.text
        actor = "" if item.is_system else text
        system = text if item.is_system else ""
        rows.append(
            f"<tr><td>{escape(actor)}</td><td>{escape(system)}</td></tr>"
        )
    return rows


def _condition_row(label: str, values: list[str]) -> str:
    bullets = "".join(f"<li>{escape(value)}</li>" for value in values)
    return f'<tr><td colspan="2"><b>{escape(label)}</b><ul>{bullets}</ul></td></tr>'


def _merged_row(label: str, value: str, SECTION: bool = False) -> str:
    if SECTION:
        return f'<tr><td colspan="2"><b>{escape(label)}</b></td></tr>'
    content = f"<b>{escape(label)}</b>"
    if value:
        content += f" {escape(value)}"
    return f'<tr><td colspan="2">{content}</td></tr>'
