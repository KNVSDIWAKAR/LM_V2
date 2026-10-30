"""Load a playbook YAML, validate it, and compile it into a LangGraph.

How the graph is built (the one idea to take away):

* Every `run` node is a plain Python function that returns an `outcome` string.
* The playbook's `routes` map says which node comes next for each outcome.
* So the graph needs only ONE router, `_route`, which reads `state["next"]`.
  A wrapper around each node writes `next` from the YAML, and the edges are generated from
  the YAML too. Change the flow by editing YAML; no `add_conditional_edges` per decision.

Gates and end nodes stop the graph. A gate leaves `paused` in the state (the runner turns it
into a Decision Inbox item); an end node leaves `result`. Resuming after a decision re-enters
the graph at any node through `resume_at`, read by the START router.
"""

import operator
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

import yaml
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, model_validator

from ..core.config import BACKEND_DIR
from ..models.lm_stages import STAGE_BY_NO
from .registry import NODES, load_node_modules

HARNESS_DIR = BACKEND_DIR / "harness"


# --------------------------------------------------------------------------- #
# The YAML, as validated models
# --------------------------------------------------------------------------- #


class NodeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    # A work node: …
    run: str | None = None
    next: str | None = None
    routes: dict[str, str] | None = None
    # … or a gate (a person decides): …
    gate: Literal["human_review"] | None = None
    team: str | None = None
    on_approve: str | None = None
    on_reject: str | None = None
    reason: str | None = None  # shown on the Decision Inbox item when the state has no review_reason
    # … or an end node.
    end: bool = False
    advance: bool = False
    # Gates and end nodes write this to lm_stages.
    status: str | None = None

    @property
    def kind(self) -> str:
        return "run" if self.run else "gate" if self.gate else "end"

    @model_validator(mode="after")
    def one_kind(self) -> "NodeSpec":
        kinds = [bool(self.run), bool(self.gate), self.end]
        if sum(kinds) != 1:
            raise ValueError("a node is exactly one of: run, gate, end")
        if self.run and bool(self.next) == bool(self.routes):
            raise ValueError("a run node needs either `next` or `routes`")
        if self.gate and not (self.on_approve and self.on_reject and self.status and self.team):
            raise ValueError("a gate needs team, status, on_approve and on_reject")
        if self.end and not self.status:
            raise ValueError("an end node needs a status")
        return self

    def targets(self) -> list[str]:
        return [t for t in [self.next, self.on_approve, self.on_reject, *(self.routes or {}).values()] if t]


class PlaybookSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process: str
    stage_no: int
    name: str
    agent: str
    rules: str
    start: str
    nodes: dict[str, NodeSpec]


# --------------------------------------------------------------------------- #
# Graph state — the Kairos 3 context travels in here
# --------------------------------------------------------------------------- #


class CaseState(TypedDict, total=False):
    loan_id: str
    stage_no: int
    agent_run_id: str  # the run executing this graph; nodes stamp it on the rows they write
    rules_version: str
    context: dict[str, Any]  # case data, MSP response, check summaries
    findings: list[dict[str, Any]]  # every check and its result, kept for review
    trial_plan_options: list[dict[str, Any]]
    selected_trial_plan: dict[str, Any] | None
    approved_trial_plan: dict[str, Any] | None
    review_reason: str  # why the next gate should stop
    next: str  # set by the node wrapper from the YAML; read by the one router
    resume_at: str | None  # re-enter here after a decision
    decision: dict[str, Any] | None  # the person's decision, once made
    paused: dict[str, Any] | None  # set by a gate
    result: dict[str, Any] | None  # set by an end node
    trace: Annotated[list[dict[str, Any]], operator.add]  # appended by every node


@dataclass
class Deps:
    """What nodes need besides the state; passed through LangGraph's config."""

    db: Any
    rules: dict[str, Any]
    now: Any


@dataclass
class Playbook:
    spec: PlaybookSpec
    rules: dict[str, Any]
    path: Path
    graph: Any = field(repr=False)

    @property
    def stage_no(self) -> int:
        return self.spec.stage_no

    @property
    def rules_version(self) -> str:
        return str(self.rules.get("version", ""))

    def node(self, name: str) -> NodeSpec:
        return self.spec.nodes[name]


# --------------------------------------------------------------------------- #
# Building the graph
# --------------------------------------------------------------------------- #


def _trace(name: str, spec: NodeSpec, started: float, **extra: Any) -> dict[str, Any]:
    return {"node": name, "title": spec.title or name, "kind": spec.kind, "duration_ms": int((time.perf_counter() - started) * 1000), **extra}


def _run_node(name: str, spec: NodeSpec):
    fn = NODES[spec.run]

    def node(state: CaseState, config) -> dict[str, Any]:
        started = time.perf_counter()
        update = dict(fn(state, config["configurable"]["deps"]) or {})
        outcome = update.pop("outcome", None)
        if spec.next:
            nxt = spec.next
        elif outcome in spec.routes:
            nxt = spec.routes[outcome]
        else:
            raise ValueError(f"node {name} returned outcome {outcome!r}; playbook routes are {sorted(spec.routes)}")
        detail = update.pop("detail", "")
        return {**update, "next": nxt, "trace": [_trace(name, spec, started, outcome=outcome, detail=detail, next=nxt)]}

    return node


def _gate_node(name: str, spec: NodeSpec):
    def node(state: CaseState, config) -> dict[str, Any]:
        started = time.perf_counter()
        reason = state.get("review_reason") or spec.reason or ""
        paused = {"gate": name, "title": spec.title or name, "team": spec.team, "status": spec.status, "reason": reason}
        return {"paused": paused, "next": END, "trace": [_trace(name, spec, started, detail=f"Paused for {spec.team}")]}

    return node


def _end_node(name: str, spec: NodeSpec):
    def node(state: CaseState, config) -> dict[str, Any]:
        started = time.perf_counter()
        result = {"node": name, "status": spec.status, "advance": spec.advance, "team": spec.team}
        return {"result": result, "next": END, "trace": [_trace(name, spec, started, detail=f"Status: {spec.status}")]}

    return node


def _route(state: CaseState) -> str:
    """The only router in the graph."""
    return state["next"]


def compile_graph(spec: PlaybookSpec):
    graph = StateGraph(CaseState)
    for name, node in spec.nodes.items():
        build = {"run": _run_node, "gate": _gate_node, "end": _end_node}[node.kind]
        graph.add_node(name, build(name, node))

    # Enter at `start`, or wherever a decision says to resume.
    entry_points = sorted({spec.start} | {t for n in spec.nodes.values() if n.gate for t in (n.on_approve, n.on_reject)})
    graph.add_conditional_edges(START, lambda s: s.get("resume_at") or spec.start, {n: n for n in entry_points})

    for name, node in spec.nodes.items():
        if node.kind == "run":
            graph.add_conditional_edges(name, _route, {t: t for t in node.targets()})
        else:
            graph.add_edge(name, END)  # gates and end nodes stop the graph
    return graph.compile()


def validate(spec: PlaybookSpec) -> None:
    errors: list[str] = []
    stage = STAGE_BY_NO.get(spec.stage_no)
    if stage is None:
        errors.append(f"unknown stage_no {spec.stage_no}")
    if spec.start not in spec.nodes:
        errors.append(f"start node {spec.start!r} is not defined")
    for name, node in spec.nodes.items():
        for target in node.targets():
            if target not in spec.nodes:
                errors.append(f"{name} → {target!r}: no such node")
        if node.run and node.run not in NODES:
            errors.append(f"{name}: no Python function registered as {node.run!r}")
        if node.status and stage and node.status not in stage.allowed:
            errors.append(f"{name}: status {node.status!r} is not allowed for {stage.name}")
        if node.advance and stage and node.status not in stage.advances:
            errors.append(f"{name}: `advance: true` but {node.status!r} is not a hand-on status for {stage.name} ({', '.join(stage.advances)})")
    if not any(n.advance for n in spec.nodes.values()):
        errors.append("no end node has `advance: true`, so no case could ever move on")
    if errors:
        raise ValueError("Invalid playbook:\n  " + "\n  ".join(errors))


def load_playbook(path: Path) -> Playbook:
    load_node_modules()
    spec = PlaybookSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    rules = yaml.safe_load((path.parent / spec.rules).read_text(encoding="utf-8")) or {}
    # Optional rules references keep review ownership in a process's rules.yaml.
    # Literal teams (including every Intake node) are unchanged.
    for node in spec.nodes.values():
        if node.team and node.team.startswith("$"):
            value = rules
            for key in node.team[1:].split("."):
                value = value[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Invalid team rules reference: {node.team}")
            node.team = value
    validate(spec)
    return Playbook(spec=spec, rules=rules, path=path, graph=compile_graph(spec))


@lru_cache
def playbooks() -> dict[int, Playbook]:
    """Every harness/<process>/playbook.yaml, keyed by stage number. Loaded once per process."""
    found: dict[int, Playbook] = {}
    for path in sorted(HARNESS_DIR.glob("*/playbook.yaml")):
        pb = load_playbook(path)
        if pb.stage_no in found:
            raise ValueError(f"two playbooks for stage {pb.stage_no}: {found[pb.stage_no].path} and {path}")
        found[pb.stage_no] = pb
    return found


def get_playbook(stage_no: int) -> Playbook | None:
    return playbooks().get(stage_no)
