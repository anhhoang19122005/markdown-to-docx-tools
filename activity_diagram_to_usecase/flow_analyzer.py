from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import (
    ActivityNode,
    AnalysisResult,
    DecisionNode,
    Diagram,
    FlowItem,
    FlowSection,
    ForkNode,
    Node,
    NoteNode,
    StartNode,
    StopNode,
    UseCase,
    WhileNode,
)

_ERROR_SIGNALS = (
    "invalid",
    "not found",
    "not available",
    "duplicate",
    "unauthorized",
    "forbidden",
    "reject",
    "error",
    "fail",
    "failure",
    "exceed",
    "insufficient",
    "lacks",
    "denied",
    "unavailable",
    "does not exist",
)
_OPTIONAL_SIGNALS = (
    "optional",
    "wants",
    "choose",
    "selected",
    "select",
    "voucher",
    "invoice",
    "promotion",
    "discount",
    "round trip",
    "alternative",
    "include",
    "enable",
)
_NORMAL_LABELS = {
    "no",
    "none",
    "default",
    "continue",
    "proceed",
    "valid",
    "available",
    "authorized",
    "unique",
    "success",
    "saved",
}


@dataclass
class _State:
    main: list[FlowItem] = field(default_factory=list)
    alternate: list[FlowSection] = field(default_factory=list)
    exception: list[FlowSection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def analyze_diagram(diagram: Diagram) -> AnalysisResult:
    state = _State(warnings=list(diagram.warnings))
    _process_sequence(diagram.nodes, state)
    primary, secondary = _actors(diagram.nodes)
    primary_display = primary or "Not determined from Activity Diagram"
    preconditions = diagram.preconditions or ["Not determined from Activity Diagram."]
    name = _use_case_name(diagram.title)
    postconditions = diagram.postconditions or _infer_postconditions(name, state.main)
    description = diagram.description or _infer_description(name, primary_display)
    use_case = UseCase(
        name=name,
        original_title=diagram.title,
        description=description,
        primary_actor=primary_display,
        secondary_actors=secondary,
        preconditions=preconditions,
        postconditions=postconditions,
        main_flow=state.main,
        alternate_flows=state.alternate,
        exception_flows=state.exception,
        source_path=diagram.source_path,
        warnings=state.warnings,
    )
    return AnalysisResult(diagram=diagram, use_case=use_case, warnings=state.warnings)


def _process_sequence(nodes: list[Node], state: _State) -> bool:
    for node in nodes:
        if isinstance(node, ActivityNode):
            state.main.append(
                FlowItem(lane=node.lane, text=node.text, number=str(len(state.main) + 1))
            )
        elif isinstance(node, StopNode):
            return False
        elif isinstance(node, (StartNode, NoteNode)):
            continue
        elif isinstance(node, WhileNode):
            if not _process_sequence(node.body, state):
                state.warnings.append(
                    f"Loop at line {node.line} contains a terminating path; represented once."
                )
        elif isinstance(node, ForkNode):
            outcomes = [_process_sequence(branch, state) for branch in node.branches]
            if outcomes and not all(outcomes):
                return False
        elif isinstance(node, DecisionNode):
            if not _process_decision(node, state):
                return False
    return True


def _process_decision(node: DecisionNode, state: _State) -> bool:
    if not node.branches:
        state.warnings.append(f"Decision at line {node.line} has no branches.")
        return True

    exception_indices = [
        index
        for index, branch in enumerate(node.branches)
        if not _has_continuing_path(branch.nodes)
        or _looks_errorish_at_branch_level(branch.nodes)
    ]
    candidates = [
        index for index in range(len(node.branches)) if index not in exception_indices
    ]

    for index in exception_indices:
        _add_section(
            state.exception,
            "Exception",
            node,
            node.branches[index],
            len(state.exception) + 1,
            len(state.main),
        )

    if not candidates:
        state.warnings.append(
            f"Decision at line {node.line} has no clearly continuing branch; "
            "all branches were classified as exceptions."
        )
        return False

    main_index = _choose_main_branch(node, candidates, state)
    for index in candidates:
        if index == main_index:
            continue
        _add_section(
            state.alternate,
            "Alternate",
            node,
            node.branches[index],
            len(state.alternate) + 1,
            None,
        )
    return _process_sequence(node.branches[main_index].nodes, state)


def _add_section(
    target: list[FlowSection],
    kind: str,
    decision: DecisionNode,
    branch: object,
    section_number: int,
    origin_step: int | None,
) -> None:
    items = _flatten_actions(branch.nodes)
    for index, item in enumerate(items, start=1):
        if kind == "Exception":
            item.number = f"{origin_step or 1}.{section_number}.{index}"
        else:
            item.number = f"{section_number}.{index}"
    target.append(
        FlowSection(
            kind=kind,
            title=f"{kind} {section_number}: {decision.condition} = {branch.label}",
            items=items,
            origin_step=origin_step if kind == "Exception" else None,
            guard=f"{decision.condition} = {branch.label}",
        )
    )


def _choose_main_branch(
    decision: DecisionNode,
    candidates: list[int],
    state: _State,
) -> int:
    if len(candidates) == 1:
        return candidates[0]
    metrics = {
        index: len(_flatten_actions(decision.branches[index].nodes))
        for index in candidates
    }
    empty = [index for index in candidates if metrics[index] == 0]
    if len(empty) == 1:
        return empty[0]

    normal = [
        index
        for index in candidates
        if decision.branches[index].label.strip().casefold() in _NORMAL_LABELS
    ]
    if len(normal) == 1:
        return normal[0]

    no_result = [
        index
        for index in candidates
        if decision.branches[index].label.strip().casefold().startswith("no ")
    ]
    if len(no_result) == 1 and re.search(r"\b(exists?|already)\b", decision.condition, re.IGNORECASE):
        return no_result[0]

    condition = decision.condition.casefold()
    if _contains_signal(condition, _OPTIONAL_SIGNALS):
        state.warnings.append(
            f"Decision at line {decision.line} has multiple continuing optional branches; "
            "selected the first continuing branch as Main Flow."
        )
        return candidates[0]

    state.warnings.append(
        f"Ambiguous rejoining decision at line {decision.line}: "
        f'"{decision.condition}". No branch is structurally preferred; '
        "selected the first continuing branch as Main Flow and retained the others as Alternate Flow."
    )
    return candidates[0]


def _flatten_actions(nodes: list[Node]) -> list[FlowItem]:
    items: list[FlowItem] = []
    for node in nodes:
        if isinstance(node, ActivityNode):
            items.append(FlowItem(lane=node.lane, text=node.text))
        elif isinstance(node, WhileNode):
            items.extend(_flatten_actions(node.body))
        elif isinstance(node, ForkNode):
            for branch in node.branches:
                items.extend(_flatten_actions(branch))
        elif isinstance(node, DecisionNode):
            for branch in node.branches:
                items.extend(_flatten_actions(branch.nodes))
    return items


def _contains_stop(nodes: list[Node]) -> bool:
    for node in nodes:
        if isinstance(node, StopNode):
            return True
        if isinstance(node, WhileNode) and _contains_stop(node.body):
            return True
        if isinstance(node, ForkNode) and any(_contains_stop(branch) for branch in node.branches):
            return True
        if isinstance(node, DecisionNode) and any(
            _contains_stop(branch.nodes) for branch in node.branches
        ):
            return True
    return False


def _has_continuing_path(nodes: list[Node]) -> bool:
    """Whether at least one route through the sequence reaches its successor."""
    for node in nodes:
        if isinstance(node, StopNode):
            return False
        if isinstance(node, DecisionNode):
            if not any(_has_continuing_path(branch.nodes) for branch in node.branches):
                return False
        elif isinstance(node, WhileNode):
            # A loop may complete without entering its body.
            continue
        elif isinstance(node, ForkNode):
            if any(not _has_continuing_path(branch) for branch in node.branches):
                return False
    return True


def _looks_errorish(nodes: list[Node]) -> bool:
    text = " ".join(item.text for item in _flatten_actions(nodes)).casefold()
    return _contains_signal(text, _ERROR_SIGNALS)


def _looks_errorish_at_branch_level(nodes: list[Node]) -> bool:
    """Do not let an error in a nested decision classify its parent branch."""
    text = " ".join(
        node.text for node in nodes if isinstance(node, ActivityNode)
    ).casefold()
    return _contains_signal(text, _ERROR_SIGNALS)


def _contains_signal(text: str, signals: tuple[str, ...]) -> bool:
    return any(
        re.search(rf"\b{re.escape(signal)}\b", text, re.IGNORECASE)
        for signal in signals
    )


def _actors(nodes: list[Node]) -> tuple[str | None, list[str]]:
    lanes: list[str] = []

    def visit(items: list[Node]) -> None:
        for node in items:
            if isinstance(node, ActivityNode):
                lane = node.lane.strip()
                if lane and lane.casefold() != "system" and lane not in lanes:
                    lanes.append(lane)
            elif isinstance(node, DecisionNode):
                for branch in node.branches:
                    visit(branch.nodes)
            elif isinstance(node, WhileNode):
                visit(node.body)
            elif isinstance(node, ForkNode):
                for branch in node.branches:
                    visit(branch)

    visit(nodes)
    return (lanes[0] if lanes else None, lanes[1:])


def _use_case_name(title: str) -> str:
    parts = re.split(r"\s+-\s+", title.strip())
    return parts[-1].strip() if parts else title.strip()


def _infer_description(name: str, actor: str) -> str:
    subject = actor if actor != "Not determined from Activity Diagram" else "the user"
    action = name[:1].lower() + name[1:]
    return f"The system allows {subject} to {action}."


def _infer_postconditions(name: str, main_flow: list[FlowItem]) -> list[str]:
    if not main_flow:
        return ["Not determined from Activity Diagram."]
    ending = " ".join(item.text.casefold() for item in main_flow[-3:])
    if not re.search(
        r"\b(create|created|save|saved|complete|completed|success|successful|return|view)\b",
        ending,
    ):
        return ["Not determined from Activity Diagram."]
    match = re.match(r"create\s+(?:a|an|the)\s+(.+)", name, re.IGNORECASE)
    if match:
        return [f"{match.group(1).capitalize()} is created successfully."]
    return ["The requested operation completes successfully."]


def debug_text(result: AnalysisResult) -> str:
    use_case = result.use_case
    lines = [
        "=== USE CASE ===",
        "",
        f"Name: {use_case.name}",
        f"Original title: {use_case.original_title}",
        f"Primary Actor: {use_case.primary_actor}",
        f"Secondary Actors: {', '.join(use_case.secondary_actors) or 'None'}",
        "",
        "Preconditions:",
        *[f"- {item}" for item in use_case.preconditions],
        "",
        "Postconditions:",
        *[f"- {item}" for item in use_case.postconditions],
        "",
        "=== MAIN FLOW ===",
    ]
    lines.extend(
        f"{item.number} [{_role(item.lane)}] {item.text}" for item in use_case.main_flow
    )
    lines.extend(["", "=== ALTERNATE FLOWS ==="])
    if use_case.alternate_flows:
        for section in use_case.alternate_flows:
            lines.append(section.title)
            lines.extend(
                f"{item.number} [{_role(item.lane)}] {item.text}" for item in section.items
            )
    else:
        lines.append("None")
    lines.extend(["", "=== EXCEPTION FLOWS ==="])
    if use_case.exception_flows:
        for section in use_case.exception_flows:
            origin = f" from Main Step {section.origin_step}" if section.origin_step else ""
            lines.append(f"{section.title}{origin}")
            lines.extend(
                f"{item.number} [{_role(item.lane)}] {item.text}" for item in section.items
            )
    else:
        lines.append("None")
    lines.extend(["", "=== WARNINGS ==="])
    if use_case.warnings:
        lines.extend(f"- {warning}" for warning in use_case.warnings)
    else:
        lines.append("None")
    return "\n".join(lines) + "\n"


def _role(lane: str) -> str:
    return "System" if lane.strip().casefold() == "system" else "Actor"
