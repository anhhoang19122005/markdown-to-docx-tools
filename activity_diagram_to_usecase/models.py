from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


@dataclass
class ActivityNode:
    text: str
    lane: str
    line: int = 0


@dataclass
class StartNode:
    line: int = 0


@dataclass
class StopNode:
    line: int = 0


@dataclass
class NoteNode:
    text: str
    lane: str
    inline: bool = False
    line: int = 0


@dataclass
class Branch:
    label: str
    nodes: list["Node"] = field(default_factory=list)


@dataclass
class DecisionNode:
    condition: str
    branches: list[Branch] = field(default_factory=list)
    line: int = 0


@dataclass
class WhileNode:
    condition: str
    body: list["Node"] = field(default_factory=list)
    line: int = 0


@dataclass
class ForkNode:
    branches: list[list["Node"]] = field(default_factory=list)
    line: int = 0


Node = Union[ActivityNode, StartNode, StopNode, NoteNode, DecisionNode, WhileNode, ForkNode]


@dataclass
class Diagram:
    title: str
    nodes: list[Node]
    notes: list[NoteNode] = field(default_factory=list)
    source_path: str | None = None
    block_index: int = 1
    description: str | None = None
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class FlowItem:
    lane: str
    text: str
    number: str = ""

    @property
    def is_system(self) -> bool:
        return self.lane.strip().casefold() == "system"


@dataclass
class FlowSection:
    kind: str
    title: str
    items: list[FlowItem] = field(default_factory=list)
    origin_step: int | None = None
    guard: str = ""


@dataclass
class UseCase:
    name: str
    original_title: str
    description: str
    primary_actor: str
    secondary_actors: list[str]
    preconditions: list[str]
    postconditions: list[str]
    main_flow: list[FlowItem]
    alternate_flows: list[FlowSection] = field(default_factory=list)
    exception_flows: list[FlowSection] = field(default_factory=list)
    source_path: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    diagram: Diagram
    use_case: UseCase
    warnings: list[str] = field(default_factory=list)
