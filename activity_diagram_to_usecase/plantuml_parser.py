from __future__ import annotations

import re
from pathlib import Path

from .models import (
    ActivityNode,
    Branch,
    DecisionNode,
    Diagram,
    ForkNode,
    NoteNode,
    Node,
    StartNode,
    StopNode,
    WhileNode,
)

_BLOCK_RE = re.compile(r"@startuml\b.*?@enduml\b", re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(r"^\s*title\s+(.+?)\s*$", re.IGNORECASE)
_IF_RE = re.compile(
    r"^\s*if\s*\((?P<condition>.*?)\)\s*(?:then\s*\((?P<label>.*?)\))?\s*$",
    re.IGNORECASE,
)
_ELSEIF_RE = re.compile(
    r"^\s*elseif\s*\((?P<condition>.*?)\)\s*(?:then\s*\((?P<label>.*?)\))?\s*$",
    re.IGNORECASE,
)
_WHILE_RE = re.compile(
    r"^\s*while\s*\((?P<condition>.*?)\)\s*(?:is\s*\((?P<label>.*?)\))?\s*$",
    re.IGNORECASE,
)
_ELSE_RE = re.compile(r"^\s*else(?:\s*\((?P<label>.*)\))?\s*$", re.IGNORECASE)
_ENDWHILE_RE = re.compile(r"^\s*endwhile(?:\s*\(.*\))?\s*$", re.IGNORECASE)
_LANE_RE = re.compile(r"^\s*\|(?P<lane>[^|]+)\|\s*$")


def extract_plantuml_blocks(text: str) -> list[str]:
    """Return complete PlantUML blocks without downloading includes."""
    blocks = _BLOCK_RE.findall(text)
    starts = len(re.findall(r"@startuml\b", text, re.IGNORECASE))
    if starts and len(blocks) != starts:
        raise ValueError("Unclosed @startuml block")
    return blocks


def parse_text(text: str, source_path: str | None = None) -> list[Diagram]:
    blocks = extract_plantuml_blocks(text)
    return [
        _parse_block(block, source_path=source_path, block_index=index)
        for index, block in enumerate(blocks, start=1)
    ]


def parse_file(path: str | Path) -> list[Diagram]:
    file_path = Path(path)
    return parse_text(
        file_path.read_text(encoding="utf-8-sig"),
        source_path=str(file_path),
    )


class _Parser:
    def __init__(self, block: str) -> None:
        self.lines = block.splitlines()
        self.index = 0
        self.lane = ""
        self.title = ""
        self.notes: list[NoteNode] = []
        self.warnings: list[str] = []

    def parse(self) -> tuple[str, list[Node], list[NoteNode], list[str]]:
        nodes = self._parse_sequence(set())
        return self.title, nodes, self.notes, self.warnings

    def _parse_sequence(self, stop_tokens: set[str]) -> list[Node]:
        nodes: list[Node] = []
        while self.index < len(self.lines):
            raw = self.lines[self.index]
            stripped = raw.strip()
            lowered = stripped.casefold()
            token = self._token(lowered)
            if token in stop_tokens:
                break
            if not stripped or stripped.startswith("'") or stripped.startswith("//"):
                self.index += 1
                continue
            lane_match = _LANE_RE.match(stripped)
            if lane_match:
                self.lane = lane_match.group("lane").strip()
                self.index += 1
                continue
            title_match = _TITLE_RE.match(stripped)
            if title_match:
                self.title = title_match.group(1).strip()
                self.index += 1
                continue
            if lowered.startswith("note"):
                nodes.append(self._parse_note())
                continue
            if lowered.startswith("if"):
                nodes.append(self._parse_if())
                continue
            if lowered.startswith("while"):
                nodes.append(self._parse_while())
                continue
            if lowered == "fork":
                nodes.append(self._parse_fork())
                continue
            if lowered == "start":
                nodes.append(StartNode(line=self.index + 1))
                self.index += 1
                continue
            if lowered in {"stop", "detach", "kill"}:
                nodes.append(StopNode(line=self.index + 1))
                self.index += 1
                continue
            if stripped.startswith(":"):
                nodes.append(self._parse_activity())
                continue
            # Presentation or unsupported non-flow syntax is intentionally ignored.
            self.index += 1
        return nodes

    def _parse_activity(self) -> ActivityNode:
        line = self.index + 1
        chunks = [self.lines[self.index].strip()[1:]]
        while ";" not in chunks[-1] and self.index + 1 < len(self.lines):
            self.index += 1
            chunks.append(self.lines[self.index].strip())
        text = " ".join(chunks)
        if ";" in text:
            text = text.split(";", 1)[0]
        self.index += 1
        return ActivityNode(text=_clean_text(text), lane=self.lane, line=line)

    def _parse_if(self) -> DecisionNode:
        line = self.index + 1
        match = _IF_RE.match(self.lines[self.index].strip())
        if not match:
            self.warnings.append(f"Unparsed if statement at line {line}")
            self.index += 1
            return DecisionNode(condition="", branches=[], line=line)
        condition = _clean_text(match.group("condition"))
        first_label = _clean_text(match.group("label") or "Yes")
        self.index += 1
        branches = [
            Branch(first_label, self._parse_sequence({"elseif", "else", "endif"}))
        ]
        if self._token_at_current() == "elseif":
            branches.append(Branch("No", [self._parse_elseif()]))
        elif self._token_at_current() == "else":
            else_match = _ELSE_RE.match(self.lines[self.index].strip())
            else_label = _clean_text(else_match.group("label") if else_match else "") or "No"
            self.index += 1
            branches.append(Branch(else_label, self._parse_sequence({"endif"})))
        else:
            branches.append(Branch("No", []))
        if self._token_at_current() == "endif":
            self.index += 1
        else:
            self.warnings.append(f"Missing endif for decision at line {line}")
        return DecisionNode(condition=condition, branches=branches, line=line)

    def _parse_elseif(self) -> DecisionNode:
        line = self.index + 1
        match = _ELSEIF_RE.match(self.lines[self.index].strip())
        if not match:
            self.warnings.append(f"Unparsed elseif statement at line {line}")
            self.index += 1
            return DecisionNode(condition="", branches=[], line=line)
        condition = _clean_text(match.group("condition"))
        first_label = _clean_text(match.group("label") or "Yes")
        self.index += 1
        branches = [
            Branch(first_label, self._parse_sequence({"elseif", "else", "endif"}))
        ]
        if self._token_at_current() == "elseif":
            branches.append(Branch("No", [self._parse_elseif()]))
        elif self._token_at_current() == "else":
            else_match = _ELSE_RE.match(self.lines[self.index].strip())
            else_label = _clean_text(else_match.group("label") if else_match else "") or "No"
            self.index += 1
            branches.append(Branch(else_label, self._parse_sequence({"endif"})))
        else:
            branches.append(Branch("No", []))
        return DecisionNode(condition=condition, branches=branches, line=line)

    def _parse_while(self) -> WhileNode:
        line = self.index + 1
        match = _WHILE_RE.match(self.lines[self.index].strip())
        if not match:
            self.warnings.append(f"Unparsed while statement at line {line}")
            self.index += 1
            return WhileNode(condition="", body=[], line=line)
        condition = _clean_text(match.group("condition"))
        self.index += 1
        body = self._parse_sequence({"endwhile"})
        if self._token_at_current() == "endwhile":
            self.index += 1
        else:
            self.warnings.append(f"Missing endwhile for loop at line {line}")
        return WhileNode(condition=condition, body=body, line=line)

    def _parse_fork(self) -> ForkNode:
        line = self.index + 1
        self.index += 1
        branches: list[list[Node]] = []
        while self.index < len(self.lines):
            branches.append(self._parse_sequence({"fork again", "end fork"}))
            token = self._token_at_current()
            if token == "fork again":
                self.index += 1
                continue
            if token == "end fork":
                self.index += 1
                break
            self.warnings.append(f"Missing end fork for fork at line {line}")
            break
        return ForkNode(branches=branches, line=line)

    def _parse_note(self) -> NoteNode:
        line = self.index + 1
        header = self.lines[self.index].strip().casefold()
        inline = header != "note"
        self.index += 1
        content: list[str] = []
        while self.index < len(self.lines):
            if self.lines[self.index].strip().casefold() == "end note":
                self.index += 1
                break
            content.append(self.lines[self.index].rstrip())
            self.index += 1
        else:
            self.warnings.append(f"Missing end note for note at line {line}")
        note = NoteNode(
            text="\n".join(content).strip(),
            lane=self.lane,
            inline=inline,
            line=line,
        )
        self.notes.append(note)
        return note

    def _token_at_current(self) -> str:
        if self.index >= len(self.lines):
            return ""
        return self._token(self.lines[self.index].strip().casefold())

    @staticmethod
    def _token(lowered: str) -> str:
        if lowered == "endif":
            return "endif"
        if _ENDWHILE_RE.match(lowered):
            return "endwhile"
        if _ELSEIF_RE.match(lowered):
            return "elseif"
        if lowered == "fork again":
            return "fork again"
        if lowered == "end fork":
            return "end fork"
        if _ELSE_RE.match(lowered):
            return "else"
        return lowered


def _parse_block(
    block: str,
    source_path: str | None,
    block_index: int,
) -> Diagram:
    parser = _Parser(block)
    title, nodes, notes, warnings = parser.parse()
    preconditions, postconditions, description = _note_metadata(notes)
    return Diagram(
        title=title or Path(source_path or "activity").stem,
        nodes=nodes,
        notes=notes,
        source_path=source_path,
        block_index=block_index,
        description=description,
        preconditions=preconditions,
        postconditions=postconditions,
        warnings=warnings,
    )


def _note_metadata(notes: list[NoteNode]) -> tuple[list[str], list[str], str | None]:
    values: dict[str, list[str]] = {
        "precondition": [],
        "postcondition": [],
        "description": [],
    }
    headings = {
        "precondition": "precondition",
        "preconditions": "precondition",
        "pre-condition": "precondition",
        "pre-conditions": "precondition",
        "postcondition": "postcondition",
        "postconditions": "postcondition",
        "post-condition": "postcondition",
        "post-conditions": "postcondition",
        "description": "description",
    }
    for note in notes:
        current: str | None = None
        for raw_line in note.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = re.match(r"^([^:]+):\s*(.*)$", line)
            if match and match.group(1).strip().casefold() in headings:
                current = headings[match.group(1).strip().casefold()]
                if match.group(2).strip():
                    values[current].append(_clean_text(match.group(2)))
                continue
            if current:
                values[current].append(_clean_text(re.sub(r"^[-*•]\s*", "", line)))
    for key in values:
        values[key] = _dedupe(values[key])
    description = " ".join(values["description"]).strip() or None
    return values["precondition"], values["postcondition"], description


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace(r"\n", " ")).strip()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            result.append(value)
            seen.add(key)
    return result
